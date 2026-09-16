"""Unit tests for HandoffCoordinator application interactor (T021)."""

import asyncio
import json
import os
from pathlib import Path
import pytest

from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecExcerpt
from runner.application.handoff_coordinator import (
    CLOCK_SLACK_SECONDS,
    HandoffCoordinator,
    SingleCycleResult,
    SingleCycleStatus,
    is_checkpoint_fresh,
)
from runner.application.worker_supervisor import WorkerSupervisor
from runner.domain.config import TokenBudgetConfig, WorkerConfig
from runner.domain.exceptions import TicketFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner


def _make_ticket(
    ticket_id: str = "T021",
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


# --- AC 1: Handoff at 135k, Fixed Prompt, Checkpoint Freshness, and Session B Resume ---


def test_handoff_at_135k_runs_same_session_and_resumes_session_b(tmp_path: Path) -> None:
    """Scripted run crossing 135k is killed, handoff run is spawned with --session <learned-id>

    and fixed instruction text, fresh checkpoint passes, and Session B resumes with checkpoint
    and git status instructions, ending READY.
    """
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021", security_required=True)
    checkpoint_file = runtime_paths.checkpoint_path("T021")

    session_a_id = "ses_firstSession1"
    session_b_id = "ses_secondSession2"

    # Stream for Session A: hits 135,000 tokens
    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 135000}},
        }) + "\n",
    ]

    # Stream for Handoff instruction run on Session A
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

    # Stream for Session B: fresh session, finishes with ready signal
    session_b_lines = [
        json.dumps({"type": "step_start", "sessionID": session_b_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_b_id,
            "part": {"tokens": {"total": 45000}},
        }) + "\n",
    ]

    # Initial prompt matching
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
    )

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    # Verify Spec 03 fixed prompt content
    assert "Context budget threshold reached (135k tokens)." in handoff_prompt
    assert ".agents/skills/handoff/SKILL.md" in handoff_prompt
    assert checkpoint_file.as_posix() in handoff_prompt
    assert "include modified files, architectural decisions, test status, and immediate next steps" in handoff_prompt.lower()
    assert handoff_prompt.strip().endswith("Then exit.")

    # Verify Resume prompt content
    assert checkpoint_file.as_posix() in resume_prompt
    assert "`git status`" in resume_prompt
    assert "T021" in resume_prompt

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt],
        stdout_lines=session_handoff_lines,
    )
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", resume_prompt],
        stdout_lines=session_b_lines,
    )

    # Fake clock to test freshness
    simulated_time = [1000.0]

    def _clock() -> float:
        return simulated_time[0]

    coordinator._clock = _clock

    async def _execute() -> SingleCycleResult:
        async def _run_cycle_with_checkpoint():
            run_task = asyncio.create_task(
                coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
            )
            # Give Session A time to run and trigger handoff
            await asyncio.sleep(0.01)
            # Advance clock and write fresh checkpoint
            simulated_time[0] = 1001.0
            runtime_paths.ensure_checkpoint_dir("T021")
            checkpoint_file.write_text("# Checkpoint\n- Modified: file1.py", encoding="utf-8")
            os.utime(checkpoint_file, (1001.0, 1001.0))

            # Emit ready signal for Session B
            ready_sig = runtime_paths.ready_signal_path("T021")
            runtime_paths.ensure_signals_dir()
            ready_sig.write_text('{"status": "ready"}', encoding="utf-8")

            return await run_task

        return await _run_cycle_with_checkpoint()

    result = asyncio.run(_execute())

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

    # Verify command sequence in spawns
    assert len(fake_runner.spawns) == 3
    # 1. Initial run (no --session)
    assert fake_runner.spawns[0] == [
        "opencode", "run", "--format", "json", "--auto", initial_prompt
    ]
    # 2. Handoff run (with --session learned-id)
    assert fake_runner.spawns[1] == [
        "opencode", "run", "--format", "json", "--session", session_a_id, "--auto", handoff_prompt
    ]
    # 3. Session B run (no --session, fresh session)
    assert fake_runner.spawns[2] == [
        "opencode", "run", "--format", "json", "--auto", resume_prompt
    ]


# --- AC 2: Checkpoint Stale and Missing Failures ---


def test_checkpoint_written_before_handoff_request_fails_as_stale(tmp_path: Path) -> None:
    """A checkpoint written before handoff_requested_at fails validation and returns CHECKPOINT_STALE."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021")
    checkpoint_file = runtime_paths.checkpoint_path("T021")

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

    # Pre-write a stale checkpoint with mtime older than (1000.0 - 2.0)
    runtime_paths.ensure_checkpoint_dir("T021")
    checkpoint_file.write_text("# Old Checkpoint from previous run", encoding="utf-8")
    os.utime(checkpoint_file, (995.0, 995.0))

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.CHECKPOINT_STALE
    assert result == "CHECKPOINT_STALE"
    assert result.is_ready is False
    assert result.session_id == session_a_id
    assert result.resumed_session_id is None
    # Exactly 2 spawns: Session A and handoff run; no Session B spawned
    assert len(fake_runner.spawns) == 2


def test_missing_checkpoint_returns_checkpoint_missing(tmp_path: Path) -> None:
    """Missing checkpoint file returns CHECKPOINT_MISSING with no Session B spawn."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021")

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
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

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

    # Do not create checkpoint file
    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.CHECKPOINT_MISSING
    assert result == "CHECKPOINT_MISSING"
    assert result.is_ready is False
    assert len(fake_runner.spawns) == 2


# --- AC 3: Crossing 150k Ceiling ---


def test_crossing_150k_kills_with_ceiling_and_launches_no_handoff(tmp_path: Path) -> None:
    """Crossing 150k kills with KILLED_CEILING and launches no handoff run."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021")

    session_a_id = "ses_ceilingBreach"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 150000}},
        }) + "\n",
    ]

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.CEILING
    assert result == "CEILING"
    assert result.is_ready is False
    assert result.occupancy == 150000
    # No handoff run launched: exactly 1 spawn
    assert len(fake_runner.spawns) == 1


# --- AC 4: Normal Exit Under Thresholds With Ready Signal ---


def test_normal_exit_under_thresholds_with_ready_signal_returns_ready(tmp_path: Path) -> None:
    """A run that exits under thresholds with a ready signal returns READY with no extra spawns."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021")

    session_a_id = "ses_cleanRun"

    session_a_lines = [
        json.dumps({"type": "step_start", "sessionID": session_a_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_a_id,
            "part": {"tokens": {"total": 50000}},
        }) + "\n",
    ]

    # Pre-write ready signal
    runtime_paths.ensure_signals_dir()
    runtime_paths.ready_signal_path("T021").write_text('{"status": "ready"}', encoding="utf-8")

    supervisor = WorkerSupervisor(command_runner=fake_runner, runtime_paths=runtime_paths)
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result == "READY"
    assert result.is_ready is True
    assert result.session_id == session_a_id
    assert result.occupancy == 50000
    assert result.ready_signal_present is True
    assert result.handoffs == 0
    # No handoff or session B: exactly 1 spawn
    assert len(fake_runner.spawns) == 1


# --- Clock Slack Boundary Invariants ---


def test_checkpoint_freshness_clock_slack_boundary(tmp_path: Path) -> None:
    """Verify ADR 0014 2.0s clock slack boundary calculation."""
    checkpoint_file = tmp_path / "handoff.md"
    checkpoint_file.write_text("content", encoding="utf-8")

    handoff_requested_at = 1000.0

    # Exactly at boundary: 1000.0 - 2.0 = 998.0 -> fresh
    os.utime(checkpoint_file, (998.0, 998.0))
    assert is_checkpoint_fresh(checkpoint_file, handoff_requested_at, slack=CLOCK_SLACK_SECONDS) is True

    # Just inside boundary: 998.1 -> fresh
    os.utime(checkpoint_file, (998.1, 998.1))
    assert is_checkpoint_fresh(checkpoint_file, handoff_requested_at, slack=CLOCK_SLACK_SECONDS) is True

    # Just outside boundary: 997.9 -> stale
    os.utime(checkpoint_file, (997.9, 997.9))
    assert is_checkpoint_fresh(checkpoint_file, handoff_requested_at, slack=CLOCK_SLACK_SECONDS) is False


# --- Gotcha Verification: Validation strictly after process exits ---


def test_checkpoint_validated_strictly_after_process_exits(tmp_path: Path) -> None:
    """Worker may write checkpoint only as instruction run exits; validate after wait() completes."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021")
    checkpoint_file = runtime_paths.checkpoint_path("T021")

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
            # Checkpoint is written only when process wait() finishes
            runtime_paths.ensure_checkpoint_dir("T021")
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

    # Pre-write ready signal for Session B
    runtime_paths.ensure_signals_dir()
    runtime_paths.ready_signal_path("T021").write_text('{"status": "ready"}', encoding="utf-8")

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True


# --- Security: Required Verifications ---


def test_security_checkpoint_path_containment_and_traversal_rejection(tmp_path: Path) -> None:
    """Security: checkpoint path must be built strictly through RuntimePaths without traversal."""
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    coordinator = HandoffCoordinator(runtime_paths=runtime_paths)

    # 1. Invalid ticket ID raises TicketFormatError or ValueError
    with pytest.raises((TicketFormatError, ValueError)):
        _make_ticket(ticket_id="../../etc/passwd")

    # 2. validate_checkpoint directly rejects traversal IDs
    status = coordinator.validate_checkpoint("../../escaped", handoff_requested_at=1000.0)
    assert status == SingleCycleStatus.CHECKPOINT_MISSING


def test_security_resumed_session_id_must_be_stream_learned_and_allowlist_valid(tmp_path: Path) -> None:
    """Security: resumed --session must be learned from stream and allowlist-validated."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021")

    # Worker emits unallowlisted session ID
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
    coordinator = HandoffCoordinator(supervisor=supervisor, runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", initial_prompt],
        stdout_lines=session_a_lines,
    )

    result = asyncio.run(coordinator.run_cycle(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT))

    # Malicious session ID is rejected; handoff run is NOT spawned with it
    assert result.status == SingleCycleStatus.FAILED
    assert len(fake_runner.spawns) == 1
    assert not any("--session" in inv.cmd for inv in fake_runner.spawn_invocations)


def test_security_prompts_contain_no_environment_expansion_or_secret_leakage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Security: prompts must contain repo/ticket data only and never leak environment tokens or secrets."""
    secret_token = "ghp_superSecretToken1234567890"
    monkeypatch.setenv("DISCORD_BOT_TOKEN", secret_token)
    monkeypatch.setenv("OPENCODE_API_KEY", "opencode_secret_key_999")

    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    ticket = _make_ticket("T021", security_required=True)
    checkpoint_file = runtime_paths.checkpoint_path("T021")

    coordinator = HandoffCoordinator(runtime_paths=runtime_paths)

    initial_prompt = coordinator.build_initial_prompt(ticket, spec_excerpt=SAMPLE_SPEC_EXCERPT)
    handoff_prompt = coordinator.build_handoff_prompt(ticket)
    resume_prompt = coordinator.build_resume_prompt(ticket, checkpoint_file)

    for p in (initial_prompt, handoff_prompt, resume_prompt):
        assert secret_token not in p
        assert "opencode_secret_key_999" not in p
        # Ensure no shell-style expansion placeholders are left raw or evaluated
        assert "$DISCORD_BOT_TOKEN" not in p
        assert "%DISCORD_BOT_TOKEN%" not in p
        assert "$OPENCODE_API_KEY" not in p
