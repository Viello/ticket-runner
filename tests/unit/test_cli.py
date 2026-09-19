"""Unit tests for ticket_runner CLI entry point."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import signal
from typing import Any
import pytest

from runner.application.doctor import CheckResult, Doctor, DoctorReport
from runner.application.git_operations import GitOperations
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
)
from runner.application.worker_supervisor import WorkerSupervisor
from runner.domain.runtime_paths import RuntimePaths
from runner.adapters.markdown.file_lock import QueueFileLock
from runner.container import build_container
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    ModelConfig,
    ModelEntry,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.exceptions import StateFormatError
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_state_store import FakeStateStore
from tests.fakes.fake_ticket_repository import FakeTicketRepository
import ticket_runner


def _make_dummy_config(queue_completion: str = "standby") -> RunnerConfig:
    return RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion=queue_completion),
        git=GitConfig(),
    )


class FakeDoctorPassing(Doctor):
    def __init__(self, config: RunnerConfig | None = None) -> None:
        self.received_local_only: bool | None = None
        self._mock_config = config or _make_dummy_config()

    async def run(self, local_only: bool = False, halt_on_failure: bool = False) -> DoctorReport:
        self.received_local_only = local_only
        self._loaded_config = self._mock_config
        checks = [
            CheckResult(name="check_opencode", passed=True, message="OpenCode CLI available"),
            CheckResult(name="check_config", passed=True, message="Config valid"),
            CheckResult(name="check_queue", passed=True, message="Queue verified"),
        ]
        return DoctorReport(passed=True, checks=checks)


class FakeDoctorFailing(Doctor):
    def __init__(self) -> None:
        self.received_local_only: bool | None = None

    async def run(self, local_only: bool = False, halt_on_failure: bool = False) -> DoctorReport:
        self.received_local_only = local_only
        checks = [
            CheckResult(
                name="check_queue",
                passed=False,
                message="Queue validation failed: No pending tickets found in 'docs/tickets'.",
                remediation="Add pending tickets.",
            )
        ]
        return DoctorReport(passed=False, checks=checks)


def test_cli_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = ticket_runner.main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "usage: ticket_runner" in captured.out


def test_cli_placeholders_pause_and_status(capsys: pytest.CaptureFixture[str]) -> None:
    code_pause = ticket_runner.main(["pause"])
    assert code_pause == 0
    assert "not yet implemented" in capsys.readouterr().out

    code_status = ticket_runner.main(["status"])
    assert code_status == 0
    assert "not yet implemented" in capsys.readouterr().out


def test_cli_start_fails_when_doctor_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_doc = FakeDoctorFailing()
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 1
    assert fake_doc.received_local_only is True
    captured = capsys.readouterr()
    assert "Doctor pre-flight verification failed." in captured.out


def test_cli_start_threads_config_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received_config_path: Path | None = None

    def fake_doctor_factory(*args: Any, **kwargs: Any) -> Doctor:
        nonlocal received_config_path
        received_config_path = kwargs.get("config_path")
        return FakeDoctorFailing()

    monkeypatch.setattr(ticket_runner, "Doctor", fake_doctor_factory)

    code = ticket_runner.main(["start", "--config", "custom.yaml"])
    assert code == 1
    assert received_config_path == Path("custom.yaml")


def test_cli_start_with_pending_tickets_processes_through_container(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T001",
        title="Pending Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T001-pending.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "add", "."], stdout="")
    fake_runner.register(["git", "commit", "-m"], stdout="")
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="a" * 40 + "\n")
    fake_git_ops = GitOperations(runner=fake_runner)

    fake_container = build_container(
        dummy_config,
        ticket_store=ticket_repo,
        git_operations=fake_git_ops,
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Queue complete" in captured.out
    assert pending_ticket.status == TicketStatus.COMPLETED


def test_cli_start_aborted_by_operator_exits_with_code_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T001",
        title="Pending Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T001-pending.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    fake_container = build_container(
        dummy_config,
        ticket_store=ticket_repo,
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.aborted(details="Intervention abort")),
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 2
    captured = capsys.readouterr()
    assert "Aborted" in captured.out or "aborted" in captured.out.lower()
    assert pending_ticket.status == TicketStatus.PENDING


def test_cli_start_empty_queue_terminates_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    ticket_repo = FakeTicketRepository([])
    fake_container = build_container(dummy_config, ticket_store=ticket_repo, lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"))
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Queue complete" in captured.out or "all tickets completed" in captured.out


def test_cli_start_empty_queue_standby_with_injected_stop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="standby")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    ticket_repo = FakeTicketRepository([])
    fake_container = build_container(dummy_config, ticket_store=ticket_repo, lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"))
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    orchestrator = fake_container.orchestrator
    original_run_lifecycle = orchestrator.run_lifecycle

    async def patched_run_lifecycle(*args: Any, **kwargs: Any) -> int:
        kwargs["poll_interval"] = 0.01
        kwargs["max_standby_iterations"] = 1
        return await original_run_lifecycle(*args, **kwargs)

    monkeypatch.setattr(orchestrator, "run_lifecycle", patched_run_lifecycle)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 0
    captured = capsys.readouterr()
    assert "standby" in captured.out.lower()


def test_cli_run_start_passes_configured_poll_interval(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="standby")
    object.__setattr__(dummy_config.lifecycle, "poll_interval", 12.5)

    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    captured_poll_interval: float | None = None

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            nonlocal captured_poll_interval
            captured_poll_interval = kwargs.get("poll_interval")
            return 0

    fake_orch = FakeOrchestrator()
    code = asyncio.run(
        ticket_runner.run_start(
            config_path=tmp_path / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            orchestrator_instance=fake_orch,  # type: ignore[arg-type]
        )
    )
    assert code == 0
    assert captured_poll_interval == 12.5


def test_cli_run_start_honors_poll_interval_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="standby")
    object.__setattr__(dummy_config.lifecycle, "poll_interval", 12.5)

    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    captured_poll_interval: float | None = None

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            nonlocal captured_poll_interval
            captured_poll_interval = kwargs.get("poll_interval")
            return 0

    fake_orch = FakeOrchestrator()
    code = asyncio.run(
        ticket_runner.run_start(
            config_path=tmp_path / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            orchestrator_instance=fake_orch,  # type: ignore[arg-type]
            poll_interval=0.5,
        )
    )
    assert code == 0
    assert captured_poll_interval == 0.5


def test_cli_ctrl_c_during_standby_exits_cleanly_with_code_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="standby")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    ticket_repo = FakeTicketRepository([])
    lock = QueueFileLock(lock_path=tmp_path / ".queue.lock")
    fake_container = build_container(
        dummy_config,
        ticket_store=ticket_repo,
        lock=lock,
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    orchestrator = fake_container.orchestrator
    original_run_lifecycle = orchestrator.run_lifecycle

    async def patched_run_lifecycle(*args: Any, **kwargs: Any) -> int:
        stop_event = kwargs.get("stop_event")

        async def _interrupt_later() -> None:
            await asyncio.sleep(0.01)
            sig_handler = signal.getsignal(signal.SIGINT)
            if callable(sig_handler):
                sig_handler(signal.SIGINT, None)
            elif stop_event is not None:
                stop_event.set()

        asyncio.create_task(_interrupt_later())
        return await original_run_lifecycle(*args, **kwargs)

    monkeypatch.setattr(orchestrator, "run_lifecycle", patched_run_lifecycle)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 130
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "Traceback" not in captured.out
    assert lock.is_locked is False


def test_cli_ctrl_c_mid_worker_terminates_active_worker_and_exits_130(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T040",
        title="Mid-Worker Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T040-mid.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    lock = QueueFileLock(lock_path=tmp_path / ".queue.lock")

    fake_runner = FakeCommandRunner()
    handle = fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "test prompt"],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": "ses_t040"})],
        delay=2.0,
    )
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        async def _interrupt_later() -> None:
            await asyncio.sleep(0.01)
            sig_handler = signal.getsignal(signal.SIGINT)
            if callable(sig_handler):
                sig_handler(signal.SIGINT, None)

        asyncio.create_task(_interrupt_later())
        await supervisor.run(ticket=ticket, prompt="test prompt")
        return TicketOutcome.approved()

    fake_container = build_container(
        dummy_config,
        ticket_store=ticket_repo,
        lock=lock,
        supervisor=supervisor,
        processor=fake_processor,
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 130
    assert handle.terminated is True
    assert handle.closed is True
    assert lock.is_locked is False


def test_cli_second_ctrl_c_during_shutdown_force_kills_with_130(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="standby")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    fake_container = build_container(
        dummy_config,
        ticket_store=FakeTicketRepository([]),
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    orchestrator = fake_container.orchestrator

    async def patched_run_lifecycle(*args: Any, **kwargs: Any) -> int:
        sig_handler = signal.getsignal(signal.SIGINT)
        assert callable(sig_handler)
        # First Ctrl+C: starts graceful shutdown
        sig_handler(signal.SIGINT, None)
        # Second Ctrl+C: must trigger immediate sys.exit(130)
        with pytest.raises(SystemExit) as exc_info:
            sig_handler(signal.SIGINT, None)
        assert exc_info.value.code == 130
        return 130

    monkeypatch.setattr(orchestrator, "run_lifecycle", patched_run_lifecycle)
    code = ticket_runner.main(["start", "--local-only"])
    assert code == 130


def test_cli_main_catches_keyboard_interrupt_returns_130(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_doc = FakeDoctorPassing()
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    def raise_keyboard_interrupt(*args: Any, **kwargs: Any) -> Any:
        raise KeyboardInterrupt()

    monkeypatch.setattr(ticket_runner, "run_start", raise_keyboard_interrupt)
    code = ticket_runner.main(["start", "--local-only"])
    assert code == 130


# --- T041: CLI Exit Code Contract and Summary Tests ---

def test_cli_help_documents_exit_code_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = ticket_runner.main([])
    assert code == 0
    captured = capsys.readouterr()
    assert "Exit codes:" in captured.out
    assert "0" in captured.out
    assert "1" in captured.out
    assert "2" in captured.out
    assert "130" in captured.out
    assert "Clean termination" in captured.out
    assert "Runtime error" in captured.out
    assert "Operator abort" in captured.out
    assert "SIGINT" in captured.out


def test_cli_start_prints_completion_summary_on_clean_terminate(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T041",
        title="Summary Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T041-summary.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    fake_runner.register(["git", "add", "."], stdout="")
    fake_runner.register(["git", "commit", "-m"], stdout="")
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="c" * 40 + "\n")
    fake_git_ops = GitOperations(runner=fake_runner)

    fake_container = build_container(
        dummy_config,
        ticket_store=ticket_repo,
        git_operations=fake_git_ops,
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Completion Summary" in captured.out
    assert "Tickets processed: 1 (1 approved, 0 skipped, 0 aborted)" in captured.out
    assert "Commits authored: ccccccc" in captured.out
    assert "Working branch: agent/ticket-runner" in captured.out
    assert "Elapsed time:" in captured.out


def test_cli_start_runtime_error_returns_code_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T001",
        title="Failing Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T001-fail.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    fake_container = build_container(
        dummy_config,
        ticket_store=ticket_repo,
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
        processor=lambda t: (_ for _ in ()).throw(RuntimeError("Unexpected pipeline fault")),
    )
    monkeypatch.setattr(ticket_runner, "build_container", lambda *args, **kwargs: fake_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 1
    captured = capsys.readouterr()
    assert "error" in captured.out.lower() or "error" in captured.err.lower()


def test_cli_parser_has_model_on_start_only() -> None:
    parser = ticket_runner.create_parser()

    args = parser.parse_args(["start", "--model", "qwen/qwen-plus"])
    assert args.model == "qwen/qwen-plus"

    args_default = parser.parse_args(["start"])
    assert args_default.model is None

    # --model must NOT exist on doctor command
    with pytest.raises(SystemExit):
        parser.parse_args(["doctor", "--model", "qwen/qwen-plus"])


def test_cli_start_with_valid_model_builds_container_with_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion="terminate"),
        git=GitConfig(),
        model=ModelConfig(
            models=(
                ModelEntry(id="qwen/qwen-plus", label="Qwen Plus"),
                ModelEntry(id="anthropic/claude-3-5-sonnet", label="Claude 3.5 Sonnet"),
            )
        ),
    )
    fake_doc = FakeDoctorPassing(config=config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T001",
        title="Pending Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T001-pending.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "add", "."], stdout="")
    fake_runner.register(["git", "commit", "-m"], stdout="")
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="a" * 40 + "\n")
    fake_git_ops = GitOperations(runner=fake_runner)

    fake_container = build_container(
        config,
        ticket_store=ticket_repo,
        git_operations=fake_git_ops,
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    fake_state_store = FakeStateStore(initial_state={"prior_key": "prior_val"})
    monkeypatch.setattr(ticket_runner, "JsonStateStore", lambda path: fake_state_store)

    passed_kwargs: dict[str, Any] = {}

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        passed_kwargs.update(kwargs)
        return fake_container

    monkeypatch.setattr(ticket_runner, "build_container", mock_build_container)

    code = ticket_runner.main(["start", "--local-only", "--model", "qwen/qwen-plus"])
    assert code == 0
    assert passed_kwargs.get("model_id") == "qwen/qwen-plus"
    assert fake_state_store.write_calls[-1]["prior_key"] == "prior_val"
    assert fake_state_store.write_calls[-1]["selected_model"] == "qwen/qwen-plus"


def test_cli_start_with_unknown_model_prints_error_and_exits_1_without_orchestrating(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion="terminate"),
        git=GitConfig(),
        model=ModelConfig(
            models=(
                ModelEntry(id="qwen/qwen-plus", label="Qwen Plus"),
                ModelEntry(id="anthropic/claude-3-5-sonnet", label="Claude 3.5 Sonnet"),
            )
        ),
    )
    fake_doc = FakeDoctorPassing(config=config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    build_container_called = False

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        nonlocal build_container_called
        build_container_called = True
        raise AssertionError("build_container should not be called when model validation fails")

    monkeypatch.setattr(ticket_runner, "build_container", mock_build_container)

    code = ticket_runner.main(["start", "--local-only", "--model", "bogus"])
    assert code == 1
    assert build_container_called is False

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "qwen/qwen-plus" in output
    assert "anthropic/claude-3-5-sonnet" in output
    assert "bogus" in output


def test_cli_start_omitting_model_passes_none_model_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    pending_ticket = Ticket(
        id="T001",
        title="Pending Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=Path("docs/tickets/test/T001-pending.md"),
    )
    ticket_repo = FakeTicketRepository([pending_ticket])
    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "add", "."], stdout="")
    fake_runner.register(["git", "commit", "-m"], stdout="")
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="a" * 40 + "\n")
    fake_git_ops = GitOperations(runner=fake_runner)

    fake_container = build_container(
        config,
        ticket_store=ticket_repo,
        git_operations=fake_git_ops,
        lock=QueueFileLock(lock_path=tmp_path / ".queue.lock"),
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    passed_kwargs: dict[str, Any] = {}

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        passed_kwargs.update(kwargs)
        return fake_container

    monkeypatch.setattr(ticket_runner, "build_container", mock_build_container)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 0
    assert passed_kwargs.get("model_id") is None


def test_cli_run_start_single_model_auto_selects_and_persists(
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(models=(ModelEntry(id="single/model", label="Single Model"),)),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore()

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            return 0

    code = asyncio.run(
        ticket_runner.run_start(
            config_path=tmp_path / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            orchestrator_instance=FakeOrchestrator(),  # type: ignore[arg-type]
            state_store=store,
        )
    )
    assert code == 0


def test_cli_run_start_multiple_models_interactive_selection(
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(
            models=(
                ModelEntry(id="m1/chat", label="M1 Chat"),
                ModelEntry(id="m2/chat", label="M2 Chat"),
            )
        ),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore()
    keys = ["2", "\r"]
    key_iter = iter(keys)

    passed_kwargs: dict[str, Any] = {}

    class ContainerDouble:
        orchestrator: Any = None
        supervisor: Any = None

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            return 0

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        passed_kwargs.update(kwargs)
        container = ContainerDouble()
        container.orchestrator = FakeOrchestrator()
        return container

    import unittest.mock as mock

    with mock.patch.object(ticket_runner, "build_container", mock_build_container):
        code = asyncio.run(
            ticket_runner.run_start(
                config_path=tmp_path / "config.yaml",
                local_only=True,
                doctor_instance=fake_doc,
                state_store=store,
                key_reader=lambda: next(key_iter),
            )
        )

    assert code == 0
    assert passed_kwargs.get("model_id") == "m2/chat"
    assert store.write_calls[-1]["selected_model"] == "m2/chat"


def test_cli_run_start_restores_from_state_and_prints_notice(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(
            models=(
                ModelEntry(id="m1/chat", label="M1 Chat"),
                ModelEntry(id="m2/chat", label="M2 Chat"),
            )
        ),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore(initial_state={"selected_model": "m2/chat", "custom": "field"})

    passed_kwargs: dict[str, Any] = {}

    class ContainerDouble:
        orchestrator: Any = None
        supervisor: Any = None

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            return 0

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        passed_kwargs.update(kwargs)
        container = ContainerDouble()
        container.orchestrator = FakeOrchestrator()
        return container

    import unittest.mock as mock

    with mock.patch.object(ticket_runner, "build_container", mock_build_container):
        code = asyncio.run(
            ticket_runner.run_start(
                config_path=tmp_path / "config.yaml",
                local_only=True,
                doctor_instance=fake_doc,
                state_store=store,
            )
        )

    assert code == 0
    assert passed_kwargs.get("model_id") == "m2/chat"
    assert store.write_calls[-1]["custom"] == "field"
    captured = capsys.readouterr()
    assert "Resuming with M2 Chat — pass --model to override" in captured.out


def test_cli_run_start_drift_warns_and_falls_back(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(models=(ModelEntry(id="single/model", label="Single Model"),)),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore(initial_state={"selected_model": "departed/model"})

    passed_kwargs: dict[str, Any] = {}

    class ContainerDouble:
        orchestrator: Any = None
        supervisor: Any = None

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            return 0

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        passed_kwargs.update(kwargs)
        container = ContainerDouble()
        container.orchestrator = FakeOrchestrator()
        return container

    import unittest.mock as mock

    with mock.patch.object(ticket_runner, "build_container", mock_build_container):
        code = asyncio.run(
            ticket_runner.run_start(
                config_path=tmp_path / "config.yaml",
                local_only=True,
                doctor_instance=fake_doc,
                state_store=store,
            )
        )

    assert code == 0
    assert passed_kwargs.get("model_id") == "single/model"
    captured = capsys.readouterr()
    assert "departed/model" in captured.out
    assert store.write_calls[-1]["selected_model"] == "single/model"


def test_cli_run_start_non_interactive_exits_1_with_model_message(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(
            models=(
                ModelEntry(id="m1/chat", label="M1 Chat"),
                ModelEntry(id="m2/chat", label="M2 Chat"),
            )
        ),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore()

    code = asyncio.run(
        ticket_runner.run_start(
            config_path=tmp_path / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            state_store=store,
            key_reader=lambda: "",  # EOF / non-interactive
        )
    )

    assert code == 1
    captured = capsys.readouterr()
    assert "--model" in captured.out or "--model" in captured.err


def test_cli_run_start_state_write_failure_exits_1_before_container_build(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(models=(ModelEntry(id="single/model", label="Single Model"),)),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore(write_error=OSError("Permission denied on write"))

    build_called = False

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        nonlocal build_called
        build_called = True
        raise AssertionError("Should not build container on write failure")

    import unittest.mock as mock

    with mock.patch.object(ticket_runner, "build_container", mock_build_container):
        code = asyncio.run(
            ticket_runner.run_start(
                config_path=tmp_path / "config.yaml",
                local_only=True,
                doctor_instance=fake_doc,
                state_store=store,
            )
        )

    assert code == 1
    assert build_called is False
    captured = capsys.readouterr()
    assert "persistence failed" in captured.out.lower() or "permission denied" in captured.out.lower()


def test_cli_run_start_corrupt_state_warns_and_persists_cleanly(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _make_dummy_config(queue_completion="terminate")
    object.__setattr__(
        config,
        "model",
        ModelConfig(models=(ModelEntry(id="single/model", label="Single Model"),)),
    )
    fake_doc = FakeDoctorPassing(config=config)
    store = FakeStateStore(read_error=StateFormatError("Malformed state file"))

    passed_kwargs: dict[str, Any] = {}

    class ContainerDouble:
        orchestrator: Any = None
        supervisor: Any = None

    class FakeOrchestrator:
        async def run_lifecycle(self, *args: Any, **kwargs: Any) -> int:
            return 0

    def mock_build_container(*args: Any, **kwargs: Any) -> Any:
        passed_kwargs.update(kwargs)
        container = ContainerDouble()
        container.orchestrator = FakeOrchestrator()
        return container

    import unittest.mock as mock

    with mock.patch.object(ticket_runner, "build_container", mock_build_container):
        code = asyncio.run(
            ticket_runner.run_start(
                config_path=tmp_path / "config.yaml",
                local_only=True,
                doctor_instance=fake_doc,
                state_store=store,
            )
        )

    assert code == 0
    assert passed_kwargs.get("model_id") == "single/model"
    captured = capsys.readouterr()
    assert "corrupted" in captured.out.lower()
    assert store.write_calls[-1] == {"selected_model": "single/model"}


