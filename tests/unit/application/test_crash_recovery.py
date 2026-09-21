"""Unit tests for CrashRecoveryCoordinator application service."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import pytest

from runner.application.crash_recovery import (
    CrashRecoveryCoordinator,
    RecoveryResult,
)
from runner.application.git_operations import GitOperations
from runner.application.state_coordinator import StateCoordinator
from runner.application.worker_supervisor import (
    RunTerminationReason,
    SessionRunResult,
    WorkerSupervisor,
)
from runner.domain.exceptions import GitError, StateFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.state import RunnerState, StateStatus, TokenState
from runner.domain.ticket import Ticket
from runner.ports.command_runner import CommandResult, ProcessHandle
from runner.ports.state_store import StateStore
from tests.fakes.fake_state_store import FakeStateStore


def _sample_active_state_dict(
    ticket_id: str = "T042",
    status: str = "WORKING",
    opencode_session_id: str | None = "ses_abc123",
    tui_open: bool = False,
    tui_session_id: str | None = None,
    **overrides: object,
) -> dict[str, object]:
    base: dict[str, object] = {
        "active_ticket_id": ticket_id,
        "status": status,
        "opencode_session_id": opencode_session_id,
        "selected_model": "test/model",
        "presence_mode": "nearby",
        "verification_attempts": 0,
        "tokens": {
            "current": 10000,
            "warning_sent": False,
        },
        "branch": "agent/ticket-runner",
        "started_at": "2026-09-19T10:00:00+00:00",
        "last_checkpoint": None,
        "tui_open": tui_open,
        "tui_session_id": tui_session_id,
        "last_updated": "2026-09-19T10:05:00+00:00",
    }
    base.update(overrides)
    return base


class FakeCommandRunner:
    """Fake CommandRunner supporting status_porcelain and other git calls."""

    def __init__(self, porcelain_output: str = "") -> None:
        self.porcelain_output = porcelain_output
        self.run_calls: list[list[str]] = []

    async def run(
        self,
        command: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        self.run_calls.append(list(command))
        cmd_str = " ".join(command)
        if "status --porcelain" in cmd_str:
            return CommandResult(exit_code=0, stdout=self.porcelain_output, stderr="")
        if "rev-parse --abbrev-ref HEAD" in cmd_str:
            return CommandResult(exit_code=0, stdout="agent/ticket-runner\n", stderr="")
        return CommandResult(exit_code=0, stdout="", stderr="")

    async def spawn(
        self,
        command: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessHandle:
        raise NotImplementedError()


class FakeWorkerSupervisor:
    """Fake WorkerSupervisor recording run calls."""

    def __init__(
        self,
        results: list[SessionRunResult] | None = None,
        exception_to_raise: Exception | None = None,
    ) -> None:
        self.results = list(results) if results is not None else [
            SessionRunResult(
                reason=RunTerminationReason.EXITED,
                session_id="ses_abc123",
                exit_code=0,
            )
        ]
        self.exception_to_raise = exception_to_raise
        self.run_calls: list[dict[str, Any]] = []
        self.budget_monitor_reset = False

    def reset_budget_monitor(self) -> None:
        self.budget_monitor_reset = True

    async def run(
        self,
        ticket: Ticket | str,
        prompt: str,
        session_id: str | None = None,
        bounded: bool = False,
    ) -> SessionRunResult:
        self.run_calls.append({
            "ticket": ticket,
            "prompt": prompt,
            "session_id": session_id,
            "bounded": bounded,
        })
        if self.exception_to_raise is not None:
            raise self.exception_to_raise
        if self.results:
            return self.results.pop(0)
        return SessionRunResult(
            reason=RunTerminationReason.EXITED,
            session_id=session_id or "ses_new_b",
            exit_code=0,
        )


def test_recover_absent_state_file_does_nothing(tmp_path: Path) -> None:
    store = FakeStateStore(None)
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
    )

    result = asyncio.run(coordinator.recover())

    assert not result.recovered
    assert result.action == "none"
    assert len(supervisor.run_calls) == 0
    assert len(cmd_runner.run_calls) == 0


def test_recover_idle_state_does_nothing(tmp_path: Path) -> None:
    idle_dict = _sample_active_state_dict(ticket_id=None, status="IDLE", opencode_session_id=None)
    idle_dict["active_ticket_id"] = None
    store = FakeStateStore(idle_dict)
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
    )

    result = asyncio.run(coordinator.recover())

    assert not result.recovered
    assert result.action == "none"
    assert len(supervisor.run_calls) == 0


def test_recover_inactive_circuit_breaker_tripped_does_nothing(tmp_path: Path) -> None:
    cb_dict = _sample_active_state_dict(status="CIRCUIT_BREAKER_TRIPPED")
    store = FakeStateStore(cb_dict)
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
    )

    result = asyncio.run(coordinator.recover())

    assert not result.recovered
    assert result.action == "none"
    assert len(supervisor.run_calls) == 0


def test_recover_corrupted_state_file_quarantines_and_initializes_clean(tmp_path: Path) -> None:
    state_file = tmp_path / ".agent" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{corrupt json", encoding="utf-8")

    from runner.adapters.filesystem.json_state_store import JsonStateStore
    store = JsonStateStore(path=state_file)
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    logs: list[str] = []
    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
        printer=logs.append,
    )

    result = asyncio.run(coordinator.recover())

    assert not result.recovered
    assert result.action == "quarantined"
    assert result.quarantine_path is not None
    assert result.quarantine_path.is_file()
    assert "state.json.corrupt." in result.quarantine_path.name
    assert result.quarantine_path.read_text(encoding="utf-8") == "{corrupt json"
    assert not state_file.read_text(encoding="utf-8").startswith("{corrupt")

    # Verify a clean state document was initialized
    clean_data = json.loads(state_file.read_text(encoding="utf-8"))
    assert clean_data["status"] == "IDLE"
    assert clean_data["active_ticket_id"] is None
    assert any("corrupted" in log.lower() or "quarantined" in log.lower() for log in logs)


def test_recover_startup_state_with_only_selected_model_does_not_quarantine(tmp_path: Path) -> None:
    state_file = tmp_path / ".agent" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text('{"selected_model": "opencode/nemotron-3.5-lightning-free"}', encoding="utf-8")

    from runner.adapters.filesystem.json_state_store import JsonStateStore
    store = JsonStateStore(path=state_file)
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    logs: list[str] = []
    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
        printer=logs.append,
    )

    result = asyncio.run(coordinator.recover())

    assert not result.recovered
    assert result.action == "none"
    assert result.quarantine_path is None
    assert not any("corrupt" in p.name for p in state_file.parent.iterdir())
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted.get("selected_model") == "opencode/nemotron-3.5-lightning-free"


def test_recover_startup_state_with_state_coordinator_initializes_idle_and_preserves_model(tmp_path: Path) -> None:
    state_file = tmp_path / ".agent" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text('{"selected_model": "opencode/nemotron-3.5-lightning-free"}', encoding="utf-8")

    from runner.adapters.filesystem.json_state_store import JsonStateStore
    store = JsonStateStore(path=state_file)
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()
    state_coord = StateCoordinator(state_store=store, branch="agent/ticket-runner")

    logs: list[str] = []
    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
        state_coordinator=state_coord,
        printer=logs.append,
    )

    result = asyncio.run(coordinator.recover())

    assert not result.recovered
    assert result.action == "none"
    assert result.quarantine_path is None
    persisted = json.loads(state_file.read_text(encoding="utf-8"))
    assert persisted.get("selected_model") == "opencode/nemotron-3.5-lightning-free"
    assert persisted.get("status") == "IDLE"
    assert persisted.get("active_ticket_id") is None




def test_recover_clean_git_tree_successful_session_resumption(tmp_path: Path) -> None:
    active_dict = _sample_active_state_dict(ticket_id="T042", opencode_session_id="ses_abc123")
    store = FakeStateStore(active_dict)
    cmd_runner = FakeCommandRunner(porcelain_output="")
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor([
        SessionRunResult(
            reason=RunTerminationReason.EXITED,
            session_id="ses_abc123",
            exit_code=0,
        )
    ])

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
    )

    result = asyncio.run(coordinator.recover())

    assert result.recovered
    assert result.action == "resumed_session"
    assert result.ticket_id == "T042"
    assert result.session_id == "ses_abc123"
    assert result.uncommitted_files == ()

    assert len(supervisor.run_calls) == 1
    call = supervisor.run_calls[0]
    assert call["session_id"] == "ses_abc123"
    assert call["prompt"] == "Resuming session after restart. Continue implementation for ticket T042."


def test_recover_dirty_git_tree_preserves_uncommitted_and_includes_files_in_prompt(tmp_path: Path) -> None:
    active_dict = _sample_active_state_dict(ticket_id="T042", opencode_session_id="ses_abc123")
    store = FakeStateStore(active_dict)
    porcelain = (
        " M runner/application/crash_recovery.py\n"
        "?? tests/unit/application/test_crash_recovery.py\n"
        "?? .agent/state.json\n"
        "?? __pycache__/something.pyc\n"
        "?? dist/package.tar.gz\n"
    )
    cmd_runner = FakeCommandRunner(porcelain_output=porcelain)
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor([
        SessionRunResult(
            reason=RunTerminationReason.EXITED,
            session_id="ses_abc123",
            exit_code=0,
        )
    ])

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
    )

    result = asyncio.run(coordinator.recover())

    assert result.recovered
    assert result.action == "resumed_session"
    assert result.ticket_id == "T042"
    # Verify .agent/ and build artifacts are filtered out
    assert result.uncommitted_files == (
        "runner/application/crash_recovery.py",
        "tests/unit/application/test_crash_recovery.py",
    )

    # Never reset working tree
    assert not any("reset" in " ".join(c) for c in cmd_runner.run_calls)
    assert not any("clean" in " ".join(c) for c in cmd_runner.run_calls)

    assert len(supervisor.run_calls) == 1
    call = supervisor.run_calls[0]
    expected_prompt = (
        "Resuming session after restart. Uncommitted edits detected in: "
        "runner/application/crash_recovery.py, tests/unit/application/test_crash_recovery.py. "
        "Continue implementation for ticket T042."
    )
    assert call["prompt"] == expected_prompt
    assert call["session_id"] == "ses_abc123"


def test_recover_crashed_tui_logs_warning_and_resets_state(tmp_path: Path) -> None:
    active_dict = _sample_active_state_dict(
        ticket_id="T042",
        opencode_session_id="ses_abc123",
        tui_open=True,
        tui_session_id="tui_sess_999",
    )
    store = FakeStateStore(active_dict)
    cmd_runner = FakeCommandRunner(porcelain_output="")
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    logs: list[str] = []
    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
        printer=logs.append,
    )

    result = asyncio.run(coordinator.recover())

    assert result.recovered
    assert result.warning_logged

    expected_warning = (
        "Runner exited while TUI session was open (session: tui_sess_999). "
        "TUI may still be running. Resuming managed execution."
    )
    assert any(expected_warning in log for log in logs)

    # Verify state was saved with tui_open=False, tui_session_id=None
    persisted = store.read()
    assert persisted is not None
    assert persisted["tui_open"] is False
    assert persisted["tui_session_id"] is None


def test_recover_failed_session_resumption_triggers_checkpoint_fallback_session_b(tmp_path: Path) -> None:
    active_dict = _sample_active_state_dict(ticket_id="T042", opencode_session_id="ses_old_crashed")
    store = FakeStateStore(active_dict)
    cmd_runner = FakeCommandRunner(porcelain_output="")
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)

    # Create checkpoint file
    checkpoint_dir = tmp_path / ".agent" / "checkpoints" / "T042"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    handoff_file = checkpoint_dir / "handoff.md"
    handoff_file.write_text("# Checkpoint Context\nWork in progress\n", encoding="utf-8")

    # First run fails (crash / rejection); second run (Session B) succeeds
    failed_run = SessionRunResult(
        reason=RunTerminationReason.EXITED,
        session_id="ses_old_crashed",
        exit_code=1,
        has_error_event=True,
    )
    success_b_run = SessionRunResult(
        reason=RunTerminationReason.EXITED,
        session_id="ses_session_b",
        exit_code=0,
    )
    supervisor = FakeWorkerSupervisor(results=[failed_run, success_b_run])

    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
        runtime_paths=runtime_paths,
    )

    result = asyncio.run(coordinator.recover())

    assert result.recovered
    assert result.action == "resumed_checkpoint"
    assert result.ticket_id == "T042"
    assert result.session_id == "ses_session_b"
    assert supervisor.budget_monitor_reset

    assert len(supervisor.run_calls) == 2
    # 1. Attempted resumption on old session
    assert supervisor.run_calls[0]["session_id"] == "ses_old_crashed"
    # 2. Resumed with fresh session (Session B) and checkpoint prompt
    assert supervisor.run_calls[1]["session_id"] is None
    expected_b_prompt = (
        f"Read the context handoff document at `{handoff_file.as_posix()}`, "
        f"inspect `git status`, then continue working on ticket T042."
    )
    assert supervisor.run_calls[1]["prompt"] == expected_b_prompt

    # State was updated with new session ID
    persisted = store.read()
    assert persisted is not None
    assert persisted["opencode_session_id"] == "ses_session_b"


@pytest.mark.parametrize("status", ["WORKING", "GATEKEEPER", "WAITING_FOR_USER", "PAUSE_REQUESTED"])
def test_recover_handles_all_active_work_statuses(tmp_path: Path, status: str) -> None:
    active_dict = _sample_active_state_dict(ticket_id="T042", status=status, opencode_session_id="ses_test")
    store = FakeStateStore(active_dict)
    cmd_runner = FakeCommandRunner(porcelain_output="")
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
    )

    result = asyncio.run(coordinator.recover())
    assert result.recovered
    assert result.action == "resumed_session"
    assert len(supervisor.run_calls) == 1


def test_runner_container_wires_crash_recovery(tmp_path: Path) -> None:
    from runner.container import build_container
    container = build_container(cwd=tmp_path)
    assert hasattr(container, "crash_recovery")
    assert isinstance(container.crash_recovery, CrashRecoveryCoordinator)


def test_run_start_invokes_crash_recovery(tmp_path: Path) -> None:
    import ticket_runner
    from runner.domain.config import (
        ModelConfig,
        ModelEntry,
        ProjectConfig,
        RunnerConfig,
        WorkerConfig,
        VerificationConfig,
        TokenBudgetConfig,
        PresenceConfig,
        DiscordConfig,
        LifecycleConfig,
        GitConfig,
    )

    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion="terminate"),
        git=GitConfig(),
        model=ModelConfig(models=(ModelEntry(id="test/model", label="Test Model"),)),
    )

    class FakeDoctor:
        def __init__(self) -> None:
            self.loaded_config = config
        async def run(self, *args: Any, **kwargs: Any) -> Any:
            from runner.application.doctor import DoctorReport
            return DoctorReport(checks=(), passed=True)

    recovered_called = False

    class FakeRecoveryCoordinator:
        async def recover(self) -> RecoveryResult:
            nonlocal recovered_called
            recovered_called = True
            return RecoveryResult(action="none", recovered=False)

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            return 0

    class FakeContainer:
        def __init__(self) -> None:
            self.orchestrator = FakeOrchestrator()
            self.supervisor = FakeWorkerSupervisor()
            self.crash_recovery = FakeRecoveryCoordinator()

    code = asyncio.run(
        ticket_runner.run_start(
            config_path=tmp_path / "config.yaml",
            local_only=True,
            doctor_instance=FakeDoctor(),
            container_instance=FakeContainer(),
        )
    )

    assert code == 0
    assert recovered_called


def test_recover_completed_ticket_resets_state_to_idle(tmp_path: Path) -> None:
    from tests.fakes.fake_ticket_repository import FakeTicketRepository
    from runner.domain.ticket import Ticket, TicketStatus

    completed_ticket = Ticket(
        id="T042",
        title="Completed ticket",
        status=TicketStatus.COMPLETED,
        spec_path="docs/specs/test.md",
        requirements=(),
        acceptance_criteria=(),
        gotchas=(),
        path=tmp_path / "completed" / "T042-test.md",
    )
    ticket_store = FakeTicketRepository([completed_ticket])

    store = FakeStateStore(_sample_active_state_dict(ticket_id="T042", status="WORKING"))
    cmd_runner = FakeCommandRunner()
    git_ops = GitOperations(runner=cmd_runner, cwd=tmp_path)
    supervisor = FakeWorkerSupervisor()
    printed: list[str] = []

    coordinator = CrashRecoveryCoordinator(
        state_store=store,
        git_operations=git_ops,
        worker_supervisor=supervisor,
        ticket_store=ticket_store,
        printer=printed.append,
    )

    result = asyncio.run(coordinator.recover())

    assert result.action == "none"
    assert result.recovered is False
    assert len(supervisor.run_calls) == 0

    state = store.read()
    assert state is not None
    assert state["status"] == "IDLE"
    assert state["active_ticket_id"] is None
    assert any("already completed" in m for m in printed)

