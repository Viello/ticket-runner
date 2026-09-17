"""Spec 04 Behavioral Test Suite: Signal Protocol, Gatekeeper Verification, and Circuit Breaker.

Validates Spec 04 User Stories end-to-end over scripted ``FakeCommandRunner`` streams,
isolated signal directories, and real temporary filesystems under ``tmp_path``:

  US 01: Worker writes .agent/signals/{ticket_id}_ready.json on implementation completion
  US 02: Worker asks clarification questions via .agent/questions/{ticket_id}.json
  US 03: Runner enforces 10-second grace period for Worker to exit cleanly after emitting a Signal,
         terminating the process (KILLED_SIGNAL) if it fails to exit on its own
  US 04: Gatekeeper independently executes configured build_cmd and test_cmd upon ready Signal
  US 05: Gatekeeper accepts Ticket only when all verification commands exit with code 0
  US 06: Trailing output diagnostics (last 100 lines) re-invoked on failed Verification Attempts
  US 07: Circuit Breaker trips after verification.max_attempts failed attempts
  US 08: [R]etry [hint] restores budget and injects advice into Worker session
  US 09: [S]kip discards uncommitted edits and advances queue after confirmation
  US 10: [A]bort cleanly halts the Runner preserving working tree for direct debugging
  US 11: Question signals updated with status answered and Worker session resumed

Story-to-test matrix (T036 coverage audit):

  US 01: Worker writes ready.json
      -> test_us03_worker_streaming_after_ready_signal_killed_after_grace
      -> test_us04_us05_orchestrator_happy_path_commit_and_relocation_with_ticket_processor
  US 02: Worker asks questions
      -> test_us03_question_signal_triggers_question_pending_without_nudge
      -> test_us11_question_interruption_preserves_budget_and_resumes_session
      -> test_us11_orchestrator_choice_question_scripted_answer_and_resume_to_commit
  US 03: 10s grace / kill
      -> test_us03_worker_streaming_after_ready_signal_killed_after_grace
      -> test_us03_worker_exiting_cleanly_within_grace_not_killed
      -> test_us03_supervisor_reused_resets_grace_state_across_runs
  US 04: Gatekeeper runs build_cmd + test_cmd
      -> test_us04_build_and_test_commands_run_on_ready_signal
      -> test_us04_build_failure_skips_test_cmd
  US 05: Accept only exit 0
      -> test_us04_us05_orchestrator_happy_path_commit_and_relocation_with_ticket_processor
      -> test_us06_failed_verification_reinvokes_session_with_diagnostics_and_passes
  US 06: Trailing diagnostics re-invoke
      -> test_us06_failed_verification_reinvokes_session_with_diagnostics_and_passes
      -> test_orchestrator_malformed_ready_signal_resumes_with_diagnostics_and_passes_later_cycle
  US 07: Breaker trips at max_attempts
      -> test_us07_circuit_breaker_trips_after_max_attempts
  US 08: Retry + hint budget restore
      -> test_us08_retry_with_hint_restores_budget_and_injects_advice
  US 09: Skip discards edits + advance
      -> test_us09_skip_after_budget_exhaustion_returns_skipped_result
      -> test_us09_orchestrator_skip_resets_tree_relocates_and_advances
  US 10: Abort preserves working tree
      -> test_us10_abort_raises_user_abort_error_preserving_working_tree
      -> test_us10_build_container_abort_mid_loop_leaves_tree_byte_identical
  US 11: Question answered + resume
      -> test_us11_question_interruption_preserves_budget_and_resumes_session
      -> test_us11_orchestrator_choice_question_scripted_answer_and_resume_to_commit
      -> test_us11_orchestrator_ready_wins_precedence_when_stale_question_exists
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.adapters.markdown.file_lock import QueueFileLock
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecMarkdownParser
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.adapters.opencode.opencode_worker import OpenCodeEvent
from runner.application.gatekeeper import (
    GatekeeperCommandExecutor,
    VerificationLoop,
    VerificationLoopResult,
    VerificationLoopStatus,
    build_shell_argv,
)
from runner.application.git_operations import GitOperations
from runner.application.queue_orchestrator import QueueOrchestrator, TicketOutcomeStatus
from runner.application.ticket_processor import TicketProcessor
from runner.application.handoff_coordinator import (
    EscalationNotice,
    HandoffCoordinator,
    QUESTION_PENDING,
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.application.worker_supervisor import (
    SIGNAL_GRACE_SECONDS,
    RunTerminationReason,
    SessionRunResult,
    WorkerSupervisor,
)
from runner.container import RunnerContainer, build_container
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.exceptions import UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import QuestionSignal, ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.intervention import InterventionAction, InterventionDecision
from runner.ports.signal_repository import SignalRepository
from tests.fakes.fake_command_runner import (
    CommandInvocation,
    FakeCommandRunner,
    FakeProcessHandle,
)
from tests.fakes.fake_intervention import FakeInterventionGateway
import pytest

SPEC_SLUG = "04-signal-protocol-and-gatekeeper"
SPEC_REL_PATH = f"docs/specs/{SPEC_SLUG}.md"

SPEC_MARKDOWN = (
    "# Spec 04: Signal Protocol, Gatekeeper Verification, and Circuit Breaker\n\n"
    "## Problem Statement\n\n"
    "Autonomous agents hallucinate completion without verifying builds.\n\n"
    "## Solution\n\n"
    "Enforce durable signals, gatekeeper verification, and circuit breaker.\n"
)

GLOBAL_GOTCHAS_MARKDOWN = (
    "# Global Gotchas & Lessons Learned\n\n"
    "---\n\n"
    "### Probe gotcha for spec 04 suite\n"
    "- **Problem**: Probe problem marked for spec 04 behavioral assertions.\n"
    "- **Solution**: Probe solution marked for spec 04 behavioral assertions.\n"
)


def _event(
    event_type: str,
    session_id: str | None = None,
    *,
    tokens: int | None = None,
    text: str | None = None,
) -> str:
    """Render a single OpenCode JSONL stream line as it would appear on stdout."""
    payload: dict[str, Any] = {"type": event_type}
    if session_id is not None:
        payload["sessionID"] = session_id
    part: dict[str, Any] = {}
    if tokens is not None:
        part["tokens"] = {"total": tokens}
    if text is not None:
        part["text"] = text
    if part:
        payload["part"] = part
    return json.dumps(payload)


def _scaffold_ticket(ticket_id: str = "T030", security_required: bool = False) -> Ticket:
    """Create a minimal valid Ticket for Spec 04 behavioral assertions."""
    return Ticket(
        id=ticket_id,
        title="Spec 04 behavioral suite ticket",
        status=TicketStatus.PENDING,
        spec_path=SPEC_REL_PATH,
        requirements=("Enforce signal armed termination.",),
        acceptance_criteria=("Worker killed after 10s grace.",),
        gotchas=(),
        path=Path(f"docs/tickets/{SPEC_SLUG}/{ticket_id}-behavioral.md"),
        security_required=security_required,
    )


def _write_workspace(root: Path) -> Path:
    """Create real workspace documents that the PromptBuilder composes from."""
    specs_dir = root / "docs" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / f"{SPEC_SLUG}.md").write_text(SPEC_MARKDOWN, encoding="utf-8", newline="")

    gotchas_path = root / "docs" / "tickets" / "gotchas.md"
    gotchas_path.parent.mkdir(parents=True, exist_ok=True)
    gotchas_path.write_text(GLOBAL_GOTCHAS_MARKDOWN, encoding="utf-8", newline="")
    return gotchas_path


@dataclass
class Scenario:
    """Assembled Spec 04 runtime wired to a scripted command runner, fake signals, and temp tree."""

    root: Path
    ticket: Ticket
    runtime_paths: RuntimePaths
    runner: FakeCommandRunner
    signals: SignalRepository
    supervisor: WorkerSupervisor
    coordinator: HandoffCoordinator
    clock_time: list[float]
    notices: list[str | EscalationNotice] = field(default_factory=list)
    gateway: FakeInterventionGateway = field(default_factory=FakeInterventionGateway)
    executor: GatekeeperCommandExecutor | None = None

    @property
    def ready_signal_path(self) -> Path:
        return self.runtime_paths.ready_signal_path(self.ticket.id)

    @property
    def question_path(self) -> Path:
        return self.runtime_paths.question_path(self.ticket.id)

    def make_loop(
        self,
        max_attempts: int = 3,
        verification_config: VerificationConfig | None = None,
    ) -> VerificationLoop:
        assert self.executor is not None
        return VerificationLoop(
            ticket=self.ticket,
            cycle_runner=self.coordinator.run_cycle,
            signal_repository=self.signals,
            executor=self.executor,
            intervention_gateway=self.gateway,
            verification_config=verification_config or VerificationConfig(test_cmd="pytest -q"),
            max_attempts=max_attempts,
        )

    @classmethod
    def assemble(
        cls,
        root: Path,
        *,
        ticket_id: str = "T030",
        clock_start: float = 0.0,
        answers: list[str] | None = None,
        decisions: list[InterventionDecision | str] | None = None,
    ) -> Scenario:
        _write_workspace(root)
        ticket = _scaffold_ticket(ticket_id)
        runtime_paths = RuntimePaths(root_dir=root / ".agent")
        runtime_paths.ensure_signals_dir()
        runtime_paths.ensure_questions_dir()
        runtime_paths.ensure_logs_dir()

        runner = FakeCommandRunner()
        clock_time = [clock_start]

        def clock() -> float:
            return clock_time[0]

        notices: list[str | EscalationNotice] = []
        signals = FilesystemSignalRepository(runtime_paths)

        supervisor = WorkerSupervisor(
            command_runner=runner,
            runtime_paths=runtime_paths,
            notify=notices.append,
            cwd=root,
            clock=clock,
            signal_repository=signals,
        )

        coordinator = HandoffCoordinator(
            supervisor=supervisor,
            runtime_paths=runtime_paths,
            notify=notices.append,
            clock=clock,
            signal_repository=signals,
        )

        gateway = FakeInterventionGateway(answers=answers, decisions=decisions)
        executor = GatekeeperCommandExecutor(command_runner=runner, cwd=root)

        return cls(
            root=root,
            ticket=ticket,
            runtime_paths=runtime_paths,
            runner=runner,
            signals=signals,
            supervisor=supervisor,
            coordinator=coordinator,
            clock_time=clock_time,
            notices=notices,
            gateway=gateway,
            executor=executor,
        )


# --- US 03: Signal-Armed Termination & Question Handoff Behavioral Tests ---


def test_us03_worker_streaming_after_ready_signal_killed_after_grace(tmp_path: Path) -> None:
    """US 03: Worker writing ready Signal and continuing to stream is killed after 10s grace.

    Outcome has reason KILLED_SIGNAL, is_crash is False, and ready Signal file remains present.
    """
    sc = Scenario.assemble(tmp_path, ticket_id="T030")
    session_id = "ses_us03ReadyGrace"

    class LingeringWorkerHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=6543, stderr="lingering stderr\n")

        async def stdout_lines(self):
            # Step 1: worker starts
            yield _event("step_start", session_id=session_id) + "\n"
            # Worker authors ready signal
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T030",
                    "status": "ready_for_verification",
                    "modified_files": ["runner/application/worker_supervisor.py"],
                    "self_review_notes": "Implemented signal-armed termination.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("text", session_id=session_id, text="Ready signal emitted") + "\n"
            # Advance clock past the 10-second grace period
            sc.clock_time[0] = 10.0
            await asyncio.sleep(0.001)
            # Step 3: worker keeps streaming beyond grace
            yield _event("text", session_id=session_id, text="Still streaming after ready...") + "\n"

        async def wait(self) -> int:
            return -15

    handle = LingeringWorkerHandle()
    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "prompt text"],
        handle,
    )

    result = asyncio.run(sc.supervisor.run("T030", prompt="prompt text"))

    assert result.reason == RunTerminationReason.KILLED_SIGNAL
    assert result.is_crash is False
    assert result.ready_signal_present is True
    assert handle.terminated is True
    # Verify taskkill tree-kill was issued
    assert any(cmd == ["taskkill", "/PID", "6543", "/T", "/F"] for cmd in sc.runner.commands)


def test_us03_worker_exiting_cleanly_within_grace_not_killed(tmp_path: Path) -> None:
    """US 03: Worker writing ready Signal and exiting within 10s grace retains reason EXITED and is never killed."""
    sc = Scenario.assemble(tmp_path, ticket_id="T030")
    session_id = "ses_us03CleanExit"

    class GracefulWorkerHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=6544, stderr="")

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T030",
                    "status": "ready_for_verification",
                    "modified_files": [],
                    "self_review_notes": "Clean exit within grace.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            # Advance clock by 3 seconds (well within 10s grace)
            sc.clock_time[0] = 3.0
            await asyncio.sleep(0.001)
            # Process completes cleanly without more output

        async def wait(self) -> int:
            return 0

    handle = GracefulWorkerHandle()
    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "prompt text"],
        handle,
    )

    result = asyncio.run(sc.supervisor.run("T030", prompt="prompt text"))

    assert result.reason == RunTerminationReason.EXITED
    assert result.is_crash is False
    assert result.ready_signal_present is True
    assert handle.terminated is False
    assert not any(cmd[:2] == ["taskkill", "/PID"] for cmd in sc.runner.commands)


def test_us03_question_signal_triggers_question_pending_without_nudge(tmp_path: Path) -> None:
    """US 02 / US 03: Pending question Signal causes coordinator to return QUESTION_PENDING.

    Active session ID is populated, question file remains on disk untouched, and no nudge prompt runs.
    """
    sc = Scenario.assemble(tmp_path, ticket_id="T030")
    session_id = "ses_us03QuestionSession"

    question_text = json.dumps({
        "ticket_id": "T030",
        "question": "Which signal timeout should be used?",
        "type": "text",
        "options": None,
        "status": "pending",
        "answer": None,
        "created_at": "2026-09-17T00:00:00+00:00",
    })
    sc.question_path.write_text(question_text, encoding="utf-8")

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    sc.runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=[
            _event("step_start", session_id=session_id) + "\n",
            _event("text", session_id=session_id, text="Asking question...") + "\n",
            _event("step_finish", session_id=session_id, tokens=15000) + "\n",
        ],
        exit_code=0,
    )

    result = asyncio.run(sc.coordinator.run_cycle(sc.ticket))

    assert result.status == SingleCycleStatus.QUESTION_PENDING
    assert result == QUESTION_PENDING
    assert result.session_id == session_id
    assert result.is_question_pending is True
    assert result.ready_signal_present is False

    # Question file remains completely untouched
    assert sc.question_path.read_text(encoding="utf-8") == question_text

    # No nudge prompt was dispatched
    assert len(sc.runner.spawns) == 1


def test_us03_supervisor_reused_resets_grace_state_across_runs(tmp_path: Path) -> None:
    """US 03: Reused supervisor resets signal-armed grace timer between consecutive runs."""
    sc = Scenario.assemble(tmp_path, ticket_id="T030")

    class Run1Handle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=7001)

        async def stdout_lines(self):
            yield _event("step_start", session_id="ses_runA") + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T030",
                    "status": "ready_for_verification",
                    "modified_files": [],
                    "self_review_notes": "First run.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("text", session_id="ses_runA", text="Emitted ready") + "\n"
            sc.clock_time[0] = 10.0
            await asyncio.sleep(0.001)
            yield _event("text", session_id="ses_runA", text="Linger run A") + "\n"

        async def wait(self) -> int:
            return -15

    class Run2Handle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=7002)

        async def stdout_lines(self):
            yield _event("step_start", session_id="ses_runB") + "\n"
            sc.clock_time[0] = 50.0
            await asyncio.sleep(0.001)
            yield _event("step_finish", session_id="ses_runB", tokens=5000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "prompt 1"],
        Run1Handle(),
    )
    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "prompt 2"],
        Run2Handle(),
    )

    # Run 1: gets killed after 10s grace
    res1 = asyncio.run(sc.supervisor.run("T030", prompt="prompt 1"))
    assert res1.reason == RunTerminationReason.KILLED_SIGNAL

    # Remove ready signal for Run 2
    sc.ready_signal_path.unlink()
    sc.clock_time[0] = 40.0

    # Run 2: starts fresh, no signals present, runs cleanly
    res2 = asyncio.run(sc.supervisor.run("T030", prompt="prompt 2"))
    assert res2.reason == RunTerminationReason.EXITED


# --- US 04: Gatekeeper Runs build_cmd + test_cmd Behavioral Tests ---


def test_us04_build_and_test_commands_run_on_ready_signal(tmp_path: Path) -> None:
    """US 04: On ready Signal Gatekeeper runs build_cmd then test_cmd; both exit 0 and Ticket is accepted."""
    sc = Scenario.assemble(tmp_path, ticket_id="T031")
    session_id = "ses_us04BuildPass"
    build_cmd = "python -m build"
    test_cmd = "pytest -q"
    verification_config = VerificationConfig(build_cmd=build_cmd, test_cmd=test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    class ReadyHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=8001)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["runner/core.py"],
                    "self_review_notes": "Build and tests pass locally.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=15000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        ReadyHandle(),
    )
    sc.runner.register_spawn(
        build_shell_argv(build_cmd),
        stdout_lines=["building wheel...", "Successfully built"],
        exit_code=0,
    )
    sc.runner.register_spawn(shell_test_cmd := build_shell_argv(test_cmd), stdout_lines=["1 passed"], exit_code=0)

    loop = sc.make_loop(max_attempts=1, verification_config=verification_config)
    result = asyncio.run(loop.run())

    assert result.is_passed is True
    assert result.attempts == 1
    report = result.verification_report
    assert report is not None
    assert [outcome.label for outcome in report.results] == ["build", "test"]
    assert report.skipped_commands == ()
    assert report.passed is True

    # Both build and test commands were executed in order
    shell_spawns = [inv.cmd for inv in sc.runner.spawn_invocations if inv.cmd[0] not in ("opencode",)]
    assert shell_spawns == [build_shell_argv(build_cmd), shell_test_cmd]


def test_us04_build_failure_skips_test_cmd(tmp_path: Path) -> None:
    """US 04: A failing build_cmd skips test_cmd and records skipped_commands on the verification report."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T031",
        decisions=[InterventionDecision(action=InterventionAction.SKIP)],
    )
    session_id = "ses_us04BuildFail"
    build_cmd = "python -m build"
    test_cmd = "pytest -q"
    verification_config = VerificationConfig(build_cmd=build_cmd, test_cmd=test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    class ReadyHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=8002)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["runner/core.py"],
                    "self_review_notes": "Ready but build broken.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=15000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        ReadyHandle(),
    )
    sc.runner.register_spawn(
        build_shell_argv(build_cmd),
        stdout_lines=["building wheel..."],
        stderr="ERROR: CompileError in core.py",
        exit_code=1,
    )

    loop = sc.make_loop(max_attempts=1, verification_config=verification_config)
    result = asyncio.run(loop.run())

    # Build failure consumes the single attempt and the operator skips the Ticket
    assert result.is_skipped is True
    assert result.attempts == 1
    assert "CompileError in core.py" in (result.diagnostics or "")

    # test_cmd was never spawned
    test_argv = build_shell_argv(test_cmd)
    assert not any(inv.cmd == test_argv for inv in sc.runner.spawn_invocations)

    # Independent verification report confirms test_cmd was skipped
    report = asyncio.run(sc.executor.verify(verification_config))
    assert report.passed is False
    assert report.skipped_commands == (test_cmd,)
    assert [outcome.label for outcome in report.results] == ["build"]


# --- US 06 - US 10: Verification Loop, Diagnostics, & Circuit Breaker Behavioral Tests ---


def test_us06_failed_verification_reinvokes_session_with_diagnostics_and_passes(tmp_path: Path) -> None:
    """US 06: Failed verification re-invokes the active Worker session with trailing diagnostics tail.

    Worker fixes the issue on the second cycle and Gatekeeper accepts the Ticket.
    """
    sc = Scenario.assemble(tmp_path, ticket_id="T031")
    session_id = "ses_us06Active"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    class Session1Handle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=8101)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["runner/core.py"],
                    "self_review_notes": "First attempt implementation.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("text", session_id=session_id, text="Ready signal emitted") + "\n"
            yield _event("step_finish", session_id=session_id, tokens=20000) + "\n"

        async def wait(self) -> int:
            return 0

    class Session2Handle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=8102)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["runner/core.py", "tests/test_core.py"],
                    "self_review_notes": "Fixed failure diagnostics.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("text", session_id=session_id, text="Ready signal emitted again") + "\n"
            yield _event("step_finish", session_id=session_id, tokens=25000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        Session1Handle(),
    )

    # Gatekeeper verification sequence for test_cmd:
    # 1. Fails with trailing output
    sc.runner.register_spawn(
        shell_test_cmd,
        stdout_lines=["running test suite..."],
        stderr="FAILED tests/test_core.py - AssertionError: expected 1 got 0",
        exit_code=1,
    )
    # 2. Passes on second cycle
    sc.runner.register_spawn(
        shell_test_cmd,
        stdout_lines=["running test suite...", "1 passed"],
        exit_code=0,
    )

    # Allow session 2 to receive any resume prompt
    def _dynamic_spawn(cmd: list[str], **kwargs: Any) -> FakeProcessHandle | None:
        if len(cmd) >= 6 and cmd[:4] == ["opencode", "run", "--format", "json"] and cmd[4] == "--session":
            return Session2Handle()
        return None

    # Custom spawn interceptor on sc.runner
    original_spawn = sc.runner.spawn

    async def _intercepting_spawn(cmd: list[str], **kwargs: Any) -> Any:
        dynamic = _dynamic_spawn(cmd, **kwargs)
        if dynamic is not None:
            sc.runner.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=kwargs.get("cwd")))
            return dynamic
        return await original_spawn(cmd, **kwargs)

    sc.runner.spawn = _intercepting_spawn  # type: ignore

    loop = sc.make_loop(max_attempts=3)
    result = asyncio.run(loop.run())

    assert result.is_passed is True
    assert result.attempts == 2
    assert not sc.ready_signal_path.exists()

    # Verify session 2 was invoked with the diagnostics in the prompt
    assert len(sc.runner.spawn_invocations) >= 4  # opencode 1, pytest 1, opencode 2, pytest 2
    opencode_invocations = [inv for inv in sc.runner.spawn_invocations if inv.cmd[0] == "opencode"]
    assert len(opencode_invocations) == 2
    resumed_cmd = opencode_invocations[1].cmd
    assert resumed_cmd[4] == "--session"
    assert resumed_cmd[5] == session_id
    assert "FAILED tests/test_core.py - AssertionError: expected 1 got 0" in resumed_cmd[7]


def test_us07_circuit_breaker_trips_after_max_attempts(tmp_path: Path) -> None:
    """US 07: Circuit breaker trips after verification.max_attempts failed attempts."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T031",
        decisions=[InterventionDecision(action=InterventionAction.SKIP)],
    )
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    class AlwaysReadyHandle(FakeProcessHandle):
        def __init__(self, run_index: int) -> None:
            super().__init__(pid=8200 + run_index)
            self._run_index = run_index

        async def stdout_lines(self):
            yield _event("step_start", session_id=f"ses_{self._run_index}") + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": [],
                    "self_review_notes": f"Run {self._run_index}",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=f"ses_{self._run_index}", tokens=10000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        AlwaysReadyHandle(1),
    )

    run_counter = [1]

    original_spawn = sc.runner.spawn

    async def _intercepting_spawn(cmd: list[str], **kwargs: Any) -> Any:
        if len(cmd) >= 6 and cmd[:4] == ["opencode", "run", "--format", "json"]:
            run_counter[0] += 1
            sc.runner.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=kwargs.get("cwd")))
            return AlwaysReadyHandle(run_counter[0])
        return await original_spawn(cmd, **kwargs)

    sc.runner.spawn = _intercepting_spawn  # type: ignore

    # Register 3 failing test spawns for Gatekeeper
    for i in range(1, 4):
        sc.runner.register_spawn(
            shell_test_cmd,
            stderr=f"Test failure attempt {i}",
            exit_code=1,
        )

    loop = sc.make_loop(max_attempts=3)
    result = asyncio.run(loop.run())

    assert result.is_skipped is True
    assert result.attempts == 3
    assert len(sc.gateway.request_records) == 1
    record = sc.gateway.request_records[0]
    assert record.attempt == 3
    assert "Test failure attempt 3" in record.diagnostics


def test_us08_retry_with_hint_restores_budget_and_injects_advice(tmp_path: Path) -> None:
    """US 08: [R]etry [hint] restores budget and injects advice directly into Worker session."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T031",
        decisions=[
            InterventionDecision(action=InterventionAction.RETRY, hint="Use relative path importing"),
        ],
    )
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    class WorkerHandle(FakeProcessHandle):
        def __init__(self, idx: int) -> None:
            super().__init__(pid=8300 + idx)
            self._idx = idx

        async def stdout_lines(self):
            yield _event("step_start", session_id="ses_retryDemo") + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": [],
                    "self_review_notes": f"Attempt {self._idx}",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id="ses_retryDemo", tokens=10000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        WorkerHandle(1),
    )

    run_counter = [1]
    captured_prompts: list[str] = []
    original_spawn = sc.runner.spawn

    async def _intercepting_spawn(cmd: list[str], **kwargs: Any) -> Any:
        if "--session" in cmd and cmd[:4] == ["opencode", "run", "--format", "json"]:
            run_counter[0] += 1
            captured_prompts.append(cmd[-1])
            sc.runner.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=kwargs.get("cwd")))
            return WorkerHandle(run_counter[0])
        return await original_spawn(cmd, **kwargs)

    sc.runner.spawn = _intercepting_spawn  # type: ignore

    # Attempt 1: fails -> max_attempts=1 trips breaker
    sc.runner.register_spawn(shell_test_cmd, stderr="ModuleNotFoundError: no module 'core'", exit_code=1)
    # Attempt 2 (after retry): passes!
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    loop = sc.make_loop(max_attempts=1)
    result = asyncio.run(loop.run())

    assert result.is_passed is True
    assert result.attempts == 1  # 1 attempt consumed in the fresh budget
    assert len(sc.gateway.request_records) == 1

    # Verify hint was injected into the prompt
    assert len(captured_prompts) == 1
    assert "Operator hint: Use relative path importing" in captured_prompts[0]
    assert "ModuleNotFoundError: no module 'core'" in captured_prompts[0]


def test_us09_skip_after_budget_exhaustion_returns_skipped_result(tmp_path: Path) -> None:
    """US 09: [S]kip returns skip result with diagnostics without modifying the working tree."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T031",
        decisions=[InterventionDecision(action=InterventionAction.SKIP)],
    )
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    class Handle(FakeProcessHandle):
        async def stdout_lines(self):
            yield _event("step_start", session_id="ses_skip") + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["foo.py"],
                    "self_review_notes": "Ready",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id="ses_skip", tokens=1000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        Handle(),
    )
    sc.runner.register_spawn(shell_test_cmd, stderr="Unfixable test failure", exit_code=1)

    loop = sc.make_loop(max_attempts=1)
    result = asyncio.run(loop.run())

    assert result.is_skipped is True
    assert "Unfixable test failure" in (result.diagnostics or "")
    # Gatekeeper loop did not commit or reset git
    assert not any(cmd[:2] == ["git", "reset"] for cmd in sc.runner.commands)


def test_us10_abort_raises_user_abort_error_preserving_working_tree(tmp_path: Path) -> None:
    """US 10: [A]bort cleanly halts raising UserAbortError and preserving working tree for direct debugging."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T031",
        decisions=[InterventionDecision(action=InterventionAction.ABORT)],
    )
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    # Worker leaves an uncommitted file on disk
    workspace_file = tmp_path / "work_in_progress.py"
    workspace_file.write_text("print('debug me on PC')", encoding="utf-8")

    class Handle(FakeProcessHandle):
        async def stdout_lines(self):
            yield _event("step_start", session_id="ses_abort") + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["work_in_progress.py"],
                    "self_review_notes": "Needs debugging",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id="ses_abort", tokens=1000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        Handle(),
    )
    sc.runner.register_spawn(shell_test_cmd, stderr="Hard bug requiring PC debugging", exit_code=1)

    loop = sc.make_loop(max_attempts=1)

    with pytest.raises(UserAbortError, match="Execution aborted by operator"):
        asyncio.run(loop.run())

    # Working tree file was preserved!
    assert workspace_file.is_file()
    assert workspace_file.read_text(encoding="utf-8") == "print('debug me on PC')"


def test_us11_question_interruption_preserves_budget_and_resumes_session(tmp_path: Path) -> None:
    """US 02 / US 11: Question interrupts with 0 budget consumed, and re-entry continues with answer."""
    sc = Scenario.assemble(tmp_path, ticket_id="T031")
    session_id = "ses_us11Q"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    initial_prompt = sc.coordinator.build_initial_prompt(sc.ticket)

    # Session 1: asks a clarification question
    class QuestionHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=8401)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.question_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "question": "Which architecture pattern should be used?",
                    "type": "text",
                    "options": None,
                    "status": "pending",
                    "answer": None,
                    "created_at": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("text", session_id=session_id, text="Question written") + "\n"
            yield _event("step_finish", session_id=session_id, tokens=5000) + "\n"

        async def wait(self) -> int:
            return 0

    # Session 2: after answer is provided, finishes and writes ready signal
    class AnsweredHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=8402)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": "T031",
                    "status": "ready_for_verification",
                    "modified_files": ["arch.py"],
                    "self_review_notes": "Implemented with chosen pattern.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=8000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        QuestionHandle(),
    )

    original_spawn = sc.runner.spawn

    async def _intercepting_spawn(cmd: list[str], **kwargs: Any) -> Any:
        if "--session" in cmd and cmd[:4] == ["opencode", "run", "--format", "json"]:
            sc.runner.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=kwargs.get("cwd")))
            return AnsweredHandle()
        return await original_spawn(cmd, **kwargs)

    sc.runner.spawn = _intercepting_spawn  # type: ignore

    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    loop = sc.make_loop(max_attempts=2)

    # 1. First run: interrupted by pending question
    res1 = asyncio.run(loop.run())
    assert res1.is_question_pending is True
    assert res1.session_id == session_id
    assert res1.attempts == 0
    assert loop.attempts == 0

    # 2. Re-entry with answer prompt
    res2 = asyncio.run(loop.run(prompt="Use Clean Architecture ports and adapters."))
    assert res2.is_passed is True
    assert res2.attempts == 1  # Passed on 1st verification attempt


# --- T032: Ready-Path Ticket Processor & Queue Orchestrator Behavioral Tests ---


def _register_git_fakes(runner: FakeCommandRunner) -> None:
    runner.register(["git", "status", "--porcelain"], stdout="")
    runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    runner.register(["git", "add", "."], stdout="")
    runner.register(["git", "commit", "-m"], stdout="")
    runner.register(["git", "rev-parse", "HEAD"], stdout="f" * 40 + "\n")
    runner.register(["git", "reset", "--hard", "HEAD"], stdout="HEAD is now at fffffff\n")
    runner.register(["git", "clean", "-fd"], stdout="")


def _write_ticket_file(root: Path, ticket: Ticket) -> Path:
    target = root / ticket.path
    target.parent.mkdir(parents=True, exist_ok=True)
    reqs = "\n".join(f"- {r}" for r in ticket.requirements)
    acs = "\n".join(f"- {a}" for a in ticket.acceptance_criteria)
    gotchas = "\n".join(f"- {g}" for g in ticket.gotchas)
    target.write_text(
        f"# {ticket.id} — {ticket.title}\n"
        f"Status: pending\n"
        f"Spec: docs/specs/{SPEC_SLUG}.md\n\n"
        f"### Requirements\n"
        f"{reqs}\n\n"
        f"### Acceptance Criteria\n"
        f"{acs}\n\n"
        f"### Gotchas\n"
        f"{gotchas}\n",
        encoding="utf-8",
    )
    return target


def _make_orchestrator(
    sc: Scenario,
    processor: TicketProcessor,
    commit_scope: str = "queue",
) -> QueueOrchestrator:
    tickets_dir = sc.root / "docs" / "tickets"
    return QueueOrchestrator(
        ticket_store=DirectoryTicketStore(root_dir=tickets_dir),
        lock=QueueFileLock(lock_path=tickets_dir / ".queue.lock"),
        gotchas_store=GotchasStore(path=tickets_dir / "gotchas.md"),
        git_operations=GitOperations(runner=sc.runner, cwd=sc.root),
        processor=processor,
        tickets_dir=tickets_dir,
        commit_scope=commit_scope,
        cwd=sc.root,
    )


def test_us04_us05_orchestrator_happy_path_commit_and_relocation_with_ticket_processor(tmp_path: Path) -> None:
    """T032: Happy path through orchestrator produces single commit, relocates ticket, and purges ready signal."""
    sc = Scenario.assemble(tmp_path, ticket_id="T032")
    ticket_file = _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t032Happy"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
    )
    orchestrator = _make_orchestrator(sc, processor=processor, commit_scope="queue")

    initial_prompt = processor.build_initial_prompt(sc.ticket)

    class HappyHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9201)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            # Worker creates modified file
            mod_file = sc.root / "runner" / "ticket_processor.py"
            mod_file.parent.mkdir(parents=True, exist_ok=True)
            mod_file.write_text("# processed", encoding="utf-8")
            # Author ready signal deterministically inside handle
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/ticket_processor.py"],
                    "self_review_notes": "Implemented and code-review verified.",
                    "new_gotchas": ["Discovered runtime lesson on signal lifecycle."],
                    "scope": "application",
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=3000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        HappyHandle(),
    )
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True
    assert outcome.commit_sha == "f" * 40

    # 1. Exactly one conventional commit authored with scope from signal and Update bullets
    commit_invocations = [inv for inv in sc.runner.invocations if inv.cmd[:2] == ["git", "commit"]]
    assert len(commit_invocations) == 1
    commit_msg = commit_invocations[0].cmd[3]
    assert commit_msg.startswith("feat(application):")
    assert "- Update runner/ticket_processor.py" in commit_msg
    assert "T032" not in commit_msg

    # 2. Ticket relocated to completed/ with Status: completed and Completed timestamp
    assert not ticket_file.exists()
    relocated_file = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert relocated_file.is_file()
    relocated_text = relocated_file.read_text(encoding="utf-8")
    assert "Status: completed" in relocated_text
    assert "Completed: 20" in relocated_text

    # 3. Ready signal file was consumed and is gone
    assert not sc.ready_signal_path.exists()

    # 4. Gotchas appended to gotchas.md
    gotchas_text = (sc.root / "docs" / "tickets" / "gotchas.md").read_text(encoding="utf-8")
    assert "Discovered runtime lesson on signal lifecycle." in gotchas_text


def test_us09_orchestrator_skip_resets_tree_relocates_and_advances(tmp_path: Path) -> None:
    """US 09: [S]kip at orchestrator level resets the working tree, relocates Ticket as skipped, and authors no commit."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T032",
        decisions=[InterventionDecision(action=InterventionAction.SKIP)],
    )
    ticket_file = _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_us09Skip"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
        max_attempts=1,
    )
    orchestrator = _make_orchestrator(sc, processor=processor)
    initial_prompt = processor.build_initial_prompt(sc.ticket)

    class SkipWorkerHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9202)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            # Worker leaves uncommitted edits on disk that skip must discard
            mod_file = sc.root / "runner" / "broken.py"
            mod_file.parent.mkdir(parents=True, exist_ok=True)
            mod_file.write_text("# broken implementation\n", encoding="utf-8")
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/broken.py"],
                    "self_review_notes": "Implemented but unfixable test failure.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=1000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        SkipWorkerHandle(),
    )
    # Verification fails on first attempt, tripping the circuit breaker into the SKIP decision
    sc.runner.register_spawn(shell_test_cmd, stderr="Unfixable test failure", exit_code=1)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_skipped is True
    assert "Unfixable test failure" in str(outcome.details)

    # 1. Working tree was reset (git reset --hard HEAD + git clean -fd)
    assert ["git", "reset", "--hard", "HEAD"] in sc.runner.commands
    assert ["git", "clean", "-fd"] in sc.runner.commands

    # 2. Ticket relocated to completed/ with Status: skipped
    assert not ticket_file.exists()
    relocated_file = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert relocated_file.is_file()
    assert "Status: skipped" in relocated_file.read_text(encoding="utf-8")

    # 3. No commit was authored
    commit_invocations = [inv for inv in sc.runner.invocations if inv.cmd[:2] == ["git", "commit"]]
    assert len(commit_invocations) == 0

    # 4. Ready signal was consumed
    assert not sc.ready_signal_path.exists()


def test_orchestrator_malformed_ready_signal_resumes_with_diagnostics_and_passes_later_cycle(tmp_path: Path) -> None:
    """T032: Malformed ready Signal resumes with diagnostics and can only pass on a later valid cycle."""
    sc = Scenario.assemble(tmp_path, ticket_id="T032")
    _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t032Malformed"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
        max_attempts=2,
    )
    orchestrator = _make_orchestrator(sc, processor=processor, commit_scope="queue")
    initial_prompt = processor.build_initial_prompt(sc.ticket)

    # Session 1: emits malformed ready signal (bad status value)
    class MalformedHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9301)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "not_a_valid_status",
                    "modified_files": ["mod.py"],
                    "self_review_notes": "Premature exit.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=1000) + "\n"

        async def wait(self) -> int:
            return 0

    # Session 2: after receiving diagnostics, emits valid ready signal
    class ValidResumeHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9302)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["mod.py"],
                    "self_review_notes": "Fixed status.",
                    "new_gotchas": [],
                    "scope": "domain",
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=2000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        MalformedHandle(),
    )

    original_spawn = sc.runner.spawn

    captured_resume_prompts: list[str] = []

    async def _intercept_resume(cmd: list[str], **kwargs: Any) -> Any:
        if "--session" in cmd and cmd[:4] == ["opencode", "run", "--format", "json"]:
            captured_resume_prompts.append(cmd[-1])
            sc.runner.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=kwargs.get("cwd")))
            return ValidResumeHandle()
        return await original_spawn(cmd, **kwargs)

    sc.runner.spawn = _intercept_resume  # type: ignore
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True

    # Check that resume prompt contained diagnostics explaining the malformed signal
    assert len(captured_resume_prompts) == 1
    assert "ready_for_verification" in captured_resume_prompts[0] or "status" in captured_resume_prompts[0]

    # Ready signal consumed and ticket completed
    assert not sc.ready_signal_path.exists()
    relocated_file = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert relocated_file.is_file()


def test_orchestrator_scope_absent_falls_back_to_orchestrator_default(tmp_path: Path) -> None:
    """T032: When scope is absent in ready Signal, commit uses orchestrator default commit scope."""
    sc = Scenario.assemble(tmp_path, ticket_id="T032")
    _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t032ScopeFallback"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
    )
    orchestrator = _make_orchestrator(sc, processor=processor, commit_scope="ports")
    initial_prompt = processor.build_initial_prompt(sc.ticket)

    class HandleNoScope(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9401)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/ports/seam.py"],
                    "self_review_notes": "Scope omitted.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=1000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        HandleNoScope(),
    )
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True

    # Commit header falls back to orchestrator default 'ports'
    commit_invocations = [inv for inv in sc.runner.invocations if inv.cmd[:2] == ["git", "commit"]]
    assert len(commit_invocations) == 1
    commit_msg = commit_invocations[0].cmd[3]
    assert commit_msg.startswith("feat(ports):")
    assert "- Update runner/ports/seam.py" in commit_msg


def test_orchestrator_purge_at_start_removes_leftover_signal_files(tmp_path: Path) -> None:
    """T032: Purge at start removes leftover ready and question files from earlier runs."""
    sc = Scenario.assemble(tmp_path, ticket_id="T032")
    _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t032Purge"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    # Pre-author stale ready and question files from an earlier run
    sc.ready_signal_path.write_text("stale ready file", encoding="utf-8")
    sc.question_path.write_text("stale question file", encoding="utf-8")
    assert sc.ready_signal_path.is_file()
    assert sc.question_path.is_file()

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
    )
    orchestrator = _make_orchestrator(sc, processor=processor)
    initial_prompt = processor.build_initial_prompt(sc.ticket)

    leftovers_purged_before_worker_start = False

    class PurgeVerifyHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9501)

        async def stdout_lines(self):
            nonlocal leftovers_purged_before_worker_start
            # Check that stale files were already removed before worker began!
            if not sc.ready_signal_path.exists() and not sc.question_path.exists():
                leftovers_purged_before_worker_start = True

            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/purged.py"],
                    "self_review_notes": "Verified purge.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=1000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        PurgeVerifyHandle(),
    )
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True
    assert leftovers_purged_before_worker_start is True


# --- T033: Question Loop & Answer Resume Behavioral Tests ---


def test_us11_orchestrator_choice_question_scripted_answer_and_resume_to_commit(tmp_path: Path) -> None:
    """T033 / US 11: Choice question leads to scripted answer, audit retention on disk, resume prompt, and single commit."""
    sc = Scenario.assemble(tmp_path, ticket_id="T033", answers=["A"])
    ticket_file = _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t033ChoiceQuestion"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
    )
    orchestrator = _make_orchestrator(sc, processor=processor, commit_scope="queue")
    initial_prompt = processor.build_initial_prompt(sc.ticket)

    class QuestionHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9601)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.question_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "question": "Which database backend should be selected?",
                    "type": "choice",
                    "options": ["A) SQLite", "B) Postgres"],
                    "status": "pending",
                    "answer": None,
                    "created_at": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("text", session_id=session_id, text="Awaiting answer...") + "\n"
            yield _event("step_finish", session_id=session_id, tokens=2000) + "\n"

        async def wait(self) -> int:
            return 0

    class AnsweredResumeHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9602)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            mod_file = sc.root / "runner" / "database.py"
            mod_file.parent.mkdir(parents=True, exist_ok=True)
            mod_file.write_text("# choice A sqlite database", encoding="utf-8")
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/database.py"],
                    "self_review_notes": "Implemented choice A.",
                    "new_gotchas": [],
                    "scope": "application",
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=4000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        QuestionHandle(),
    )

    captured_resumes: list[list[str]] = []
    original_spawn = sc.runner.spawn

    async def _intercept_resume(cmd: list[str], **kwargs: Any) -> Any:
        if "--session" in cmd and cmd[:4] == ["opencode", "run", "--format", "json"]:
            captured_resumes.append(list(cmd))
            sc.runner.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=kwargs.get("cwd")))
            return AnsweredResumeHandle()
        return await original_spawn(cmd, **kwargs)

    sc.runner.spawn = _intercept_resume  # type: ignore
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True
    assert outcome.commit_sha == "f" * 40

    # 1. Gateway prompted question and received scripted answer 'A'
    assert len(sc.gateway.question_prompts) == 1
    prompted_q = sc.gateway.question_prompts[0]
    assert prompted_q.question == "Which database backend should be selected?"
    assert prompted_q.options == ("A) SQLite", "B) Postgres")

    # 2. Worker session resumed with same session_id and answer prompt
    assert len(captured_resumes) == 1
    resumed_cmd = captured_resumes[0]
    assert resumed_cmd[4] == "--session"
    assert resumed_cmd[5] == session_id
    assert resumed_cmd[-1] == "User answered: A. Proceed with implementation."

    # 3. Ready signal consumed, but answered question retained for audit
    assert not sc.ready_signal_path.exists()
    assert sc.question_path.is_file()
    saved_q = json.loads(sc.question_path.read_text(encoding="utf-8"))
    assert saved_q["status"] == "answered"
    assert saved_q["answer"] == "A"
    assert saved_q["options"] == ["A) SQLite", "B) Postgres"]

    # 4. Commit produced and ticket relocated
    assert not ticket_file.exists()
    relocated = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert relocated.is_file()


def test_us11_orchestrator_ready_wins_precedence_when_stale_question_exists(tmp_path: Path) -> None:
    """T033 / US 11: With both pending question and valid ready Signal, ready wins, no prompt is issued, and question is cleaned."""
    sc = Scenario.assemble(tmp_path, ticket_id="T033")
    ticket_file = _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t033ReadyWins"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    processor = TicketProcessor(
        coordinator=sc.coordinator,
        signal_repository=sc.signals,
        executor=sc.executor,
        intervention_gateway=sc.gateway,
    )
    orchestrator = _make_orchestrator(sc, processor=processor, commit_scope="queue")
    initial_prompt = processor.build_initial_prompt(sc.ticket)

    class BothSignalsHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9701)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            mod_file = sc.root / "runner" / "precedence.py"
            mod_file.parent.mkdir(parents=True, exist_ok=True)
            mod_file.write_text("# precedence", encoding="utf-8")
            # Author BOTH a pending question and a valid ready signal
            sc.question_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "question": "Stale pending question that should be skipped?",
                    "type": "text",
                    "options": None,
                    "status": "pending",
                    "answer": None,
                    "created_at": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/precedence.py"],
                    "self_review_notes": "Implemented and ready wins.",
                    "new_gotchas": [],
                    "scope": "domain",
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=3000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        BothSignalsHandle(),
    )
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed"], exit_code=0)

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True

    # 1. Operator was NEVER prompted for the question
    assert len(sc.gateway.question_prompts) == 0

    # 2. Stale question was cleaned and ready signal consumed
    assert not sc.question_path.exists()
    assert not sc.ready_signal_path.exists()

    # 3. Commit authored and ticket relocated
    assert not ticket_file.exists()
    relocated = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert relocated.is_file()


# --- US 10 / US 12: Composition Root & Abort Handling Behavioral Tests ---


def test_us12_build_container_end_to_end_in_process_success(tmp_path: Path) -> None:
    """T034 / US 12: build_container wires real pipeline and processes a Ticket end-to-end in-process."""
    sc = Scenario.assemble(tmp_path, ticket_id="T034")
    ticket_file = _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t034Container"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd=test_cmd, max_attempts=3),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion="terminate"),
        git=GitConfig(),
    )

    container = build_container(
        config=config,
        command_runner=sc.runner,
        intervention_gateway=sc.gateway,
        ticket_store=DirectoryTicketStore(root_dir=sc.root / "docs" / "tickets"),
        gotchas_store=GotchasStore(path=sc.root / "docs" / "tickets" / "gotchas.md"),
        lock=QueueFileLock(lock_path=sc.root / ".agent" / ".queue.lock"),
        runtime_paths=sc.runtime_paths,
        cwd=sc.root,
        clock=lambda: sc.clock_time[0],
    )

    initial_prompt = container.processor.build_initial_prompt(sc.ticket)

    class WorkerHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9801)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            mod_file = sc.root / "runner" / "composed.py"
            mod_file.parent.mkdir(parents=True, exist_ok=True)
            mod_file.write_text("# composed pipeline implementation", encoding="utf-8")
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/composed.py"],
                    "self_review_notes": "All requirements implemented via container.",
                    "new_gotchas": [],
                    "scope": "domain",
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=4000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        WorkerHandle(),
    )
    sc.runner.register_spawn(shell_test_cmd, stdout_lines=["1 passed in 0.01s"], exit_code=0)

    exit_code = asyncio.run(container.orchestrator.run_lifecycle(lifecycle=config.lifecycle))

    assert exit_code == 0
    assert container.orchestrator.last_outcome is not None
    assert container.orchestrator.last_outcome.is_approved is True
    assert container.orchestrator.last_outcome.commit_sha == "f" * 40
    assert container.lock.is_locked is False

    # Ready signal consumed, ticket relocated, commit recorded
    assert not sc.ready_signal_path.exists()
    assert not ticket_file.exists()
    relocated = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert relocated.is_file()


def test_us10_build_container_abort_mid_loop_leaves_tree_byte_identical(tmp_path: Path) -> None:
    """T034 / US 10: [A]bort mid-loop leaves working tree byte-identical, stops lifecycle, releases lock, and exits with code 2."""
    sc = Scenario.assemble(
        tmp_path,
        ticket_id="T034",
        decisions=[InterventionDecision(action=InterventionAction.ABORT)],
    )
    ticket_file = _write_ticket_file(sc.root, sc.ticket)
    _register_git_fakes(sc.runner)

    session_id = "ses_t034Abort"
    test_cmd = "pytest -q"
    shell_test_cmd = build_shell_argv(test_cmd)

    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd=test_cmd, max_attempts=1),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion="standby"),
        git=GitConfig(),
    )

    container = build_container(
        config=config,
        command_runner=sc.runner,
        intervention_gateway=sc.gateway,
        ticket_store=DirectoryTicketStore(root_dir=sc.root / "docs" / "tickets"),
        gotchas_store=GotchasStore(path=sc.root / "docs" / "tickets" / "gotchas.md"),
        lock=QueueFileLock(lock_path=sc.root / ".agent" / ".queue.lock"),
        runtime_paths=sc.runtime_paths,
        cwd=sc.root,
        clock=lambda: sc.clock_time[0],
    )

    initial_prompt = container.processor.build_initial_prompt(sc.ticket)

    # Operator has uncommitted WIP edits that must remain completely untouched
    wip_file = sc.root / "runner" / "work_in_progress.py"
    wip_file.parent.mkdir(parents=True, exist_ok=True)
    wip_content = b"# uncommitted operator debug work\nprint('byte-identical-test')\n"
    wip_file.write_bytes(wip_content)

    class FailingWorkerHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(pid=9802)

        async def stdout_lines(self):
            yield _event("step_start", session_id=session_id) + "\n"
            sc.ready_signal_path.write_text(
                json.dumps({
                    "ticket_id": sc.ticket.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/work_in_progress.py"],
                    "self_review_notes": "Implemented but failing tests",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
            yield _event("step_finish", session_id=session_id, tokens=2000) + "\n"

        async def wait(self) -> int:
            return 0

    sc.runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        FailingWorkerHandle(),
    )
    # Verification fails on first attempt, tripping Circuit Breaker
    sc.runner.register_spawn(shell_test_cmd, stderr="AssertionError: verification failed", exit_code=1)

    exit_code = asyncio.run(container.orchestrator.run_lifecycle(lifecycle=config.lifecycle))

    # 1. CLI / lifecycle exited with code 2
    assert exit_code == 2

    # 2. Working tree is byte-identical: no reset, no commit, no archive
    assert wip_file.is_file()
    assert wip_file.read_bytes() == wip_content
    for inv in sc.runner.invocations:
        assert "reset" not in inv.argv
        assert "commit" not in inv.argv

    # 3. Ticket was NOT finalized or relocated
    assert ticket_file.is_file()
    relocated = sc.root / "docs" / "tickets" / SPEC_SLUG / "completed" / f"{sc.ticket.id}-behavioral.md"
    assert not relocated.exists()

    # 4. Sentinel lock was released
    assert container.lock.is_locked is False

    # 5. Outcome was recorded as ABORTED
    assert container.orchestrator.last_outcome is not None
    assert container.orchestrator.last_outcome.is_aborted is True
    assert container.orchestrator.last_outcome.status == TicketOutcomeStatus.ABORTED


