"""Unit tests for structured diagnostic report and escalation in VerificationLoop (T066)."""

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
from runner.domain.exceptions import NonInteractiveError
from runner.domain.failure_analyser import FailureDiagnostic, LABEL_HANG
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_intervention import FakeInterventionGateway


def _make_ready_signal(ticket_id: str = "T066") -> ReadySignal:
    from datetime import datetime, timezone
    return ReadySignal(
        ticket_id=ticket_id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("foo.py",),
        self_review_notes="Implemented feature.",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
    )


def _make_ticket(ticket_id: str = "T066") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Diagnostic Escalation Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/10-stuck-detection-and-observability.md",
        requirements=("Escalate failed verification.",),
        acceptance_criteria=("Escalates with diagnostic report.",),
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


class _SpyDiscordAdapter:
    def __init__(self, should_raise: bool = False) -> None:
        self.sent_messages: list[str] = []
        self._should_raise = should_raise

    def send(self, message: str) -> None:
        if self._should_raise:
            raise RuntimeError("Discord network error")
        self.sent_messages.append(message)


def _make_failed_report(tail: str = "FAILED test_fail.py::test_one") -> VerificationReport:
    outcome = CommandOutcome(
        label="test",
        command="pytest",
        exit_code=1,
        timed_out=False,
        tail=tail,
    )
    return VerificationReport(
        passed=False,
        results=(outcome,),
        diagnostics=("$ pytest\nexit code 1\n" + tail,),
        skipped_commands=(),
    )


@pytest.mark.anyio
async def test_escalation_at_attempt_1_operator_answers_yes() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, occupancy=42150),
    ])
    signal_repo = _StubSignalRepo([_make_ready_signal(ticket.id)])
    executor = _StubExecutor([_make_failed_report()])
    intervention_gateway = FakeInterventionGateway(escalation_answers=[True])
    discord_adapter = _SpyDiscordAdapter()

    custom_diag = FailureDiagnostic(
        label=LABEL_HANG,
        root_tests=["test_fail.py::test_one"],
        top_errors=["TimeoutError"],
        log_tail=["FAILED test_fail.py::test_one"],
        isolation_output=None,
        suggested_action="Run /diagnosing-bugs",
    )

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(test_cmd="pytest", bug_escalation_at=1),
        failure_analyser=lambda **kwargs: custom_diag,
        discord_adapter=discord_adapter,
        token_budget=150000,
    )

    result = await loop.run()

    # 1. Yields INTERVENTION_REQUESTED with FailureDiagnostic attached
    assert result.status == VerificationLoopStatus.INTERVENTION_REQUESTED
    assert result.is_intervention_requested is True
    assert result.failure_diagnostic == custom_diag

    # 2. Attempt counter must NOT be incremented (gotcha: does not consume a retry attempt)
    assert result.attempts == 0
    assert loop.attempts == 0

    # 3. Discord send was called
    assert len(discord_adapter.sent_messages) == 1
    assert "⚠ HANG detected — test_fail.py::test_one" in discord_adapter.sent_messages[0]

    # 4. Terminal prompt received the report
    assert len(intervention_gateway.escalation_records) == 1
    prompted_ticket, report = intervention_gateway.escalation_records[0]
    assert prompted_ticket == ticket
    assert "Run /diagnosing-bugs? [Y/n]" in report
    assert "Token budget: 42,150 / 150,000" in report


@pytest.mark.anyio
async def test_escalation_at_attempt_1_operator_answers_no(tmp_path: Path) -> None:
    ticket = _make_ticket()
    # Attempt 1 fails, operator answers No. Attempt 2 passes.
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, occupancy=1000),
        WorkerRunResult(status=SingleCycleStatus.READY, occupancy=2000),
    ])
    signal_repo = _StubSignalRepo([
        _make_ready_signal(ticket.id),
        _make_ready_signal(ticket.id),
    ])
    executor = _StubExecutor([
        _make_failed_report(),
        VerificationReport(
            passed=True,
            results=(CommandOutcome(label="test", command="pytest", exit_code=0, timed_out=False, tail=""),),
            diagnostics=(),
            skipped_commands=(),
        ),
    ])
    intervention_gateway = FakeInterventionGateway(escalation_answers=[False])
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(test_cmd="pytest", bug_escalation_at=1),
        runtime_paths=runtime_paths,
    )

    result = await loop.run()

    # Loop resumed and passed on attempt 2
    assert result.status == VerificationLoopStatus.PASSED
    assert result.attempts == 2

    # Diagnostic was written to .agent/logs/<ticket_id>_diagnostic.md
    diag_file = runtime_paths.diagnostic_log_path(ticket.id)
    assert diag_file.exists()
    content = diag_file.read_text(encoding="utf-8")
    assert "detected — " in content
    assert "Top errors: " in content
    assert "--- last 100 lines ---" in content


@pytest.mark.anyio
async def test_escalation_non_interactive_logs_and_resumes(tmp_path: Path) -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY),
        WorkerRunResult(status=SingleCycleStatus.READY),
    ])
    signal_repo = _StubSignalRepo([
        _make_ready_signal(ticket.id),
        _make_ready_signal(ticket.id),
    ])
    executor = _StubExecutor([
        _make_failed_report(),
        VerificationReport(
            passed=True,
            results=(CommandOutcome(label="test", command="pytest", exit_code=0, timed_out=False, tail=""),),
            diagnostics=(),
            skipped_commands=(),
        ),
    ])
    # Gateway raises NonInteractiveError on prompt_escalation
    intervention_gateway = FakeInterventionGateway(
        escalation_answers=[NonInteractiveError("No TTY")]
    )
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(test_cmd="pytest", bug_escalation_at=1),
        runtime_paths=runtime_paths,
    )

    result = await loop.run()
    assert result.status == VerificationLoopStatus.PASSED
    diag_file = runtime_paths.diagnostic_log_path(ticket.id)
    assert diag_file.exists()


@pytest.mark.anyio
async def test_escalation_at_minus_one_escalates_only_on_circuit_breaker() -> None:
    ticket = _make_ticket()
    # 3 attempts configured, all 3 fail.
    # Attempts 1 and 2 must produce NO escalation prompt.
    # Attempt 3 must trigger escalation prompt.
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY),
        WorkerRunResult(status=SingleCycleStatus.READY),
        WorkerRunResult(status=SingleCycleStatus.READY),
    ])
    signal_repo = _StubSignalRepo([
        _make_ready_signal(ticket.id),
        _make_ready_signal(ticket.id),
        _make_ready_signal(ticket.id),
    ])
    executor = _StubExecutor([
        _make_failed_report(),
        _make_failed_report(),
        _make_failed_report(),
    ])
    intervention_gateway = FakeInterventionGateway(escalation_answers=[True])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(
            test_cmd="pytest",
            max_attempts=3,
            bug_escalation_at=-1,
        ),
    )

    result = await loop.run()
    assert result.status == VerificationLoopStatus.INTERVENTION_REQUESTED
    # Prompt only fired once, on attempt 3
    assert len(intervention_gateway.escalation_records) == 1
    assert result.attempts == 2  # not incremented on attempt 3


@pytest.mark.anyio
async def test_escalation_at_zero_never_escalates() -> None:
    ticket = _make_ticket()
    # 2 attempts, both fail, circuit breaker trips and operator selects skip
    cycle_runner = _StubCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY),
        WorkerRunResult(status=SingleCycleStatus.READY),
    ])
    signal_repo = _StubSignalRepo([
        _make_ready_signal(ticket.id),
        _make_ready_signal(ticket.id),
    ])
    executor = _StubExecutor([
        _make_failed_report(),
        _make_failed_report(),
    ])
    # Circuit breaker decision is skip
    intervention_gateway = FakeInterventionGateway(
        decisions=["skip"],
        escalation_answers=[True],  # Should never be called!
    )

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(
            test_cmd="pytest",
            max_attempts=2,
            bug_escalation_at=0,
        ),
    )

    result = await loop.run()
    assert result.status == VerificationLoopStatus.SKIPPED
    # No escalation prompt was ever shown
    assert len(intervention_gateway.escalation_records) == 0


@pytest.mark.anyio
async def test_discord_adapter_exception_never_raises() -> None:
    ticket = _make_ticket()
    cycle_runner = _StubCycleRunner([WorkerRunResult(status=SingleCycleStatus.READY)])
    signal_repo = _StubSignalRepo([_make_ready_signal(ticket.id)])
    executor = _StubExecutor([_make_failed_report()])
    intervention_gateway = FakeInterventionGateway(escalation_answers=[True])
    raising_discord = _SpyDiscordAdapter(should_raise=True)

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=intervention_gateway,
        verification_config=VerificationConfig(test_cmd="pytest", bug_escalation_at=1),
        discord_adapter=raising_discord,
    )

    # Must not raise an exception despite Discord failure
    result = await loop.run()
    assert result.status == VerificationLoopStatus.INTERVENTION_REQUESTED
