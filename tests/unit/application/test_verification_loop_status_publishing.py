"""Unit tests for StatusPublisher integration in VerificationLoop (T067)."""

from __future__ import annotations

from pathlib import Path
import pytest

from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationLoop,
    VerificationLoopResult,
    VerificationLoopStatus,
    VerificationReport,
)
from runner.application.handoff_coordinator import (
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.domain.config import VerificationConfig
from runner.domain.failure_analyser import FailureDiagnostic, LABEL_HANG
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal, SignalStatus
from runner.domain.status_event import RunState
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_intervention import FakeInterventionGateway
from tests.fakes.fake_status_publisher import FakeStatusPublisher


def _make_ready_signal(ticket_id: str = "T067") -> ReadySignal:
    from datetime import datetime, timezone
    return ReadySignal(
        ticket_id=ticket_id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("foo.py",),
        self_review_notes="Implemented feature.",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
    )


def _make_ticket(ticket_id: str = "T067") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Status Event File Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/10-stuck-detection-and-observability.md",
        requirements=("Publish status events.",),
        acceptance_criteria=("Publishes ATTEMPT_STARTED, ATTEMPT_ENDED, ESCALATION_EMITTED, CIRCUIT_BREAKER_TRIPPED.",),
        gotchas=(),
        path=Path(f"docs/tickets/10-stuck-detection-and-observability/{ticket_id}.md"),
    )


class _StubCycleRunner:
    def __init__(self, responses: list[WorkerRunResult]) -> None:
        self._responses = list(responses)

    async def __call__(self, ticket: Ticket, **kwargs) -> WorkerRunResult:
        return self._responses.pop(0)


class _StubSignalRepo:
    def __init__(self, ready_signals: list[ReadySignal | None]) -> None:
        self._ready_signals = list(ready_signals)
        self.consumed: list[str] = []

    def read_ready(self, ticket_id: str) -> ReadySignal | None:
        if not self._ready_signals:
            return None
        return self._ready_signals.pop(0)

    def consume_ready(self, ticket_id: str) -> None:
        self.consumed.append(ticket_id)

    def read_pending_question(self, ticket_id: str) -> None:
        return None

    def clean_question(self, ticket_id: str) -> None:
        pass


class _StubExecutor:
    def __init__(self, reports: list[VerificationReport]) -> None:
        self._reports = list(reports)

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        return self._reports.pop(0)


def _make_failed_report() -> VerificationReport:
    return VerificationReport(
        passed=False,
        results=(
            CommandOutcome(
                label="test",
                command="pytest",
                exit_code=1,
                timed_out=False,
                tail="FAILED test_something.py",
            ),
        ),
        diagnostics=("FAILED test_something.py",),
        skipped_commands=(),
    )


@pytest.mark.anyio
async def test_status_publisher_attempt_started_and_ended_on_pass() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, occupancy=10000),
    ])
    signal_repo = _StubSignalRepo([_make_ready_signal(ticket.id)])
    executor = _StubExecutor([
        VerificationReport(
            passed=True,
            results=(CommandOutcome(label="test", command="pytest", exit_code=0, timed_out=False, tail=""),),
            diagnostics=(),
            skipped_commands=(),
        ),
    ])
    publisher = FakeStatusPublisher()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        verification_config=VerificationConfig(test_cmd="pytest"),
        status_publisher=publisher,
    )

    result = await loop.run()
    assert result.status == VerificationLoopStatus.PASSED

    # Assert ATTEMPT_STARTED and ATTEMPT_ENDED were published
    event_names = [e.last_event for e in publisher.events]
    assert "ATTEMPT_STARTED" in event_names
    assert "ATTEMPT_ENDED" in event_names

    start_event = next(e for e in publisher.events if e.last_event == "ATTEMPT_STARTED")
    assert start_event.ticket_id == ticket.id
    assert start_event.run_state == RunState.VERIFYING
    assert start_event.attempt == 1

    end_event = next(e for e in publisher.events if e.last_event == "ATTEMPT_ENDED")
    assert end_event.ticket_id == ticket.id
    assert end_event.run_state == RunState.DONE
    assert end_event.attempt == 1


@pytest.mark.anyio
async def test_status_publisher_escalation_emitted() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, occupancy=20000),
    ])
    signal_repo = _StubSignalRepo([_make_ready_signal(ticket.id)])
    executor = _StubExecutor([_make_failed_report()])
    intervention_gateway = FakeInterventionGateway(escalation_answers=[True])
    publisher = FakeStatusPublisher()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(test_cmd="pytest", bug_escalation_at=1),
        status_publisher=publisher,
    )

    result = await loop.run()
    assert result.status == VerificationLoopStatus.INTERVENTION_REQUESTED

    event_names = [e.last_event for e in publisher.events]
    assert "ATTEMPT_STARTED" in event_names
    assert "ESCALATION_EMITTED" in event_names

    esc_event = next(e for e in publisher.events if e.last_event == "ESCALATION_EMITTED")
    assert esc_event.ticket_id == ticket.id
    assert esc_event.run_state == RunState.ESCALATING
    assert esc_event.attempt == 1


@pytest.mark.anyio
async def test_status_publisher_circuit_breaker_tripped() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, occupancy=5000),
    ])
    signal_repo = _StubSignalRepo([_make_ready_signal(ticket.id)])
    executor = _StubExecutor([_make_failed_report()])
    intervention_gateway = FakeInterventionGateway(
        decisions=["abort"],
        escalation_answers=[False],
    )
    publisher = FakeStatusPublisher()

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(test_cmd="pytest", max_attempts=1, bug_escalation_at=0),
        status_publisher=publisher,
    )

    from runner.domain.exceptions import UserAbortError
    with pytest.raises(UserAbortError):
        await loop.run()

    event_names = [e.last_event for e in publisher.events]
    assert "CIRCUIT_BREAKER_TRIPPED" in event_names

    cb_event = next(e for e in publisher.events if e.last_event == "CIRCUIT_BREAKER_TRIPPED")
    assert cb_event.ticket_id == ticket.id
    assert cb_event.attempt == 1
