"""Unit tests for HandoffCoordinator application interactor (T021 & T022)."""

import asyncio
import json
import os
from pathlib import Path
import pytest

from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecExcerpt
from runner.application.git_operations import GitOperations
from runner.application.handoff_coordinator import (
    CLOCK_SLACK_SECONDS,
    ESCALATED,
    EscalationNotice,
    HandoffCoordinator,
    MAX_CONSECUTIVE_HANDOFFS,
    SingleCycleResult,
    SingleCycleStatus,
    WorkerRunResult,
    default_recovery_confirmation,
    is_checkpoint_fresh,
)
from runner.application.worker_supervisor import RunTerminationReason, WorkerSupervisor
from runner.domain.config import TokenBudgetConfig, WorkerConfig
from runner.domain.exceptions import TicketFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle


def _make_ticket(
    ticket_id: str = "T022",
    security_required: bool = True,
    spec_path: str = "docs/specs/03-worker-orchestration-and-handoff.md",
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Handoff coordinator test ticket",
        status=TicketStatus.PENDING,
        spec_path=spec_path,
        requirements=("Implement single handoff cycle.", "Validate checkpoints."),
        acceptance_criteria=("135k triggers handoff run.", "150k triggers ceiling."),
        gotchas=("Validate checkpoint after process exit.",),
        path=Path(f"docs/tickets/03-worker-orchestration-and-handoff/{ticket_id}-test.md"),
        security_required=security_required,
    )


SAMPLE_SPEC_EXCERPT = SpecExcerpt(
    text="## Problem Statement\n\nContext limits exist.\n\n## Solution\n\nContext handoff coordinator.",
    spec_path="docs/specs/03-worker-orchestration-and-handoff.md",
    problem_statement="Context limits exist.",
    solution="Context handoff coordinator.",
)


# --- AC 1 (T021): Handoff at 135k, Fixed Prompt, Fresh Checkpoint, Session B Resume ---


def test_handoff_at_135k_runs_same_session_and_resumes_session_b(tmp_path: Path) -> None:
    """Scripted run crossing 135k is killed, handoff run is spawned with --session <learned-id>

    and fixed instruction text, fresh checkpoint passes, and Session B resumes with checkpoint
    and git status instructions, ending READY.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022", security_required=True)
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    session_a_id = "ses_firstSession1"
    session_b_id = "ses_secondSession2"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    session_handoff_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "text",
            "sessionID": session_a_id,
            "part": {"text": "Wrote checkpoint file successfully."},
        }) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 136000}},
        }) + "\n",
    ]

    session_b_lines = [
        json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_b_id,
            "part": {"tokens": {"total": 45000}},
        }) + "\n",
    ]

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: 1000.0,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    assert "Context budget threshold reached (135k tokens)." in handoff_prompt
    assert ".agents/skills/handoff/SKILL.md" in handoff_prompt
    assert checkpoint_file.as_posix() in handoff_prompt
    assert "include modified files, architectural decisions, test status, and immediate next steps" in handoff_prompt.lower()
    assert handoff_prompt.strip().endswith("Then exit.")

    assert checkpoint_file.as_posix() in resume_prompt
    assert "`git status`" in resume_prompt
    assert "T022" in resume_prompt

    # Deterministic handle writing checkpoint upon wait()
    class _HandoffHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(stdout_lines=session_handoff_lines)

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T022")
            checkpoint_file.write_text("# Checkpoint\n- Modified: file1.py", encoding="utf-8")
            os.utime(checkpoint_file, (1001.0, 1001.0))
            return 0

    class _SessionBHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(stdout_lines=session_b_lines)

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path("T022")
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        _HandoffHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _SessionBHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result == "READY"
    assert result.is_ready is True
    assert result.session_id == session_a_id
    assert result.resumed_session_id == session_b_id
    assert result.session_ids == (session_a_id, session_b_id)
    assert result.occupancy == 136000
    assert result.handoffs == 1
    assert result.ready_signal_present is True
    assert len(result.run_results) == 3

    assert len(fake_runner.spawns) == 3
    assert fake_runner.spawns[0] == ["opencode", "run", "--format", "json", "--auto", initial_prompt]
    assert fake_runner.spawns[1] == ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt]
    assert fake_runner.spawns[2] == ["opencode", "run", "--format", "json", "--auto", resume_prompt]


# --- T022 Path 1: Exit 0 Without Ready Signal (Nudge) ---


def test_exit_0_without_ready_signal_nudges_same_session_and_succeeds(tmp_path: Path) -> None:
    """Exit 0 without ready signal triggers exactly one nudge spawn on same session;

    signal appearing on disk during nudge returns READY.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    session_id = "ses_nudgeSession"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 30000}}}) + "\n",
    ]

    nudge_prompt = coordinator_prompt = f"You exited without writing `.agent/signals/{ticket.id}_ready.json`. Write it with your `self_review_notes`, or report the blocker, then exit."

    class _NudgeHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(stdout_lines=[
                json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
                json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 32000}}}) + "\n",
            ])

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path(ticket.id)
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready", "self_review_notes": "All ACs pass"}', encoding="utf-8")
            return 0

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_id, "--auto", nudge_prompt],
        _NudgeHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True
    assert result.session_id == session_id
    assert result.occupancy == 32000
    assert len(fake_runner.spawns) == 2
    assert fake_runner.spawns[1] == [
        "opencode", "run", "--format", "json", "--session", session_id, "--auto", nudge_prompt
    ]


def test_exit_0_without_ready_signal_nudges_and_escalates_on_missing_signal(tmp_path: Path) -> None:
    """If nudge run also finishes without a ready signal, execution escalates."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    session_id = "ses_nudgeEscalate"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 30000}}}) + "\n",
    ]
    nudge_lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 35000}}}) + "\n",
    ]

    notices: list[EscalationNotice] = []
    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        notify=notices.append,
        confirm_recovery=lambda esc: False,  # Decline recovery
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    nudge_prompt = coordinator.build_nudge_prompt(ticket)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", session_id, "--auto", nudge_prompt],
        stdout_lines=nudge_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "ESCALATED"
    assert result == WorkerRunResult.ESCALATED
    assert result.is_ready is False
    assert result.is_escalated is True
    assert len(fake_runner.spawns) == 2
    assert len(notices) == 1
    assert notices[0].ticket_id == "T022"
    assert notices[0].reason == "NO_SIGNAL_AFTER_NUDGE"


# --- T022 Path 2: Crash Retry (Non-Zero Exit or Error Event) ---


def test_crash_retries_once_same_session_with_trimmed_stderr(tmp_path: Path) -> None:
    """Non-zero exit triggers exactly one same-session retry whose prompt includes stderr tail."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    session_id = "ses_crashSession"

    stderr_msg = "Error: unhandled exception in build script\nTraceback line 42"

    class _CrashHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
                ],
                stderr=stderr_msg,
                exit_code=1,
            )

    class _RetryHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
                    json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 40000}}}) + "\n",
                ],
                exit_code=0,
            )

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path(ticket.id)
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    retry_prompt = coordinator.build_crash_retry_prompt(ticket, stderr_msg)

    assert "unhandled exception in build script" in retry_prompt
    assert "Traceback line 42" in retry_prompt

    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        _CrashHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_id, "--auto", retry_prompt],
        _RetryHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True
    assert len(fake_runner.spawns) == 2
    assert fake_runner.spawns[1] == [
        "opencode", "run", "--format", "json", "--session", session_id, "--auto", retry_prompt
    ]


def test_second_crash_escalates_without_third_spawn(tmp_path: Path) -> None:
    """A second crash on the retry run escalates without a third spawn."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    session_id = "ses_doubleCrash"

    class _Crash1Handle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[json.dumps({"type": "step_start", "sessionID": session_id}) + "\n"],
                stderr="First crash error",
                exit_code=1,
            )

    class _Crash2Handle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[json.dumps({"type": "step_start", "sessionID": session_id}) + "\n"],
                stderr="Second crash error",
                exit_code=1,
            )

    notices: list[EscalationNotice] = []
    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        notify=notices.append,
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    retry_prompt = coordinator.build_crash_retry_prompt(ticket, "First crash error")

    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        _Crash1Handle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_id, "--auto", retry_prompt],
        _Crash2Handle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "CRASH_AFTER_RETRY"
    assert result.is_ready is False
    assert len(fake_runner.spawns) == 2  # Exactly 2 spawns: initial + retry; no 3rd spawn
    assert len(notices) == 1
    assert notices[0].reason == "CRASH_AFTER_RETRY"
    assert "Second crash error" in notices[0].stderr_tail


def test_stream_error_event_triggers_crash_retry(tmp_path: Path) -> None:
    """A stream 'error' event triggers crash retry even if process exits with code 0."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    session_id = "ses_streamError"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "error", "sessionID": session_id, "part": {"message": "Model connection refused"}}) + "\n",
    ]

    class _RetryHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
                    json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 25000}}}) + "\n",
                ],
                exit_code=0,
            )

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path(ticket.id)
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    retry_prompt = coordinator.build_crash_retry_prompt(ticket, "")

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_id, "--auto", retry_prompt],
        _RetryHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert len(fake_runner.spawns) == 2


# --- T022 Path 3: Escalation and Emergency Synthesis ---


def test_escalation_confirmed_synthesizes_checkpoint_and_resumes_fresh_session(tmp_path: Path) -> None:
    """With confirm_recovery True, synthetic checkpoint is written with status/diff content

    and marker 'synthesized — no Worker handoff', then a fresh session resumes.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    session_a_id = "ses_ceilingBreach"
    session_resumed_id = "ses_emergencyResume"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_a_id, "part": {"tokens": {"total": 150000}}}) + "\n",
    ]

    class _ResumedHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_resumed_id}) + "\n",
                    json.dumps({"type": "step_finish", "sessionID": session_resumed_id, "part": {"tokens": {"total": 20000}}}) + "\n",
                ]
            )

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path(ticket.id)
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    # Register fake git operations
    fake_runner.register_result(
        ["git", "status", "--porcelain"],
        CommandResult(exit_code=0, stdout=" M runner/coordinator.py\n?? untracked.py\n", stderr=""),
    )
    fake_runner.register_result(
        ["git", "diff", "--stat"],
        CommandResult(exit_code=0, stdout=" runner/coordinator.py | 12 +++---\n 1 file changed\n", stderr=""),
    )

    git_ops = GitOperations(runner=fake_runner)
    notices: list[EscalationNotice] = []

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        git_operations=git_ops,
        notify=notices.append,
        confirm_recovery=lambda esc: True,  # Authorize recovery
        clock=lambda: 5555.0,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _ResumedHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True
    assert result.resumed_session_id == session_resumed_id
    assert result.session_ids == (session_a_id, session_resumed_id)

    # Verify synthetic checkpoint file content
    assert checkpoint_file.is_file()
    content = checkpoint_file.read_text(encoding="utf-8")
    assert "synthesized — no Worker handoff" in content
    assert "T022" in content
    assert "CEILING" in content
    assert "5555.0" in content
    assert "ses_ceilingBreach" in content
    assert "M runner/coordinator.py" in content
    assert "1 file changed" in content


def test_escalation_declined_leaves_tree_untouched_and_writes_no_checkpoint(tmp_path: Path) -> None:
    """Declined confirmation returns WorkerRunResult.ESCALATED, writes no checkpoint,

    and leaves working tree untouched.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    session_a_id = "ses_ceilingBreach"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_a_id, "part": {"tokens": {"total": 150000}}}) + "\n",
    ]

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        confirm_recovery=lambda esc: False,  # Decline
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "ESCALATED"
    assert result == WorkerRunResult.ESCALATED
    assert result == "CEILING"
    assert result.is_ready is False
    assert not checkpoint_file.exists()  # No checkpoint written!
    assert len(fake_runner.spawns) == 1  # No fresh session spawned


def test_stall_routes_through_confirmation_flow(tmp_path: Path) -> None:
    """Stall failure routes through confirmation flow."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")

    session_a_id = "ses_stallSession"
    notices: list[EscalationNotice] = []

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        stall_timeout=5.0,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        notify=notices.append,
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    class _StallHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n"],
                delay=10.0,
            )

    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        _StallHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "STALLED"
    assert len(notices) == 1
    assert notices[0].reason == "STALLED"


def test_emergency_synthesis_does_not_overwrite_valid_cycle_checkpoint(tmp_path: Path) -> None:
    """Emergency synthesis must not overwrite a valid fresh checkpoint from the current cycle."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    session_a_id = "ses_handoffPassed"
    session_b_id = "ses_sessionBCrashed"
    session_resumed_id = "ses_sessionCResumed"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_a_id, "part": {"tokens": {"total": 135000}}}) + "\n",
    ]
    session_handoff_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_a_id, "part": {"tokens": {"total": 136000}}}) + "\n",
    ]

    class _HandoffHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(stdout_lines=session_handoff_lines)

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T022")
            checkpoint_file.write_text("# Worker Real Checkpoint\n- Detailed findings", encoding="utf-8")
            os.utime(checkpoint_file, (1001.0, 1001.0))
            return 0

    class _SessionBCrashHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n"],
                stderr="Session B fatal crash",
                exit_code=1,
            )

    class _SessionBRetryCrashHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n"],
                stderr="Session B second crash",
                exit_code=1,
            )

    class _SessionCResumedHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_resumed_id}) + "\n",
                    json.dumps({"type": "step_finish", "sessionID": session_resumed_id, "part": {"tokens": {"total": 20000}}}) + "\n",
                ]
            )

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path(ticket.id)
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: 1000.0,
        confirm_recovery=lambda esc: True,  # Authorize recovery
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)
    retry_prompt = coordinator.build_crash_retry_prompt(ticket, "Session B fatal crash")

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        _HandoffHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _SessionBCrashHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_b_id, "--auto", retry_prompt],
        _SessionBRetryCrashHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _SessionCResumedHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    # Verify the original worker checkpoint was NOT overwritten by emergency synthesis
    assert checkpoint_file.is_file()
    content = checkpoint_file.read_text(encoding="utf-8")
    assert "# Worker Real Checkpoint" in content
    assert "synthesized — no Worker handoff" not in content


# --- T021 Checkpoint Stale and Missing Failures (Now Escalated) ---


def test_checkpoint_written_before_handoff_request_fails_as_stale(tmp_path: Path) -> None:
    """A checkpoint written before handoff_requested_at fails validation and escalates."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    session_a_id = "ses_stale123"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135500}},
        }) + "\n",
    ]
    session_handoff_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 136000}},
        }) + "\n",
    ]

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    simulated_time = [1000.0]
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: simulated_time[0],
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        stdout_lines=session_handoff_lines,
    )

    runtime_paths.ensure_checkpoint_dir("T022")
    checkpoint_file.write_text("# Old Checkpoint from previous run", encoding="utf-8")
    os.utime(checkpoint_file, (995.0, 995.0))

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "CHECKPOINT_STALE"
    assert result == "ESCALATED"
    assert result.is_ready is False
    assert result.session_id == session_a_id
    assert len(fake_runner.spawns) == 2


def test_missing_checkpoint_returns_checkpoint_missing_and_escalates(tmp_path: Path) -> None:
    """Missing checkpoint file fails validation and escalates."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")

    session_a_id = "ses_missing123"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]
    session_handoff_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 136000}},
        }) + "\n",
    ]

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        stdout_lines=session_handoff_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "CHECKPOINT_MISSING"
    assert result == "ESCALATED"
    assert result.is_ready is False
    assert len(fake_runner.spawns) == 2


# --- Clock Slack Boundary Invariants ---


def test_checkpoint_freshness_clock_slack_boundary(tmp_path: Path) -> None:
    """Verify ADR 0014 2.0s clock slack boundary calculation."""
    checkpoint_file = tmp_path / "handoff.md"
    checkpoint_file.write_text("content", encoding="utf-8")

    handoff_requested_at = 1000.0

    os.utime(checkpoint_file, (998.0, 998.0))
    assert is_checkpoint_fresh(checkpoint_file, handoff_requested_at, slack=CLOCK_SLACK_SECONDS) is True

    os.utime(checkpoint_file, (998.1, 998.1))
    assert is_checkpoint_fresh(checkpoint_file, handoff_requested_at, slack=CLOCK_SLACK_SECONDS) is True

    os.utime(checkpoint_file, (997.9, 997.9))
    assert is_checkpoint_fresh(checkpoint_file, handoff_requested_at, slack=CLOCK_SLACK_SECONDS) is False


# --- Gotcha Verification: Validation strictly after process exits ---


def test_checkpoint_validated_strictly_after_process_exits(tmp_path: Path) -> None:
    """Worker may write checkpoint only as instruction run exits; validate after wait() completes."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    session_a_id = "ses_delayedExit"
    session_b_id = "ses_delayedExitB"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    class DelayedHandoffHandle:
        def __init__(self) -> None:
            self.pid = 4455
            self.stderr = ""
            self.has_exited = False

        async def stdout_lines(self):
            yield json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n"
            yield json.dumps({"type": "text", "sessionID": session_a_id, "part": {"text": "Saving..."}}) + "\n"

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T022")
            checkpoint_file.write_text("# Checkpoint on process exit", encoding="utf-8")
            os.utime(checkpoint_file, (1000.5, 1000.5))
            self.has_exited = True
            return 0

        async def terminate(self) -> None:
            pass

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: 1000.0,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        DelayedHandoffHandle(),
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n"],
    )

    runtime_paths.ensure_signals_dir()
    runtime_paths.ready_signal_path("T022").write_text('{"status": "ready"}', encoding="utf-8")

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True


# --- Security: Required Verifications ---


def test_security_checkpoint_path_containment_and_traversal_rejection(tmp_path: Path) -> None:
    """Security: checkpoint path must be built strictly through RuntimePaths without traversal."""
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    coordinator = HandoffCoordinator(runtime_paths=runtime_paths)

    with pytest.raises((TicketFormatError, ValueError)):
        _make_ticket(ticket_id="../../etc/passwd")

    status = coordinator.validate_checkpoint("../../escaped", handoff_requested_at=1000.0)
    assert status == SingleCycleStatus.CHECKPOINT_MISSING


def test_security_resumed_session_id_must_be_stream_learned_and_allowlist_valid(tmp_path: Path) -> None:
    """Security: resumed --session must be learned from stream and allowlist-validated."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022")

    malicious_session_id = "ses_evil;rm -rf /"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": malicious_session_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": malicious_session_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "FAILED"
    assert len(fake_runner.spawns) == 1
    assert not any("--session" in inv.cmd for inv in fake_runner.spawn_invocations)


def test_security_prompts_contain_no_environment_expansion_or_secret_leakage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Security: prompts must contain repo/ticket data only and never leak environment tokens or secrets."""
    secret_token = "ghp_superSecretToken1234567890"
    monkeypatch.setenv("DISCORD_BOT_TOKEN", secret_token)
    monkeypatch.setenv("OPENCODE_API_KEY", "opencode_secret_key_999")

    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T022", security_required=True)
    checkpoint_file = runtime_paths.checkpoint_path("T022")

    coordinator = HandoffCoordinator(runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)
    nudge_prompt = coordinator.build_nudge_prompt(ticket)
    retry_prompt = coordinator.build_crash_retry_prompt(ticket, "error detail")

    for p in (initial_prompt, handoff_prompt, resume_prompt, nudge_prompt, retry_prompt):
        assert secret_token not in p
        assert "opencode_secret_key_999" not in p
        assert "$DISCORD_BOT_TOKEN" not in p
        assert "%DISCORD_BOT_TOKEN%" not in p
        assert "$OPENCODE_API_KEY" not in p


def test_security_default_recovery_confirmation_safe_on_closed_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security: default_recovery_confirmation must catch OSError, EOFError, KeyboardInterrupt and return False."""
    def _raise_oserror(prompt: str = "") -> str:
        raise OSError("reading from stdin while output is captured")

    monkeypatch.setattr("builtins.input", _raise_oserror)
    assert default_recovery_confirmation("T022") is False

    def _raise_eof(prompt: str = "") -> str:
        raise EOFError()

    monkeypatch.setattr("builtins.input", _raise_eof)
    assert default_recovery_confirmation("T022") is False

    def _raise_interrupt(prompt: str = "") -> str:
        raise KeyboardInterrupt()

    monkeypatch.setattr("builtins.input", _raise_interrupt)
    assert default_recovery_confirmation("T022") is False


# ==============================================================================
# --- T023: Handoff Chain Loop, Cap, Notices, and Public Result Contract ---
# ==============================================================================


def test_handoff_chain_loop_a_to_b_to_c_finishes_ready(tmp_path: Path) -> None:
    """A scripted A->B->C chain validates a fresh checkpoint per cycle and finishes READY.

    Supervisor records the exact spawn sequence and session_ids has 3 entries.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T023")
    checkpoint_file = runtime_paths.checkpoint_path("T023")

    session_a_id = "ses_chainA"
    session_b_id = "ses_chainB"
    session_c_id = "ses_chainC"

    simulated_time = [1000.0]

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: simulated_time[0],
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    # Session A: runs, crosses 135k
    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    # Handoff A: writes checkpoint at t=1001.0
    class _HandoffAHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_a_id,
                        "part": {"tokens": {"total": 136000}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T023")
            checkpoint_file.write_text("# Checkpoint Cycle 1\n- Handing off from A", encoding="utf-8")
            os.utime(checkpoint_file, (1001.0, 1001.0))
            return 0

    # Session B: runs, crosses 135k at simulated time 1010.0
    session_b_lines = [
        json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_b_id,
            "part": {"tokens": {"total": 135200}},
        }) + "\n",
    ]

    # Handoff B: writes fresh checkpoint at t=1011.0
    class _HandoffBHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_b_id,
                        "part": {"tokens": {"total": 137000}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T023")
            checkpoint_file.write_text("# Checkpoint Cycle 2\n- Handing off from B", encoding="utf-8")
            os.utime(checkpoint_file, (1011.0, 1011.0))
            return 0

    # Session C: runs, writes ready signal and finishes
    class _SessionCHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_c_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_c_id,
                        "part": {"tokens": {"total": 25000}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path("T023")
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        _HandoffAHandle(),
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        stdout_lines=session_b_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_b_id, "--auto", handoff_prompt],
        _HandoffBHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _SessionCHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result == "READY"
    assert result.is_ready is True
    assert result.session_id == session_a_id
    assert result.resumed_session_id == session_c_id
    assert result.session_ids == (session_a_id, session_b_id, session_c_id)
    assert len(result.session_ids) == 3
    assert result.handoffs == 2
    assert result.ready_signal_present is True
    assert result.occupancy == 137000
    assert len(result.run_results) == 5

    # Check fake runner recorded exactly 5 spawns in order
    assert len(fake_runner.spawns) == 5
    assert fake_runner.spawns[0] == ["opencode", "run", "--format", "json", "--auto", initial_prompt]
    assert fake_runner.spawns[1] == ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt]
    assert fake_runner.spawns[2] == ["opencode", "run", "--format", "json", "--auto", resume_prompt]
    assert fake_runner.spawns[3] == ["opencode", "run", "--format", "json", "--session", session_b_id, "--auto", handoff_prompt]
    assert fake_runner.spawns[4] == ["opencode", "run", "--format", "json", "--auto", resume_prompt]

    # Verify log paths are distinct across sessions
    assert len(result.jsonl_paths) == 3
    assert len(set(result.jsonl_paths)) == 3
    assert result.jsonl_path_for(session_a_id) is not None
    assert result.jsonl_path_for(session_b_id) is not None
    assert result.jsonl_path_for(session_c_id) is not None


def test_handoff_chain_reaches_cap_and_escalates_without_sixth_session(tmp_path: Path) -> None:
    """A chain reaching MAX_CONSECUTIVE_HANDOFFS (5) escalates without a sixth session spawn,

    and the escalation payload names '5 handoffs without completion'.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T023")
    checkpoint_file = runtime_paths.checkpoint_path("T023")

    simulated_time = [1000.0]
    notices: list[str | EscalationNotice] = []

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: simulated_time[0],
        notify=notices.append,
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    session_ids = [f"ses_cap{i}" for i in range(1, 6)]

    # Register 5 cycles of session run + handoff run
    for i, sid in enumerate(session_ids):
        t_base = 1000.0 + (i * 20.0)

        # Worker session crossing 135k
        session_lines = [
            json.dumps({"type": "step_start", "sessionID": sid}) + "\n",
            json.dumps({
                "type": "step_finish",
                "sessionID": sid,
                "part": {"tokens": {"total": 135100}},
            }) + "\n",
        ]

        # Handoff handle writing fresh checkpoint
        current_t = t_base + 2.0
        class _CycleHandoffHandle(FakeProcessHandle):
            def __init__(self, target_time: float, cycle_idx: int) -> None:
                super().__init__(
                    stdout_lines=[
                        json.dumps({"type": "step_start", "sessionID": sid}) + "\n",
                        json.dumps({
                            "type": "step_finish",
                            "sessionID": sid,
                            "part": {"tokens": {"total": 136000}},
                        }) + "\n",
                    ]
                )
                self._target_time = target_time
                self._cycle_idx = cycle_idx

            async def wait(self) -> int:
                runtime_paths.ensure_checkpoint_dir("T023")
                checkpoint_file.write_text(f"# Checkpoint cycle {self._cycle_idx}", encoding="utf-8")
                os.utime(checkpoint_file, (self._target_time, self._target_time))
                return 0

        if i == 0:
            fake_runner.register_spawn(
                ["opencode", "run", "--format", "json", "--auto", initial_prompt],
                stdout_lines=session_lines,
            )
        else:
            fake_runner.register_spawn(
                ["opencode", "run", "--format", "json", "--auto", resume_prompt],
                stdout_lines=session_lines,
            )

        fake_runner.register_spawn_handle(
            ["opencode", "run", "--format", "json", "--session", sid, "--auto", handoff_prompt],
            _CycleHandoffHandle(current_t, i + 1),
        )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "ESCALATED"
    assert result.is_escalated is True
    assert result.is_ready is False
    assert result.handoffs == 5
    assert result.session_ids == tuple(session_ids)
    assert len(result.session_ids) == 5

    # Exactly 5 worker sessions + 5 handoffs = 10 spawns. Absolutely NO 6th session (11th spawn)!
    assert len(fake_runner.spawns) == 10

    # Escalation payload names '5 handoffs without completion'
    assert result.escalation is not None
    assert result.escalation.reason == "5 handoffs without completion"
    assert "5 handoffs without completion" in str(result.escalation)
    assert result.escalation_details == "5 handoffs without completion"


def test_handoff_chain_stale_checkpoint_in_cycle_two_fails_freshness_and_escalates(tmp_path: Path) -> None:
    """Cycle 2 handoff does not update checkpoint; fails freshness check against cycle 2 request time and escalates."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T023")
    checkpoint_file = runtime_paths.checkpoint_path("T023")

    session_a_id = "ses_staleA"
    session_b_id = "ses_staleB"

    simulated_time = [1000.0]

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        clock=lambda: simulated_time[0],
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    # Session A: hits 135k
    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    # Handoff A: writes checkpoint at t=1001.0
    class _HandoffAHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_a_id,
                        "part": {"tokens": {"total": 136000}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T023")
            checkpoint_file.write_text("# Checkpoint Cycle 1", encoding="utf-8")
            os.utime(checkpoint_file, (1001.0, 1001.0))
            return 0

    # Session B: hits 135k at simulated time 1050.0
    session_b_lines = [
        json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_b_id,
            "part": {"tokens": {"total": 135500}},
        }) + "\n",
    ]

    class _SessionBHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(stdout_lines=session_b_lines)

        async def stdout_lines(self):
            simulated_time[0] = 1050.0
            for line in session_b_lines:
                yield line.rstrip("\r\n")

    # Handoff B: runs at t=1050.0 but DOES NOT update checkpoint file (mtime remains 1001.0)
    class _HandoffBHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_b_id,
                        "part": {"tokens": {"total": 136500}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            return 0

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        _HandoffAHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _SessionBHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_b_id, "--auto", handoff_prompt],
        _HandoffBHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == "CHECKPOINT_STALE"
    assert result.is_ready is False
    assert result.is_escalated is True
    assert result.handoffs == 2
    assert len(fake_runner.spawns) == 4  # Session A, Handoff A, Session B, Handoff B; NO Session C!


def test_handoff_chain_emits_cycle_notices_through_t019_seam(tmp_path: Path) -> None:
    """Coordinator emits notices per handoff cycle: threshold crossed, checkpoint validated, session N+1 started."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T023")
    checkpoint_file = runtime_paths.checkpoint_path("T023")

    session_a_id = "ses_noticesA"
    session_b_id = "ses_noticesB"

    notices: list[str | EscalationNotice] = []

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        notify=notices.append,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    class _HandoffHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_a_id,
                        "part": {"tokens": {"total": 136000}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            runtime_paths.ensure_checkpoint_dir("T023")
            checkpoint_file.write_text("# Checkpoint", encoding="utf-8")
            return 0

    class _SessionBHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=[
                    json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
                    json.dumps({
                        "type": "step_finish",
                        "sessionID": session_b_id,
                        "part": {"tokens": {"total": 20000}},
                    }) + "\n",
                ]
            )

        async def wait(self) -> int:
            ready_sig = runtime_paths.ready_signal_path("T023")
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")
            return 0

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        _HandoffHandle(),
    )
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        _SessionBHandle(),
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))
    assert result.status == SingleCycleStatus.READY

    notice_texts = [str(n) for n in notices]

    # Verify notice for threshold crossed
    assert any("threshold crossed" in text.lower() for text in notice_texts)
    # Verify notice for checkpoint validated
    assert any("checkpoint validated" in text.lower() for text in notice_texts)
    # Verify notice for session N+1 started
    assert any("session 2 started" in text.lower() or "session n+1 started" in text.lower() for text in notice_texts)


def test_worker_run_result_public_contract_and_session_paths(tmp_path: Path) -> None:
    """Complete WorkerRunResult public type satisfies Spec 04 contract with log paths and escalation details."""
    p_jsonl_1 = tmp_path / "T023_ses1.jsonl"
    p_stderr_1 = tmp_path / "T023_ses1.stderr"
    p_jsonl_2 = tmp_path / "T023_ses2.jsonl"
    p_stderr_2 = tmp_path / "T023_ses2.stderr"

    from runner.application.worker_supervisor import SessionRunResult

    run1 = SessionRunResult(
        session_id="ses_1",
        occupancy=135000,
        jsonl_path=p_jsonl_1,
        stderr_path=p_stderr_1,
    )
    run2 = SessionRunResult(
        session_id="ses_2",
        occupancy=50000,
        ready_signal_present=True,
        jsonl_path=p_jsonl_2,
        stderr_path=p_stderr_2,
    )

    result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        session_id="ses_1",
        resumed_session_id="ses_2",
        session_ids=("ses_1", "ses_2"),
        handoffs=1,
        occupancy=135000,
        ready_signal_present=True,
        run_results=(run1, run2),
    )

    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True
    assert result.is_escalated is False
    assert result.session_ids == ("ses_1", "ses_2")
    assert result.handoffs == 1
    assert result.occupancy == 135000
    assert result.ready_signal_present is True
    assert result.jsonl_paths == (p_jsonl_1, p_jsonl_2)
    assert result.stderr_paths == (p_stderr_1, p_stderr_2)
    assert result.jsonl_path_for("ses_1") == p_jsonl_1
    assert result.jsonl_path_for("ses_2") == p_jsonl_2
    assert result.stderr_path_for("ses_1") == p_stderr_1
    assert result.stderr_path_for("ses_2") == p_stderr_2
    assert result.jsonl_paths_by_session == {"ses_1": p_jsonl_1, "ses_2": p_jsonl_2}
    assert result.stderr_paths_by_session == {"ses_1": p_stderr_1, "ses_2": p_stderr_2}
    assert result.escalation_details is None

    # Test escalated WorkerRunResult with details
    escalation = EscalationNotice(
        ticket_id="T023",
        reason="5 handoffs without completion",
        session_id="ses_2",
        occupancy=135000,
    )
    esc_result = WorkerRunResult(
        status=SingleCycleStatus.ESCALATED,
        session_ids=("ses_1", "ses_2"),
        handoffs=5,
        occupancy=135000,
        escalation=escalation,
    )
    assert esc_result.is_escalated is True
    assert esc_result.is_ready is False
    assert esc_result.escalation_details == "5 handoffs without completion"
    assert esc_result == "5 handoffs without completion"
    assert esc_result == "ESCALATED"


def test_security_loop_termination_is_guaranteed_and_bounded(tmp_path: Path) -> None:
    """Security: verify no unbounded spawn loop is reachable from repeated handoffs; loop unconditionally halts at cap."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T023", security_required=True)
    checkpoint_file = runtime_paths.checkpoint_path("T023")

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        confirm_recovery=lambda esc: False,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    # Configure fake runner to endlessly trigger handoffs
    for i in range(1, 10):
        sid = f"ses_endless{i}"
        session_lines = [
            json.dumps({"type": "step_start", "sessionID": sid}) + "\n",
            json.dumps({
                "type": "step_finish",
                "sessionID": sid,
                "part": {"tokens": {"total": 135000}},
            }) + "\n",
        ]

        class _EndlessHandoffHandle(FakeProcessHandle):
            def __init__(self, s_id: str) -> None:
                super().__init__(
                    stdout_lines=[
                        json.dumps({"type": "step_start", "sessionID": s_id}) + "\n",
                        json.dumps({
                            "type": "step_finish",
                            "sessionID": s_id,
                            "part": {"tokens": {"total": 136000}},
                        }) + "\n",
                    ]
                )

            async def wait(self) -> int:
                runtime_paths.ensure_checkpoint_dir("T023")
                checkpoint_file.write_text("# Checkpoint", encoding="utf-8")
                return 0

        if i == 1:
            fake_runner.register_spawn(
                ["opencode", "run", "--format", "json", "--auto", initial_prompt],
                stdout_lines=session_lines,
            )
        else:
            fake_runner.register_spawn(
                ["opencode", "run", "--format", "json", "--auto", resume_prompt],
                stdout_lines=session_lines,
            )

        fake_runner.register_spawn_handle(
            ["opencode", "run", "--format", "json", "--session", sid, "--auto", handoff_prompt],
            _EndlessHandoffHandle(sid),
        )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result.handoffs == MAX_CONSECUTIVE_HANDOFFS  # 5
    assert len(result.session_ids) == 5
    # Strict bound: no more than 10 spawns (5 sessions + 5 handoffs)
    assert len(fake_runner.spawns) == 10

