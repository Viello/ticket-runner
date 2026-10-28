"""Spec 16 Behavioral Test Suite: Live-Run Gatekeeper Shell Quoting, Antigravity Telemetry, and Queue Boundary Remediation.

Validates Spec 16 requirements:
  - Seam 1: Windows Gatekeeper shell quoting preserves double quotes in Python one-liners
            and retains Windows Job Object process-tree termination without CancelledError.
  - Seam 2: Provider-agnostic token telemetry calculates true per-step context occupancy
            (including cache_read_tokens) under Antigravity, suppresses cumulative result.usage,
            decouples stall heartbeats from token presence, forwards active tools to UI,
            and enforces ready-signal precedence over late budget escalations.
  - Seam 3: Autonomous queue boundary guardrails forbid queue file mutations and gotchas direct edits,
            and DirectoryTicketStore.finalize_completed handles pre-relocated ticket files idempotently.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import shutil
import sys
from typing import Any
import pytest

from runner.adapters.antigravity.antigravity_worker import AntigravityWorker
from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.markdown.parser import TicketMarkdownParser
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.gatekeeper import GatekeeperCommandExecutor, build_shell_argv
from runner.application.handoff_coordinator import (
    HandoffCoordinator,
    SingleCycleStatus,
)
from runner.application.prompt_builder import PromptBuilder, build_prompt
from runner.application.state_coordinator import StateCoordinator
from runner.application.worker_supervisor import RunTerminationReason, SessionRunResult, WorkerSupervisor
from runner.domain.config import TokenBudgetConfig, VerificationConfig
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.telemetry import BudgetAction
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_state_store import FakeStateStore
from tests.fakes.fake_status_publisher import FakeStatusPublisher


def _make_ticket(
    ticket_id: str = "T123",
    status: TicketStatus = TicketStatus.PENDING,
    requirements: tuple[str, ...] = ("Test requirement",),
    path: Path | None = None,
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Test Ticket",
        status=status,
        spec_path="docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md",
        requirements=requirements,
        acceptance_criteria=("Test criteria",),
        gotchas=(),
        path=path or Path(f"docs/tickets/16-live-run/{ticket_id}.md"),
    )


# ==============================================================================
# Seam 1: Windows Gatekeeper Shell Quoting & Subprocess Supervision
# ==============================================================================


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shell quoting Gatekeeper integration test")
def test_seam1_gatekeeper_windows_shell_quoting_with_real_subprocess_runner() -> None:
    """GatekeeperCommandExecutor verifies double-quoted Python one-liner via real SubprocessRunner on Windows."""
    runner = SubprocessRunner()
    executor = GatekeeperCommandExecutor(command_runner=runner)

    # Exact double-quoted Python YAML-validation one-liner from the live T101 run
    test_cmd = (
        'python -c "import glob,yaml; '
        'fs=glob.glob(\'*/agents/openai.yaml\'); '
        '[yaml.safe_load(open(f,encoding=\'utf-8\')) for f in fs]; '
        'print(\'validated %d openai.yaml files\' % len(fs))"'
    )

    report = asyncio.run(executor.verify(VerificationConfig(test_cmd=test_cmd)))
    assert report.passed is True
    assert report.diagnostics == ()
    assert len(report.results) == 1
    assert report.results[0].exit_code == 0
    assert report.results[0].timed_out is False
    assert "validated 0 openai.yaml files" in report.results[0].tail


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object test")
def test_seam1_subprocess_runner_windows_job_tree_termination() -> None:
    """SubprocessRunner terminates child process tree in Windows Job Object without CancelledError."""
    runner = SubprocessRunner()
    sleep_cmd = 'python -c "import time; time.sleep(30)"'
    argv = build_shell_argv(sleep_cmd, "win32")

    async def _scenario() -> None:
        handle = await runner.spawn(argv)
        assert handle.pid > 0
        await asyncio.sleep(0.2)
        await handle.terminate()
        code = await handle.wait()
        assert code is not None

    asyncio.run(_scenario())


# ==============================================================================
# Seam 2: Antigravity Token Occupancy, Heartbeat Decoupling & Ready Precedence
# ==============================================================================


def test_seam2_antigravity_token_occupancy_parity_and_cumulative_result_suppressed(
    tmp_path: Path,
) -> None:
    """True per-step context occupancy is recorded and cumulative result.usage is suppressed."""
    session_id = "f4446873-0561-4a98-b9a9-13da3c00b3af"
    ticket = _make_ticket("T123")
    stream_lines = [
        json.dumps({"event": "init", "conversation_id": session_id}) + "\n",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "step_index": 1,
                "state": "DONE",
                "step_type": "agent_response",
                "text_delta": "Plan formed",
                "usage": {
                    "input_tokens": 24000,
                    "cache_read_tokens": 15000,
                    "output_tokens": 700,
                    "thinking_tokens": 0,
                    "cache_write_tokens": 0,
                    "total_tokens": 24700,  # agy omits cache_read_tokens
                },
            },
        }) + "\n",
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": session_id,
                "status": "SUCCESS",
                "response": "Done",
                "usage": {
                    "input_tokens": 120000,
                    "cache_read_tokens": 50000,
                    "output_tokens": 4000,
                    "total_tokens": 174000,  # Multi-step cumulative sum
                },
            },
        }) + "\n",
    ]

    worker = AntigravityWorker()
    cmd = worker.build_run_command(prompt="implement", session_id=None)
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(cmd, stdout_lines=stream_lines, exit_code=0)

    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    state_store = FakeStateStore()
    state_coord = StateCoordinator(state_store=state_store)
    status_pub = FakeStatusPublisher()

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        agent_worker=worker,
        state_coordinator=state_coord,
        status_publisher=status_pub,
    )

    result = asyncio.run(supervisor.run(ticket=ticket, prompt="implement"))

    # Expected context occupancy: 24000 (input) + 15000 (cache_read) + 700 (output) = 39700
    assert result.occupancy == 39700
    assert state_coord.current_state is not None
    assert state_coord.current_state.tokens.current == 39700
    assert len(status_pub.events) >= 1
    assert status_pub.events[-1].token_count == 39700
    assert status_pub.events[-1].last_event == "STEP_FINISHED"


def test_seam2_antigravity_tool_step_advances_stall_timer_without_tokens(
    tmp_path: Path,
) -> None:
    """Tool step_update events advance last_step_time even when token_usage is None."""
    session_id = "a1112222-3333-4444-5555-666677778888"
    ticket = _make_ticket("T123")
    simulated_clock = [100.0]

    def _clock() -> float:
        return simulated_clock[0]

    stream_lines = [
        json.dumps({"event": "init", "conversation_id": session_id}) + "\n",
        # Tool step without token usage
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "step_type": "tool",
                "state": "ACTIVE",
                "tool_info": {"name": "read_file", "parameters": {"path": "a.txt"}},
            },
        }) + "\n",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "step_type": "tool",
                "state": "DONE",
            },
        }) + "\n",
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": session_id,
                "status": "SUCCESS",
                "response": "Done",
            },
        }) + "\n",
    ]

    worker = AntigravityWorker()
    cmd = worker.build_run_command(prompt="implement", session_id=None)
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(cmd, stdout_lines=stream_lines, exit_code=0)

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        agent_worker=worker,
        clock=_clock,
        stall_timeout=60.0,
    )

    result = asyncio.run(supervisor.run(ticket=ticket, prompt="implement"))
    assert result.reason == RunTerminationReason.EXITED
    assert result.is_crash is False


def test_seam2_antigravity_active_tool_forwarded_to_ui_event_sink(
    tmp_path: Path,
) -> None:
    """Active Antigravity tool invocations are emitted to ui_event_sink."""
    session_id = "c7778888-9999-0000-1111-222233334444"
    ticket = _make_ticket("T123")
    stream_lines = [
        json.dumps({"event": "init", "conversation_id": session_id}) + "\n",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "step_type": "tool",
                "state": "ACTIVE",
                "tool_info": {
                    "name": "edit_file",
                    "parameters": {"path": "runner/application/gatekeeper.py"},
                },
            },
        }) + "\n",
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": session_id,
                "status": "SUCCESS",
                "response": "Done",
            },
        }) + "\n",
    ]

    class _FakeSink:
        def __init__(self) -> None:
            self.messages: list[tuple[str, str]] = []

        def emit(self, channel: str, message: str) -> None:
            self.messages.append((channel, message))

    fake_sink = _FakeSink()
    worker = AntigravityWorker()
    cmd = worker.build_run_command(prompt="implement", session_id=None)
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(cmd, stdout_lines=stream_lines, exit_code=0)

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        agent_worker=worker,
        ui_event_sink=fake_sink,  # type: ignore[arg-type]
    )

    asyncio.run(supervisor.run(ticket=ticket, prompt="implement"))
    assert len(fake_sink.messages) == 1
    channel, message = fake_sink.messages[0]
    assert channel == "worker"
    assert "edit_file" in message.lower()
    assert "runner/application/gatekeeper.py" in message


def test_seam2_antigravity_genuine_mid_turn_budget_escalation(
    tmp_path: Path,
) -> None:
    """Mid-turn context occupancy crossing 120k / 135k triggers WARN and HANDOFF when no ready signal exists."""
    session_id = "e5556666-7777-8888-9999-000011112222"
    ticket = _make_ticket("T123")
    stream_lines = [
        json.dumps({"event": "init", "conversation_id": session_id}) + "\n",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "state": "DONE",
                "usage": {"input_tokens": 120000, "output_tokens": 1500, "total_tokens": 121500},
            },
        }) + "\n",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "state": "DONE",
                "usage": {"input_tokens": 135000, "output_tokens": 1500, "total_tokens": 136500},
            },
        }) + "\n",
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": session_id,
                "status": "SUCCESS",
                "response": "Done",
            },
        }) + "\n",
    ]

    budget_actions: list[tuple[BudgetAction, int]] = []
    worker = AntigravityWorker()
    cmd = worker.build_run_command(prompt="implement", session_id=None)
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(cmd, stdout_lines=stream_lines, exit_code=0)

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        agent_worker=worker,
        on_budget_action=lambda action, occ: budget_actions.append((action, occ)),
    )

    asyncio.run(supervisor.run(ticket=ticket, prompt="implement"))
    assert (BudgetAction.WARN, 121500) in budget_actions
    assert (BudgetAction.HANDOFF, 136500) in budget_actions


def test_seam2_ready_signal_precedence_in_supervisor_and_handoff_coordinator(
    tmp_path: Path,
) -> None:
    """Valid ready signal on disk takes precedence over late budget kills in supervisor and run_cycle."""
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    ticket = _make_ticket("T123")
    ready_file = runtime_paths.ready_signal_path("T123")
    ready_file.write_text(
        json.dumps({
            "ticket_id": "T123",
            "status": "ready_for_verification",
            "modified_files": ["foo.py"],
            "self_review_notes": "All green",
            "new_gotchas": [],
            "timestamp": "2026-10-27T22:00:00Z",
        }),
        encoding="utf-8",
    )

    # 1. Verify WorkerSupervisor suppresses budget kills when ready signal is present
    session_id = "d8889999-0000-1111-2222-333344445555"
    stream_lines = [
        json.dumps({"event": "init", "conversation_id": session_id}) + "\n",
        json.dumps({
            "event": "step_update",
            "step_update": {
                "conversation_id": session_id,
                "state": "DONE",
                "usage": {"input_tokens": 151000, "output_tokens": 500, "total_tokens": 151500},
            },
        }) + "\n",
        json.dumps({
            "event": "result",
            "result": {
                "conversation_id": session_id,
                "status": "SUCCESS",
                "response": "Done",
            },
        }) + "\n",
    ]

    budget_actions: list[tuple[BudgetAction, int]] = []
    worker = AntigravityWorker()
    cmd = worker.build_run_command(prompt="implement", session_id=None)
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(cmd, stdout_lines=stream_lines, exit_code=0)

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        agent_worker=worker,
        on_budget_action=lambda action, occ: budget_actions.append((action, occ)),
    )

    sup_result = asyncio.run(supervisor.run(ticket=ticket, prompt="implement"))
    assert len(budget_actions) == 0
    assert sup_result.ready_signal_present is True
    assert sup_result.reason in (RunTerminationReason.EXITED, RunTerminationReason.KILLED_SIGNAL)

    # 2. Verify HandoffCoordinator.run_cycle yields SingleCycleStatus.READY directly
    from unittest.mock import AsyncMock

    mock_sup = AsyncMock()
    mock_sup.runtime_paths = runtime_paths
    mock_sup.cwd = tmp_path
    mock_sup.on_budget_action = None
    mock_sup.run.return_value = SessionRunResult(
        reason=RunTerminationReason.KILLED_CEILING,
        session_id=session_id,
        exit_code=0,
        occupancy=152000,
        ready_signal_present=True,
    )

    coordinator = HandoffCoordinator(
        supervisor=mock_sup,
        runtime_paths=runtime_paths,
        budget_config=TokenBudgetConfig(ceiling=150000),
    )

    cycle_result = asyncio.run(coordinator.run_cycle(ticket))
    assert cycle_result.status == SingleCycleStatus.READY
    assert cycle_result.ready_signal_present is True
    assert cycle_result.occupancy == 152000


# ==============================================================================
# Seam 3: Queue Ownership Guardrails & Idempotent Ticket Finalization
# ==============================================================================


def test_seam3_prompt_builder_forbids_queue_mutations_and_gotchas_direct_edits() -> None:
    """PromptBuilder prompt explicitly forbids mutating docs/tickets/ or editing gotchas.md directly."""
    ticket = _make_ticket("T123")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt="## Problem Statement\nSample\n\n## Solution\nSample",
        gotchas_path="docs/tickets/gotchas.md",
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "No Git Staging, Commits, or Queue File Mutations" in prompt
    assert "docs/tickets/gotchas.md" in prompt
    prompt_lower = prompt.lower()
    assert (
        "do not edit `docs/tickets/gotchas.md` directly" in prompt_lower
        or "do not edit docs/tickets/gotchas.md directly" in prompt_lower
    )
    assert (
        "modifying, moving, or deleting any ticket markdown file under `docs/tickets/`" in prompt_lower
        or "modify, move, or delete any ticket markdown file under `docs/tickets/`" in prompt_lower
    )


def test_seam3_directory_ticket_store_finalize_completed_idempotent(tmp_path: Path) -> None:
    """DirectoryTicketStore.finalize_completed handles pre-relocated ticket files idempotently."""
    spec_dir = tmp_path / "16-live-run"
    spec_dir.mkdir(parents=True, exist_ok=True)
    ticket_file = spec_dir / "T123-sample.md"
    ticket_file.write_text(
        "# T123 — Sample\nStatus: pending\n### Requirements\n- Must pass.\n",
        encoding="utf-8",
    )

    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)

    # Simulate worker prematurely moving ticket to completed/
    completed_dir = spec_dir / "completed"
    completed_dir.mkdir(parents=True, exist_ok=True)
    moved_file = completed_dir / "T123-sample.md"
    shutil.move(str(ticket_file), str(moved_file))

    store = DirectoryTicketStore(root_dir=tmp_path)
    dest = store.finalize_completed(ticket, completed_at="2026-10-27T22:30:00Z")

    assert dest == moved_file
    assert dest.is_file()
    assert (completed_dir / ".gitkeep").is_file()
    content = dest.read_text(encoding="utf-8")
    assert "Status: completed" in content
    assert "Completed: 2026-10-27T22:30:00Z" in content
