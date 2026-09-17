"""Unit tests for VerificationLoop and Circuit Breaker use case (T031)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationLoop,
    VerificationLoopResult,
    VerificationLoopStatus,
    VerificationReport,
    build_verification_failure_prompt,
)
from runner.application.handoff_coordinator import (
    EscalationNotice,
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
    TicketOutcomeStatus,
)
from runner.domain.config import VerificationConfig
from runner.domain.exceptions import SignalFormatError, UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.command_runner import CommandRunner
from runner.ports.intervention import (
    InterventionAction,
    InterventionDecision,
    InterventionGateway,
)
from runner.ports.signal_repository import SignalRepository
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_ticket_repository import FakeTicketRepository
from tests.fakes.fake_intervention import FakeInterventionGateway


def _make_ticket(ticket_id: str = "T031") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Verification Loop Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/04-signal-protocol-and-gatekeeper.md",
        requirements=("Implement verification loop.",),
        acceptance_criteria=("Verification loop passes and handles circuit breaker.",),
        gotchas=(),
        path=Path(f"docs/tickets/04-signal-protocol-and-gatekeeper/{ticket_id}-test.md"),
    )


class _StubCycleRunner:
    """Configurable test double for worker cycle runs."""

    def __init__(
        self,
        responses: list[WorkerRunResult | Exception],
        on_call: Callable[[Ticket, int], None] | None = None,
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
    outcome = CommandOutcome(label="test", command=cmd, exit_code=0, timed_out=False, tail="1 passed")
    return VerificationReport(passed=True, results=(outcome,), diagnostics=(), skipped_commands=())


def _failing_report(cmd: str = "pytest -q", tail: str = "FAILED test_x - AssertionError") -> VerificationReport:
    outcome = CommandOutcome(label="test", command=cmd, exit_code=1, timed_out=False, tail=tail)
    diagnostic = f"$ {cmd}\nexit code 1\n{tail}"
    return VerificationReport(passed=False, results=(outcome,), diagnostics=(diagnostic,), skipped_commands=())


def _ready_signal_payload(ticket_id: str = "T031") -> str:
    return (
        f'{{\n'
        f'  "ticket_id": "{ticket_id}",\n'
        f'  "status": "ready_for_verification",\n'
        f'  "modified_files": ["runner/application/gatekeeper.py"],\n'
        f'  "self_review_notes": "Implemented verification loop.",\n'
        f'  "new_gotchas": [],\n'
        f'  "timestamp": "2026-09-17T00:00:00+00:00"\n'
        f'}}'
    )


# --- Tests ---


def test_failing_verification_resumes_with_diagnostics_tail_and_passes_next_cycle(tmp_path: Path) -> None:
    """A failing verification resumes with diagnostics containing the tail and passes on the next cycle."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    # Pre-author ready signal for attempt 1
    runtime_paths.ready_signal_path(ticket.id).write_text(_ready_signal_payload(ticket.id), encoding="utf-8")

    # In attempt 2, author ready signal again (since attempt 1 consumed it)
    def _on_call(t: Ticket, call_count: int) -> None:
        if call_count == 2:
            runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_active"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_active"),
        ],
        on_call=_on_call,
    )

    executor = _StubExecutor([
        _failing_report(tail="FAILED test_core.py::test_bar - assertion failed"),
        _passing_report(),
    ])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed is True
    assert result.status == VerificationLoopStatus.PASSED
    assert result.attempts == 2
    assert len(cycle_runner.calls) == 2

    # Check that resume prompt carried the failure tail and active session ID was preserved
    resume_call = cycle_runner.calls[1]
    assert resume_call["session_id"] == "ses_active"
    assert "FAILED test_core.py::test_bar - assertion failed" in resume_call["prompt"]
    assert "exit code 1" in resume_call["prompt"]


def test_malformed_ready_signal_consumes_attempt_with_format_error_diagnostics(tmp_path: Path) -> None:
    """A malformed ready Signal consumes an attempt with the format error as diagnostics."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    # Author invalid JSON for ready signal
    runtime_paths.ready_signal_path(ticket.id).write_text("NOT VALID JSON", encoding="utf-8")

    def _on_call(t: Ticket, call_count: int) -> None:
        if call_count == 2:
            runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
        ],
        on_call=_on_call,
    )

    executor = _StubExecutor([_passing_report()])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed is True
    assert result.attempts == 2
    assert len(cycle_runner.calls) == 2

    # Format error was injected into prompt on attempt 2
    resume_prompt = cycle_runner.calls[1]["prompt"]
    assert "Malformed ready Signal" in resume_prompt or "Signal file" in resume_prompt


def test_worker_phase_non_ready_consumes_attempt_with_escalation_details(tmp_path: Path) -> None:
    """A worker-phase non-READY status consumes an attempt with escalation details."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    escalation = EscalationNotice(
        ticket_id=ticket.id,
        reason="STALLED",
        session_id="ses_stalled",
        message="Process silence for 30s",
    )

    def _on_call(t: Ticket, call_count: int) -> None:
        if call_count == 2:
            runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(
                status=SingleCycleStatus.STALLED,
                session_id="ses_stalled",
                escalation=escalation,
                escalation_details="Worker process stalled with no output for 30s",
            ),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_stalled"),
        ],
        on_call=_on_call,
    )

    executor = _StubExecutor([_passing_report()])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed is True
    assert result.attempts == 2
    resume_prompt = cycle_runner.calls[1]["prompt"]
    assert "Worker process stalled with no output for 30s" in resume_prompt


def test_budget_exhaustion_opens_intervention_menu(tmp_path: Path) -> None:
    """Exhausting max_attempts opens the intervention menu through InterventionGateway."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)

    # Gateway scripted to skip
    gateway = FakeInterventionGateway(decisions=[InterventionDecision(action=InterventionAction.SKIP)])

    def _on_call(t: Ticket, call_count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
        ],
        on_call=_on_call,
    )

    executor = _StubExecutor([
        _failing_report(tail="Failure 1"),
        _failing_report(tail="Failure 2"),
        _failing_report(tail="Failure 3"),
    ])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    result = asyncio.run(loop.run())

    assert result.is_skipped is True
    assert result.status == VerificationLoopStatus.SKIPPED
    assert result.attempts == 3
    assert len(gateway.request_records) == 1
    record = gateway.request_records[0]
    assert record.ticket.id == ticket.id
    assert record.attempt == 3
    assert "Failure 3" in record.diagnostics


def test_retry_with_hint_restores_full_budget_and_injects_hint_in_prompt(tmp_path: Path) -> None:
    """Retry with a hint restores the full budget and injects the hint in the resume prompt."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)

    gateway = FakeInterventionGateway(
        decisions=[
            InterventionDecision(action=InterventionAction.RETRY, hint="Check fixture path"),
            InterventionDecision(action=InterventionAction.SKIP),
        ]
    )

    def _on_call(t: Ticket, call_count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
            # After retry, fresh budget of 2:
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1"),
        ],
        on_call=_on_call,
    )

    # max_attempts = 2:
    # Fail 1, Fail 2 -> menu opens -> retry -> Fail 3, Fail 4 -> menu opens -> skip
    executor = _StubExecutor([
        _failing_report(tail="Fail 1"),
        _failing_report(tail="Fail 2"),
        _failing_report(tail="Fail 3 after retry"),
        _failing_report(tail="Fail 4 after retry"),
    ])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=2,
    )

    result = asyncio.run(loop.run())

    assert result.is_skipped is True
    # Two intervention requests occurred, each after 2 failed attempts
    assert len(gateway.request_records) == 2
    assert gateway.request_records[0].attempt == 2
    assert gateway.request_records[1].attempt == 2

    # The first run after retry (call index 2 in 0-indexed: call 0, call 1, call 2) received the hint
    retry_prompt = cycle_runner.calls[2]["prompt"]
    assert "Operator hint: Check fixture path" in retry_prompt
    assert "Fail 2" in retry_prompt


def test_skip_returns_skip_result_with_last_diagnostics(tmp_path: Path) -> None:
    """Skip returns a skip result carrying the last diagnostics."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=[InterventionDecision(action=InterventionAction.SKIP)])

    def _on_call(t: Ticket, call_count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )

    executor = _StubExecutor([_failing_report(tail="Critical syntax error")])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=1,
    )

    result = asyncio.run(loop.run())

    assert result.is_skipped is True
    assert "Critical syntax error" in (result.diagnostics or "")


def test_abort_raises_user_abort_error(tmp_path: Path) -> None:
    """Abort raises UserAbortError immediately and does not touch the tree."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=[InterventionDecision(action=InterventionAction.ABORT)])

    def _on_call(t: Ticket, call_count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )

    executor = _StubExecutor([_failing_report(tail="Aborted failure")])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=1,
    )

    with pytest.raises(UserAbortError, match="aborted by operator"):
        asyncio.run(loop.run())


def test_question_pending_returns_session_id_with_zero_budget_consumed(tmp_path: Path) -> None:
    """QUESTION_PENDING returns with session id and zero budget consumed; re-entry continues with same budget."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    def _on_call(t: Ticket, call_count: int) -> None:
        # Calls 2 and 3 produce ready signal
        if call_count in (2, 3):
            runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            # Run 1: asks a question
            WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_q1"),
            # Run 2 (re-entry): ready signal emitted, verification fails
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_q1"),
            # Run 3: ready signal emitted, verification passes
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_q1"),
        ],
        on_call=_on_call,
    )

    executor = _StubExecutor([
        _failing_report(tail="Verify failure after question answered"),
        _passing_report(),
    ])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=2,
    )

    # First invocation: question interrupts
    result1 = asyncio.run(loop.run())

    assert result1.is_question_pending is True
    assert result1.session_id == "ses_q1"
    assert result1.attempts == 0  # Zero budget consumed!
    assert loop.attempts == 0

    # Second invocation on the same loop instance: re-entry with answer prompt
    result2 = asyncio.run(loop.run(prompt="Answer to your question: use posix."))

    assert result2.is_passed is True
    assert result2.attempts == 2
    # Ensure call 2 carried the answer prompt
    assert cycle_runner.calls[1]["prompt"] == "Answer to your question: use posix."
    assert cycle_runner.calls[1]["session_id"] == "ses_q1"


def test_question_interleave_preserves_accumulated_failure_budget(tmp_path: Path) -> None:
    """A question interleave between failures does not reset the failure counter."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=[InterventionDecision(action=InterventionAction.SKIP)])

    def _on_call(t: Ticket, call_count: int) -> None:
        if call_count in (1, 3):
            runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [
            # Attempt 1: ready -> fails verification
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_active"),
            # Attempt 2: question interrupts! (0 budget consumed)
            WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_active"),
            # Re-entry Attempt 2: ready -> fails verification (budget = 2, trips max_attempts=2)
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_active"),
        ],
        on_call=_on_call,
    )

    executor = _StubExecutor([
        _failing_report(tail="Failure before question"),
        _failing_report(tail="Failure after question"),
    ])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=2,
    )

    # Attempt 1 fails, loop proceeds to attempt 2 where question interrupts
    result1 = asyncio.run(loop.run())
    assert result1.is_question_pending is True
    assert loop.attempts == 1  # 1 failure was already consumed

    # Re-entry: attempt 2 fails, hitting max_attempts=2 -> trips breaker!
    result2 = asyncio.run(loop.run())
    assert result2.is_skipped is True
    assert len(gateway.request_records) == 1
    assert gateway.request_records[0].attempt == 2


def test_max_attempts_one_trips_after_first_failure(tmp_path: Path) -> None:
    """max_attempts=1 trips after the first failure; counter never goes negative."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=[InterventionDecision(action=InterventionAction.SKIP)])

    def _on_call(t: Ticket, call_count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(_ready_signal_payload(t.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )

    executor = _StubExecutor([_failing_report(tail="Single shot fail")])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=1,
    )

    assert loop.attempts == 0
    result = asyncio.run(loop.run())
    assert result.is_skipped is True
    assert loop.attempts == 1
    assert gateway.request_records[0].attempt == 1


def test_ready_signal_is_single_use_and_consumed(tmp_path: Path) -> None:
    """Ready signal file is deleted so it can never be verified twice without fresh emission."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    # Author ready signal file
    ready_path = runtime_paths.ready_signal_path(ticket.id)
    ready_path.write_text(_ready_signal_payload(ticket.id), encoding="utf-8")

    cycle_runner = _StubCycleRunner([WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")])
    executor = _StubExecutor([_passing_report()])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed is True
    # The ready signal file on disk must now be gone!
    assert not ready_path.exists()
    assert signals.read_ready(ticket.id) is None


def test_diagnostics_are_bounded_in_resume_prompt() -> None:
    """Bounding prevents a huge diagnostics tail from blowing token context."""
    ticket = _make_ticket()
    huge_tail = "\n".join(f"line-{i}: some verbose test output" for i in range(250))
    prompt = build_verification_failure_prompt(
        ticket=ticket,
        diagnostics=huge_tail,
        hint="My operator hint",
        max_lines=100,
    )

    prompt_lines = prompt.splitlines()
    # Ensure bounded
    assert len(prompt_lines) <= 120
    assert "line-249: some verbose test output" in prompt
    assert "line-150: some verbose test output" in prompt
    assert "line-0: some verbose test output" not in prompt
    assert "Operator hint: My operator hint" in prompt


def test_orchestrator_outcome_aborted_and_user_abort_error() -> None:
    """Orchestrator outcome enum has ABORTED and run_next releases lock and raises UserAbortError."""
    assert TicketOutcomeStatus.ABORTED == "aborted"
    outcome = TicketOutcome.aborted(details="Intervention abort")
    assert outcome.is_aborted is True
    assert outcome.status == TicketOutcomeStatus.ABORTED

    # Test QueueOrchestrator raising UserAbortError on aborted outcome
    ticket_repo = FakeTicketRepository([_make_ticket("T031")])
    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        processor=lambda t: asyncio.sleep(0, result=TicketOutcome.aborted(details="Operator abort")),
    )

    # When run_next processes an aborted outcome, it releases the lock and raises UserAbortError
    with pytest.raises(UserAbortError, match="Operator abort"):
        asyncio.run(orchestrator.run_next())
