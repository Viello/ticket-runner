"""Unit tests for VerificationLoop manual verification surfacing (T069)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from runner.application.gatekeeper import (
    CommandOutcome,
    VerificationLoop,
    VerificationReport,
)
from runner.application.handoff_coordinator import (
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.domain.config import VerificationConfig
from runner.domain.exceptions import SignalFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_intervention import FakeInterventionGateway


def _make_ticket(ticket_id: str = "T069") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Smoke Scenarios Surfacing",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/10-stuck-detection-and-observability.md",
        requirements=("Surfacing manual verification in gatekeeper",),
        acceptance_criteria=("Full checklist on pass",),
        gotchas=(),
        path=Path(f"docs/tickets/10-stuck-detection-and-observability/{ticket_id}-test.md"),
    )


def _passing_report(cmd: str = "pytest -q") -> VerificationReport:
    outcome = CommandOutcome(
        label="test", command=cmd, exit_code=0, timed_out=False, tail="1 passed"
    )
    return VerificationReport(
        passed=True, results=(outcome,), diagnostics=(), skipped_commands=()
    )


class _StubCycleRunner:
    def __init__(self, response: WorkerRunResult) -> None:
        self._response = response

    async def __call__(
        self,
        ticket: Ticket,
        *,
        session_id: str | None = None,
        prompt: str | None = None,
    ) -> WorkerRunResult:
        return self._response


class _StubExecutor:
    def __init__(self, report: VerificationReport) -> None:
        self._report = report

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        return self._report


class _StubSignalRepo:
    def __init__(self, signal: ReadySignal | None) -> None:
        self._signal = signal
        self.consumed = False

    def read_ready(self, ticket_id: str) -> ReadySignal | None:
        return self._signal

    def consume_ready(self, ticket_id: str) -> None:
        self.consumed = True

    def read_pending_question(self, ticket_id: str) -> Any:
        return None

    def clean_question(self, ticket_id: str) -> None:
        pass


@pytest.fixture
def sample_scenarios() -> tuple[dict[str, str], ...]:
    return (
        {
            "name": "Full terminal checklist verification",
            "setup": "Start terminal UI in test harness",
            "steps": "1. Run runner\n2. Wait for gatekeeper pass",
            "expected": "Checklist is printed with full details",
        },
        {
            "name": "Discord summary verification",
            "setup": "Configure fake discord adapter",
            "steps": "1. Trigger pass\n2. Check adapter calls",
            "expected": "Discord summary received with scenario names",
        },
    )


@pytest.fixture
def mixed_scenarios() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "Auto-covered scenario",
            "setup": "Auto-covered setup",
            "steps": "1. Run auto test",
            "expected": "Auto test passes",
            "auto_covered": True,
            "update_notes": "Updates: T001 — Old scenario name",
        },
        {
            "name": "Manual-only scenario",
            "setup": "Manual setup",
            "steps": "1. Verify manually",
            "expected": "Manual verification passes",
            "auto_covered": False,
            "update_notes": "",
        },
    )


def test_absent_manual_verification_backward_compatible():
    """A ReadySignal payload without manual_verification parses with () and emits nothing."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        # manual_verification defaults to ()
    )
    assert ready.manual_verification == ()
    assert ready.manual_verification_is_default is True

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    notified: list[str] = []
    mock_discord = MagicMock()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        notify=notified.append,
        discord_adapter=mock_discord,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    # Nothing emitted for absent manual_verification
    assert not notified
    mock_discord.send.assert_not_called()


def test_empty_manual_verification_logs_warning():
    """When manual_verification is present but empty, emit a warning log and no user notification."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=(),
        _manual_verification_was_present=True,
    )
    assert not ready.manual_verification_is_default

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    notified: list[str] = []
    mock_discord = MagicMock()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        notify=notified.append,
        discord_adapter=mock_discord,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    # Empty manual_verification => warning only, no user-visible notification
    assert len(notified) == 0
    mock_discord.send.assert_not_called()


def test_populated_manual_verification_terminal_output(sample_scenarios):
    """When manual_verification contains scenarios, print full Setup/Steps/Expected verbatim."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    notified: list[str] = []

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        notify=notified.append,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    combined_output = "\n".join(notified)
    for s in sample_scenarios:
        assert f"Scenario: {s['name']}" in combined_output
        assert f"Setup: {s['setup']}" in combined_output
        assert f"Steps: {s['steps']}" in combined_output
        assert f"Expected: {s['expected']}" in combined_output


def test_populated_manual_verification_discord_summary(sample_scenarios):
    """Discord receives names-only summary in the specified bullet format."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    mock_discord = MagicMock()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        discord_adapter=mock_discord,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    mock_discord.send.assert_called_once()
    discord_msg = mock_discord.send.call_args[0][0]
    assert "✅ Gatekeeper passed — manual verification required:" in discord_msg
    assert "• Full terminal checklist verification" in discord_msg
    assert "• Discord summary verification" in discord_msg
    # No Setup/Steps/Expected details in Discord summary
    assert "Start terminal UI in test harness" not in discord_msg


def test_populated_manual_verification_commit_body_injection(sample_scenarios):
    """Commit body includes 'Manual verification required:' and one bullet per scenario name."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    mock_git = MagicMock()
    mock_git.commit_ticket = AsyncMock(return_value="commit_sha_123")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        git_operations=mock_git,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    mock_git.commit_ticket.assert_called_once()
    _, kwargs = mock_git.commit_ticket.call_args
    changes = kwargs.get("changes") or mock_git.commit_ticket.call_args[0][2]
    assert "Manual verification required:" in changes
    assert "- Full terminal checklist verification" in changes
    assert "- Discord summary verification" in changes


def test_missing_git_operations_logs_warning_and_does_not_block_pass(sample_scenarios, caplog):
    """When git_operations is None, loop logs warning and passes successfully."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        git_operations=None,
    )

    with caplog.at_level("WARNING"):
        res = asyncio.run(loop.run())
    assert res.is_passed
    assert any("GitOperations not provided to VerificationLoop" in r.message for r in caplog.records)


def test_missing_or_failing_discord_adapter_never_raises(sample_scenarios):
    """Missing or failing Discord adapter logs a warning and does not raise."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )

    # Failing discord adapter
    failing_discord = MagicMock()
    failing_discord.send.side_effect = RuntimeError("Discord connection refused")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        discord_adapter=failing_discord,
    )

    # Should not raise
    res = asyncio.run(loop.run())
    assert res.is_passed


def test_signal_format_error_on_malformed_manual_verification():
    """Non-dict entries or non-string values raise SignalFormatError."""
    payload_bad_entry = {
        "ticket_id": "T069",
        "status": "ready_for_verification",
        "modified_files": ["foo.py"],
        "self_review_notes": "ok",
        "new_gotchas": [],
        "timestamp": "2026-09-21T00:00:00+00:00",
        "manual_verification": ["not-a-dict"],
    }
    with pytest.raises(SignalFormatError):
        ReadySignal.parse(payload_bad_entry, "T069")

    payload_bad_type = {
        "ticket_id": "T069",
        "status": "ready_for_verification",
        "modified_files": ["foo.py"],
        "self_review_notes": "ok",
        "new_gotchas": [],
        "timestamp": "2026-09-21T00:00:00+00:00",
        "manual_verification": [{"name": 123}],
    }
    with pytest.raises(SignalFormatError):
        ReadySignal.parse(payload_bad_type, "T069")


def test_manual_verification_sanitization():
    """Embedded newlines, carriage returns, and ANSI escape sequences are stripped."""
    payload = {
        "ticket_id": "T069",
        "status": "ready_for_verification",
        "modified_files": ["foo.py"],
        "self_review_notes": "ok",
        "new_gotchas": [],
        "timestamp": "2026-09-21T00:00:00+00:00",
        "manual_verification": [
            {
                "name": "Scenario\r\nName\x1b[31mRed\x1b[0m",
                "setup": "Line1\nLine2",
                "steps": "Step",
                "expected": "Pass",
            }
        ],
    }
    signal = ReadySignal.parse(payload, "T069")
    entry = signal.manual_verification[0]
    assert "\r" not in entry["name"]
    assert "\n" not in entry["name"]
    assert "\x1b" not in entry["name"]
    assert "Scenario NameRed" in entry["name"]


def test_auto_covered_tag_in_terminal_output(mixed_scenarios: tuple[dict[str, Any], ...]) -> None:
    """Assert terminal output contains 'Auto-covered scenario [also auto-covered]' while manual-only line has no tag."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=mixed_scenarios,
        _manual_verification_was_present=True,
    )
    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    notified: list[str] = []

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        notify=notified.append,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    combined_output = "\n".join(notified)
    assert "Scenario: Auto-covered scenario [also auto-covered]" in combined_output
    assert "Scenario: Manual-only scenario" in combined_output
    assert "Manual-only scenario [also auto-covered]" not in combined_output


def test_auto_covered_tag_in_discord_bullets(mixed_scenarios: tuple[dict[str, Any], ...]) -> None:
    """Assert Discord send call contains '• Auto-covered scenario [also auto-covered]'."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=mixed_scenarios,
        _manual_verification_was_present=True,
    )
    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    mock_discord = MagicMock()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        discord_adapter=mock_discord,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    mock_discord.send.assert_called_once()
    discord_msg = mock_discord.send.call_args[0][0]
    assert "• Auto-covered scenario [also auto-covered]" in discord_msg
    assert "• Manual-only scenario" in discord_msg
    assert "Manual-only scenario [also auto-covered]" not in discord_msg


def test_smoke_log_appended_after_pass(
    mixed_scenarios: tuple[dict[str, Any], ...],
    tmp_path: Path,
) -> None:
    """Verify .agent/smoke_log_test-spec.md is created with header, auto-covered scenario, and update notes."""
    ticket = _make_ticket("T078")
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        scope="test-spec",
        manual_verification=mixed_scenarios,
        _manual_verification_was_present=True,
    )
    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        runtime_paths=runtime_paths,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    log_path = runtime_paths.smoke_log_path("test-spec")
    assert log_path == tmp_path / ".agent" / "smoke_log_test-spec.md"
    assert log_path.exists()

    content = log_path.read_text(encoding="utf-8")
    assert "# Smoke Log — test-spec" in content
    assert "### Auto-covered scenario [also auto-covered]" in content
    assert "> Updates: T001 — Old scenario name" in content
    assert "### Manual-only scenario" in content
    assert "Manual-only scenario [also auto-covered]" not in content

