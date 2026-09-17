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
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecMarkdownParser
from runner.adapters.opencode.opencode_worker import OpenCodeEvent
from runner.application.git_operations import GitOperations
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
from runner.domain.config import WorkerConfig
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import QuestionSignal, ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.signal_repository import SignalRepository
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle

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

    @property
    def ready_signal_path(self) -> Path:
        return self.runtime_paths.ready_signal_path(self.ticket.id)

    @property
    def question_path(self) -> Path:
        return self.runtime_paths.question_path(self.ticket.id)

    @classmethod
    def assemble(
        cls,
        root: Path,
        *,
        ticket_id: str = "T030",
        clock_start: float = 0.0,
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
