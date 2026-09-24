"""Unit tests for Gatekeeper Human Approval Mode Integration (Spec 13, T109)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import pytest

from runner.application.gatekeeper import (
    CommandOutcome,
    VerificationLoop,
    VerificationLoopResult,
    VerificationLoopStatus,
    VerificationReport,
)
from runner.application.handoff_coordinator import (
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.domain.config import LifecycleConfig, VerificationConfig
from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.domain.exceptions import ConfigError, UserAbortError
from runner.domain.signal import ReadySignal
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_approval_gateway import FakeApprovalGateway
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_intervention import FakeInterventionGateway
from tests.fakes.fake_signal_repository import FakeSignalRepository


def _make_ticket(ticket_id: str = "T109") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Gatekeeper Human Approval Mode Integration",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/13-token-guarded-verification-and-human-gate.md",
        requirements=("Implement human approval mode in VerificationLoop.",),
        acceptance_criteria=("Evidence card dispatched and decision respected.",),
        gotchas=(),
        path=Path(f"docs/tickets/13-token-guarded-verification-and-human-gate/{ticket_id}-test.md"),
    )


class _StubCycleRunner:
    """Configurable test double for worker cycle runs."""

    def __init__(
        self,
        responses: list[WorkerRunResult | Exception],
        on_call: Any | None = None,
    ) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self._on_call = on_call

    async def __call__(
        self,
        ticket: Ticket,
        *,
        session_id: str | None = None,
        prompt: str | None = None,
    ) -> WorkerRunResult:
        self.calls.append({"ticket": ticket, "session_id": session_id, "prompt": prompt})
        if self._on_call is not None:
            self._on_call(ticket, len(self.calls))
        if not self._responses:
            raise AssertionError("StubCycleRunner called with no responses remaining")
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


class _StubExecutor:
    """Configurable test double for Gatekeeper command verification."""

    def __init__(self, reports: list[VerificationReport]) -> None:
        self._reports = list(reports)
        self.calls: list[VerificationConfig] = []

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        self.calls.append(config)
        if not self._reports:
            raise AssertionError("StubExecutor called with no reports remaining")
        return self._reports.pop(0)


def _passing_report(cmd: str = "pytest -q") -> VerificationReport:
    outcome = CommandOutcome(
        label="test",
        command=cmd,
        exit_code=0,
        timed_out=False,
        tail="1 passed in 0.01s",
    )
    return VerificationReport(
        passed=True,
        results=(outcome,),
        diagnostics=(),
        skipped_commands=(),
    )


def _make_ready_signal(ticket_id: str = "T109") -> ReadySignal:
    return ReadySignal.parse(
        {
            "ticket_id": ticket_id,
            "status": "ready_for_verification",
            "modified_files": ["runner/application/gatekeeper.py"],
            "self_review_notes": "Implemented human approval mode",
            "new_gotchas": [],
            "timestamp": "2026-09-24T12:00:00Z",
            "scope": "gatekeeper",
            "manual_verification": [
                {
                    "name": "Human mode pauses and collects approval",
                    "setup": "Set approval_mode: human",
                    "steps": "Run loop and check card",
                    "expected": "Card received and approval requested",
                    "auto_covered": True,
                },
            ],
        },
        expected_ticket_id=ticket_id,
    )


class _MockTuiCoordinator:
    def __init__(self) -> None:
        self.launched_sessions: list[str | None] = []

    async def launch_tui(self, session_id: str | None = None) -> None:
        self.launched_sessions.append(session_id)


# --- LifecycleConfig validation tests ---


def test_lifecycle_config_approval_mode_default_is_autonomous() -> None:
    cfg = LifecycleConfig()
    assert cfg.approval_mode == "autonomous"


def test_lifecycle_config_approval_mode_human_valid() -> None:
    cfg = LifecycleConfig(approval_mode="human")
    assert cfg.approval_mode == "human"


def test_lifecycle_config_approval_mode_invalid_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="Lifecycle approval_mode must be one of"):
        LifecycleConfig(approval_mode="invalid")


# --- VerificationLoop Human Approval Mode tests ---


def test_human_mode_dispatches_evidence_card_and_passes_on_approve() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
    ])
    executor = _StubExecutor([_passing_report()])
    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket.id))
    gateway = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=gateway,
        approval_mode="human",
    )

    result = asyncio.run(loop.run())

    assert result.is_passed
    assert result.approval_decision == ApprovalDecision.APPROVE
    assert len(gateway.received_cards) == 1
    card = gateway.received_cards[0]
    assert card.ticket_id == ticket.id
    assert card.test_status == "passed"


def test_autonomous_mode_bypasses_approval_gateway() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
    ])
    executor = _StubExecutor([_passing_report()])
    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket.id))
    gateway = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=gateway,
        approval_mode="autonomous",
    )

    result = asyncio.run(loop.run())

    assert result.is_passed
    # In autonomous mode, approval gateway is never consulted
    assert len(gateway.received_cards) == 0


def test_human_mode_reject_loops_back_to_worker_with_bounded_hint() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
    ])
    executor = _StubExecutor([_passing_report(), _passing_report()])
    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket.id))
    # First cycle: REJECT with reason; Second cycle: APPROVE
    reject_decision = ApprovalDecision.REJECT.with_reason("Fix the typo in the error message")
    gateway = FakeApprovalGateway(decisions=[reject_decision, ApprovalDecision.APPROVE])

    # On second cycle, make sure ready signal is available again
    def _repopulate_signal(t: Ticket, call_count: int) -> None:
        if call_count == 2:
            signal_repo.seed_ready(_make_ready_signal(t.id))

    cycle_runner._on_call = _repopulate_signal

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=gateway,
        approval_mode="human",
    )

    result = asyncio.run(loop.run())

    assert result.is_passed
    assert result.approval_decision == ApprovalDecision.APPROVE
    assert len(gateway.received_cards) == 2
    # Verify retry prompt contains the rejection reason
    assert len(cycle_runner.calls) == 2
    retry_prompt = cycle_runner.calls[1]["prompt"]
    assert retry_prompt is not None
    assert "Fix the typo in the error message" in retry_prompt


def test_human_mode_diagnose_triggers_diagnostic_session() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
    ])
    executor = _StubExecutor([_passing_report(), _passing_report()])
    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket.id))
    gateway = FakeApprovalGateway(decisions=[ApprovalDecision.DIAGNOSE, ApprovalDecision.APPROVE])
    tui_coord = _MockTuiCoordinator()

    def _repopulate_signal(t: Ticket, call_count: int) -> None:
        if call_count == 2:
            signal_repo.seed_ready(_make_ready_signal(t.id))

    cycle_runner._on_call = _repopulate_signal

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=gateway,
        approval_mode="human",
        tui_coordinator=tui_coord,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed
    assert len(tui_coord.launched_sessions) == 1
    assert tui_coord.launched_sessions[0] == "sess-1"


def test_human_mode_fails_closed_when_gateway_missing() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
    ])
    executor = _StubExecutor([_passing_report()])
    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket.id))

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=None,  # Missing in human mode
        approval_mode="human",
    )

    with pytest.raises(UserAbortError, match="Fail-closed"):
        asyncio.run(loop.run())


def test_human_mode_fails_closed_on_unhandled_decision() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-1"),
    ])
    executor = _StubExecutor([_passing_report()])
    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket.id))

    # Custom gateway returning unexpected/unhandled decision
    class _BogusGateway:
        async def request_approval(self, card: EvidenceCard) -> Any:
            return "SOMETHING_INVALID"

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=_BogusGateway(),  # type: ignore[arg-type]
        approval_mode="human",
    )

    with pytest.raises(UserAbortError, match="Fail-closed"):
        asyncio.run(loop.run())


def test_rejection_reason_bounded_and_sanitized() -> None:
    from runner.application.gatekeeper import _format_rejection_hint

    # Very long string
    long_reason = "X" * 2000
    hint = _format_rejection_hint(long_reason)
    assert len(hint) <= 600
    assert "..." in hint

    # Secret / credential masking
    secret_reason = "Found token=secret_abc12345 in output"
    hint2 = _format_rejection_hint(secret_reason)
    assert "secret_abc12345" not in hint2
    assert "[REDACTED]" in hint2
