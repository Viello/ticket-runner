"""Unit tests for ticket_runner CLI entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import pytest

from runner.application.doctor import CheckResult, Doctor, DoctorReport
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
)
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
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner
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


def test_cli_start_with_pending_tickets_and_no_processor_reports_spec_04(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_doc = FakeDoctorPassing()
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
    orchestrator = QueueOrchestrator(ticket_store=ticket_repo, processor=None)
    monkeypatch.setattr(ticket_runner, "QueueOrchestrator", lambda *args, **kwargs: orchestrator)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 1
    captured = capsys.readouterr()
    assert "Worker execution will arrive in Spec 03" not in captured.out
    assert "Spec 04" in captured.out
    # Repository was untouched
    assert pending_ticket.status == TicketStatus.PENDING


def test_cli_start_empty_queue_terminates_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dummy_config = _make_dummy_config(queue_completion="terminate")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    ticket_repo = FakeTicketRepository([])
    orchestrator = QueueOrchestrator(ticket_store=ticket_repo)
    monkeypatch.setattr(ticket_runner, "QueueOrchestrator", lambda *args, **kwargs: orchestrator)

    code = ticket_runner.main(["start", "--local-only"])
    assert code == 0
    captured = capsys.readouterr()
    assert "Queue complete" in captured.out or "all tickets completed" in captured.out


def test_cli_start_empty_queue_standby_with_injected_stop(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dummy_config = _make_dummy_config(queue_completion="standby")
    fake_doc = FakeDoctorPassing(config=dummy_config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    ticket_repo = FakeTicketRepository([])
    orchestrator = QueueOrchestrator(ticket_store=ticket_repo)
    monkeypatch.setattr(ticket_runner, "QueueOrchestrator", lambda *args, **kwargs: orchestrator)

    # Inject max_standby_iterations=1 so standby exits after 1 check
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
