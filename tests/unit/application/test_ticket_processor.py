"""Unit tests for TicketProcessor application interactor (T032)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationLoop,
    VerificationReport,
    build_verification_failure_prompt,
)
from runner.application.handoff_coordinator import (
    HandoffCoordinator,
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.application.prompt_builder import PromptBuilder
from runner.application.queue_orchestrator import (
    TicketOutcome,
    TicketOutcomeStatus,
    TicketProcessor as TicketProcessorProtocol,
)
from runner.application.ticket_processor import GatekeeperTicketProcessor, TicketProcessor
from runner.domain.config import VerificationConfig
from runner.domain.exceptions import UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import QuestionSignal, QuestionType, ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_intervention import FakeInterventionGateway


def _make_ticket(
    ticket_id: str = "T032",
    title: str = "Ready-path ticket processor",
    spec_path: str = "docs/specs/04-signal-protocol-and-gatekeeper.md",
    security_required: bool = False,
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=title,
        status=TicketStatus.PENDING,
        spec_path=spec_path,
        requirements=("Implement the TicketProcessor seam.",),
        acceptance_criteria=("Single commit with Update bullets.",),
        gotchas=(),
        path=Path(f"docs/tickets/04-signal-protocol-and-gatekeeper/{ticket_id}-test.md"),
        security_required=security_required,
    )


class _StubCycleRunner:
    def __init__(
        self,
        responses: list[WorkerRunResult],
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
        return self._responses.pop(0)


class _StubExecutor:
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


def _failing_report(cmd: str = "pytest -q", tail: str = "AssertionError in tests") -> VerificationReport:
    outcome = CommandOutcome(label="test", command=cmd, exit_code=1, timed_out=False, tail=tail)
    return VerificationReport(
        passed=False,
        results=(outcome,),
        diagnostics=(f"$ {cmd}\nexit code 1\n{tail}",),
        skipped_commands=(),
    )


def test_conforms_to_queue_orchestrator_ticket_processor_protocol() -> None:
    """TicketProcessor satisfies the queue_orchestrator.TicketProcessor protocol."""
    processor = TicketProcessor()
    assert isinstance(processor, TicketProcessorProtocol)
    assert isinstance(GatekeeperTicketProcessor(), TicketProcessorProtocol)


def test_purge_at_start_removes_stale_ready_and_question_signals(tmp_path: Path) -> None:
    """Purge at start deletes leftover ready and question files from earlier runs."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    runtime_paths.ensure_questions_dir()
    signals = FilesystemSignalRepository(runtime_paths)

    ready_file = runtime_paths.ready_signal_path(ticket.id)
    question_file = runtime_paths.question_path(ticket.id)
    ready_file.write_text("stale ready content", encoding="utf-8")
    question_file.write_text("stale question content", encoding="utf-8")
    assert ready_file.is_file()
    assert question_file.is_file()

    purged_during_run = False

    def _on_call(t: Ticket, count: int) -> None:
        nonlocal purged_during_run
        # Verify that by the time cycle runner is called, files were purged!
        if not ready_file.exists() and not question_file.exists():
            purged_during_run = True
        # Write fresh ready signal for cycle 1
        ready_file.write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/foo.py"],
                "self_review_notes": "Cleaned up",
                "new_gotchas": [],
                "timestamp": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])
    gateway = FakeInterventionGateway()

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
    )

    outcome = asyncio.run(processor(ticket))

    assert purged_during_run is True
    assert outcome.is_approved is True


def test_happy_path_approved_outcome_mapping(tmp_path: Path) -> None:
    """Passing verification maps into TicketOutcome.approved with changes, gotchas, scope, and logged notes."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    printed_lines: list[str] = []

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/application/ticket_processor.py", "tests/unit/test_foo.py"],
                "self_review_notes": "All unit tests pass and code-review verified.",
                "new_gotchas": ["Discovered async queue timing nuance."],
                "scope": "application",
                "timestamp": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        printer=printed_lines.append,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    # Changes formatted as ["Update <path>", ...]
    assert outcome.changes == (
        "Update runner/application/ticket_processor.py",
        "Update tests/unit/test_foo.py",
    )
    # new_gotchas passed through
    assert outcome.new_gotchas == ("Discovered async queue timing nuance.",)
    # scope mapped from signal
    assert outcome.scope == "application"
    # self_review_notes surfaced to terminal log only (never in changes or gotchas)
    assert any("All unit tests pass and code-review verified." in line for line in printed_lines)
    assert "All unit tests pass" not in "".join(outcome.changes)
    assert "All unit tests pass" not in "".join(outcome.new_gotchas)


def test_scope_absent_maps_to_none_for_orchestrator_default(tmp_path: Path) -> None:
    """When scope is absent from ready signal, outcome.scope is None for orchestrator fallback."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/foo.py"],
                "self_review_notes": "Implemented without explicit scope.",
                "new_gotchas": [],
                "timestamp": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert outcome.scope is None


def test_skipped_outcome_mapping_with_diagnostics(tmp_path: Path) -> None:
    """A skipped verification result maps to TicketOutcome.skipped(details=<diagnostics>)."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=["skip"])

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/broken.py"],
                "self_review_notes": "Broken build.",
                "new_gotchas": [],
                "timestamp": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )
    executor = _StubExecutor([_failing_report(tail="SyntaxError: invalid syntax")])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=1,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_skipped is True
    assert "SyntaxError: invalid syntax" in str(outcome.details)


def test_aborted_outcome_mapping_on_operator_abort(tmp_path: Path) -> None:
    """When operator selects abort, processor maps UserAbortError into TicketOutcome.aborted."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=["abort"])

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/broken.py"],
                "self_review_notes": "Needs debugging on PC.",
                "new_gotchas": [],
                "timestamp": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_1")],
        on_call=_on_call,
    )
    executor = _StubExecutor([_failing_report(tail="Fatal test crash")])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=1,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_aborted is True
    assert "aborted" in str(outcome.details).lower()


def test_initialization_with_handoff_coordinator(tmp_path: Path) -> None:
    """TicketProcessor seamlessly extracts cycle_runner and signal_repository from coordinator."""
    ticket = _make_ticket()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)

    runner = FakeCommandRunner()
    coordinator = HandoffCoordinator(
        runtime_paths=runtime_paths,
        signal_repository=signals,
    )

    processor = TicketProcessor(
        coordinator=coordinator,
        executor=_StubExecutor([_passing_report()]),  # type: ignore
        intervention_gateway=FakeInterventionGateway(),
    )

    assert processor.signal_repository is signals
    assert processor.cycle_runner == coordinator.run_cycle

    # Test build_initial_prompt delegates to coordinator
    prompt = processor.build_initial_prompt(ticket)
    assert ticket.id in prompt
    assert "Ready Signal Protocol" in prompt


# --- T033: Question Loop & Answer Resume Unit Tests ---


def test_choice_question_scripted_answer_and_resume_to_approval(tmp_path: Path) -> None:
    """A choice question leads to scripted answer 'A', writes answered JSON, resumes session, and passes."""
    ticket = _make_ticket(ticket_id="T033", title="Question loop ticket")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    runtime_paths.ensure_questions_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(answers=["A"])

    question_path = runtime_paths.question_path(ticket.id)
    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        if count == 1:
            # Worker writes choice question
            question_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "question": "Which caching backend should be selected?",
                    "type": "choice",
                    "options": ["A) Redis", "B) Memcached"],
                    "status": "pending",
                    "answer": None,
                    "created_at": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
        elif count == 2:
            # Worker verifies answer was recorded, then emits ready signal
            ready_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/cache.py"],
                    "self_review_notes": "Implemented choice A.",
                    "new_gotchas": [],
                    "scope": "application",
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_active"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_active"),
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert outcome.changes == ("Update runner/cache.py",)
    assert outcome.scope == "application"

    # Gateway recorded the choice question
    assert len(gateway.question_prompts) == 1
    assert gateway.question_prompts[0].question == "Which caching backend should be selected?"
    assert gateway.question_prompts[0].options == ("A) Redis", "B) Memcached")

    # On-disk JSON shows "answered" plus "A", preserving other fields
    assert question_path.is_file()
    saved_payload = json.loads(question_path.read_text(encoding="utf-8"))
    assert saved_payload["status"] == "answered"
    assert saved_payload["answer"] == "A"
    assert saved_payload["type"] == "choice"
    assert saved_payload["options"] == ["A) Redis", "B) Memcached"]
    assert saved_payload["ticket_id"] == ticket.id

    # The resume prompt on cycle 2 carried the answer and session_id was preserved
    assert len(cycle_runner.calls) == 2
    resume_call = cycle_runner.calls[1]
    assert resume_call["session_id"] == "ses_active"
    assert "User answered: A. Proceed with implementation." in resume_call["prompt"]

    # Ready signal was single-use consumed, answered question retained for audit
    assert not ready_path.exists()
    assert question_path.exists()


def test_two_sequential_questions_preserve_budget_and_session(tmp_path: Path) -> None:
    """Two sequential questions both work with the budget counter unchanged afterwards."""
    ticket = _make_ticket(ticket_id="T033")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    runtime_paths.ensure_questions_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(answers=["First Answer", "Second Answer"])

    question_path = runtime_paths.question_path(ticket.id)
    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        if count == 1:
            question_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "question": "First question?",
                    "type": "text",
                    "options": None,
                    "status": "pending",
                    "answer": None,
                    "created_at": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
        elif count == 2:
            question_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "question": "Second question?",
                    "type": "text",
                    "options": None,
                    "status": "pending",
                    "answer": None,
                    "created_at": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )
        elif count == 3:
            ready_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/sequential.py"],
                    "self_review_notes": "Implemented after 2 questions.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_seq"),
            WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_seq"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_seq"),
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert len(cycle_runner.calls) == 3

    # Both questions prompted
    assert len(gateway.question_prompts) == 2
    assert gateway.question_prompts[0].question == "First question?"
    assert gateway.question_prompts[1].question == "Second question?"

    # Prompts for calls 2 and 3
    assert cycle_runner.calls[1]["prompt"] == "User answered: First Answer. Proceed with implementation."
    assert cycle_runner.calls[2]["prompt"] == "User answered: Second Answer. Proceed with implementation."
    assert cycle_runner.calls[1]["session_id"] == "ses_seq"
    assert cycle_runner.calls[2]["session_id"] == "ses_seq"


def test_ready_wins_precedence_when_both_signals_exist(tmp_path: Path) -> None:
    """Ready-wins: with a pending question and a valid ready Signal, verification proceeds with no prompt."""
    ticket = _make_ticket(ticket_id="T033")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    runtime_paths.ensure_questions_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    question_path = runtime_paths.question_path(ticket.id)
    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        # Worker authored a question AND a valid ready signal
        question_path.write_text(
            json.dumps({
                "ticket_id": t.id,
                "question": "Stale question that shouldn't be asked?",
                "type": "text",
                "options": None,
                "status": "pending",
                "answer": None,
                "created_at": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )
        ready_path.write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/winner.py"],
                "self_review_notes": "Ready signal wins over question.",
                "new_gotchas": [],
                "timestamp": "2026-09-17T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_readyWins")],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    # Human was NEVER prompted
    assert len(gateway.question_prompts) == 0

    # Stale question was cleaned and ready signal was consumed
    assert not question_path.exists()
    assert not ready_path.exists()


def test_malformed_question_consumes_attempt_with_parse_error_diagnostics(tmp_path: Path) -> None:
    """A malformed question consumes one attempt with the parse error fed back as diagnostics."""
    ticket = _make_ticket(ticket_id="T033")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    runtime_paths.ensure_questions_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    question_path = runtime_paths.question_path(ticket.id)
    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        if count == 1:
            # Emits malformed question JSON (missing required field 'question')
            question_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "type": "text",
                    "status": "pending",
                }),
                encoding="utf-8",
            )
        elif count == 2:
            # Emits valid ready signal
            ready_path.write_text(
                json.dumps({
                    "ticket_id": t.id,
                    "status": "ready_for_verification",
                    "modified_files": ["runner/fixed.py"],
                    "self_review_notes": "Fixed after malformed question.",
                    "new_gotchas": [],
                    "timestamp": "2026-09-17T00:00:00+00:00",
                }),
                encoding="utf-8",
            )

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_malformed"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_malformed"),
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert len(cycle_runner.calls) == 2

    # Cycle 2 resume prompt received diagnostics with the parse error
    resume_prompt = cycle_runner.calls[1]["prompt"]
    assert "Gatekeeper verification failed" in resume_prompt
    assert "question" in resume_prompt.lower()
    assert cycle_runner.calls[1]["session_id"] == "ses_malformed"

    # Malformed question file was cleaned
    assert not question_path.exists()


def test_malformed_question_exhausts_budget_trips_circuit_breaker(tmp_path: Path) -> None:
    """A malformed question when budget is 1 trips circuit breaker; operator skip returns skipped."""
    ticket = _make_ticket(ticket_id="T033")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    runtime_paths.ensure_questions_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=["skip"])

    question_path = runtime_paths.question_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        question_path.write_text("NOT VALID JSON", encoding="utf-8")

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.QUESTION_PENDING, session_id="ses_breaker")],
        on_call=_on_call,
    )
    executor = _StubExecutor([])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=1,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_skipped is True
    assert "not valid json" in str(outcome.details).lower()
    assert len(gateway.request_records) == 1
    assert gateway.request_records[0].attempt == 1


# --- T046: Ready Signal Soft Warnings & Diagnostic Resume Tests ---


def test_ready_signal_soft_warnings_emitted_when_code_review_and_agents_md_missing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Missing code-review and AGENTS.md triggers soft warnings via notify and logger, but verification passes."""
    ticket = _make_ticket(ticket_id="T046", security_required=False)
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/app.py"],
                "self_review_notes": "Implemented feature without review.",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    # Worker accessed only "implement", missing "code-review" and "AGENTS.md"
    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_1",
                resources_accessed=frozenset({"implement"}),
            )
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    notices: list[str] = []
    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        notify=notices.append,
    )

    with caplog.at_level(logging.WARNING):
        outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True

    # Check both warnings emitted via notify
    expected_cr = (
        "[T046] Warning: Ready signal emitted without reading '.agents/skills/code-review/SKILL.md'. "
        "Proceeding to verification."
    )
    expected_agents = (
        "[T046] Warning: Ready signal emitted without reading 'AGENTS.md'. "
        "Proceeding to verification."
    )
    assert expected_cr in notices
    assert expected_agents in notices

    # Check warnings in caplog at WARNING level
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    log_messages = [r.getMessage() for r in warning_records]
    assert any(expected_cr in msg for msg in log_messages)
    assert any(expected_agents in msg for msg in log_messages)


def test_ready_signal_security_required_missing_security_review_emits_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When security_required is true, missing security-review emits soft warning."""
    ticket = _make_ticket(ticket_id="T046", security_required=True)
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/secure.py"],
                "self_review_notes": "Implemented security feature.",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    # Worker accessed code-review and AGENTS.md, but missed security-review
    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_1",
                resources_accessed=frozenset({"implement", "code-review", "AGENTS.md"}),
            )
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    notices: list[str] = []
    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        notify=notices.append,
    )

    with caplog.at_level(logging.WARNING):
        outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True

    expected_sec = (
        "[T046] Warning: Ready signal emitted without reading required '.agents/skills/security-review/SKILL.md'. "
        "Proceeding to verification."
    )
    assert expected_sec in notices
    assert not any("code-review" in n for n in notices)
    assert not any("AGENTS.md" in n for n in notices)

    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    log_messages = [r.getMessage() for r in warning_records]
    assert any(expected_sec in msg for msg in log_messages)


def test_ready_signal_with_all_required_resources_emits_no_soft_warnings(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When all required resources are present in resources_accessed, no soft warnings are emitted."""
    ticket = _make_ticket(ticket_id="T046", security_required=True)
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/perfect.py"],
                "self_review_notes": "All reviews performed.",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_1",
                resources_accessed=frozenset({
                    "implement",
                    "code-review",
                    "AGENTS.md",
                    "security-review",
                }),
            )
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_passing_report()])

    notices: list[str] = []
    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        notify=notices.append,
    )

    with caplog.at_level(logging.WARNING):
        outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert len(notices) == 0
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warning_records) == 0


def test_soft_warnings_non_blocking_on_verification_failure(
    tmp_path: Path,
) -> None:
    """Missing skills emit soft warnings without failing verification attempt or tripping breaker."""
    ticket = _make_ticket(ticket_id="T046")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway(decisions=["skip"])

    def _on_call(t: Ticket, count: int) -> None:
        runtime_paths.ready_signal_path(t.id).write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/failed.py"],
                "self_review_notes": "Needs fix.",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    # Missing all review skills; command fails
    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_1",
                resources_accessed=frozenset({"implement"}),
            )
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([_failing_report(tail="Test failed on assert")])

    notices: list[str] = []
    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        notify=notices.append,
        max_attempts=1,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_skipped is True
    assert "Test failed on assert" in str(outcome.details)
    # Warnings were emitted
    assert any("code-review" in n for n in notices)
    # The failure was due to test failure, exactly 1 attempt consumed
    assert len(gateway.request_records) == 1
    assert gateway.request_records[0].attempt == 1


def test_attempt_1_failure_resume_prompt_has_no_diagnostic_skill_directive(
    tmp_path: Path,
) -> None:
    """Attempt 1 failure resume prompt contains error output without prepending diagnostic directive."""
    ticket = _make_ticket(ticket_id="T046")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        ready_path.write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/attempt1.py"],
                "self_review_notes": f"Attempt {count}",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_diag"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_diag"),
        ],
        on_call=_on_call,
    )
    # Attempt 1 fails, Attempt 2 passes
    executor = _StubExecutor([
        _failing_report(tail="FAILED test_unit.py - KeyError: 'foo'"),
        _passing_report(),
    ])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert len(cycle_runner.calls) == 2

    resume_prompt = cycle_runner.calls[1]["prompt"]
    assert resume_prompt is not None
    assert "Gatekeeper verification failed for ticket T046." in resume_prompt
    assert "FAILED test_unit.py - KeyError: 'foo'" in resume_prompt
    # Must NOT have diagnosing-bugs directive
    assert ".agents/skills/diagnosing-bugs/SKILL.md" not in resume_prompt


def test_attempt_2_plus_failure_resume_prompt_prepends_diagnosing_bugs_directive(
    tmp_path: Path,
) -> None:
    """Attempt 2+ failure resume prompt prepends diagnosing-bugs directive before error diagnostics."""
    ticket = _make_ticket(ticket_id="T046")
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        ready_path.write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/attempt2.py"],
                "self_review_notes": f"Attempt {count}",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_diag2"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_diag2"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_diag2"),
        ],
        on_call=_on_call,
    )
    # Attempt 1 fails, Attempt 2 fails, Attempt 3 passes
    executor = _StubExecutor([
        _failing_report(tail="FAILED test_one.py"),
        _failing_report(tail="FAILED test_two.py"),
        _passing_report(),
    ])

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        max_attempts=3,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    assert len(cycle_runner.calls) == 3

    # Cycle 2 resume prompt (after attempt 1 failure) does NOT have directive
    prompt_cycle_2 = cycle_runner.calls[1]["prompt"]
    assert ".agents/skills/diagnosing-bugs/SKILL.md" not in prompt_cycle_2

    # Cycle 3 resume prompt (after attempt 2 failure) PREPENDS directive
    prompt_cycle_3 = cycle_runner.calls[2]["prompt"]
    expected_prefix = (
        "Gatekeeper verification failed (attempt 2). "
        "Before making further edits, read and follow '.agents/skills/diagnosing-bugs/SKILL.md' "
        "using your file reading tool to diagnose and isolate the root cause.\n\n"
    )
    assert prompt_cycle_3.startswith(expected_prefix)
    assert "FAILED test_two.py" in prompt_cycle_3


def test_build_verification_failure_prompt_formatting_by_attempt() -> None:
    """build_verification_failure_prompt formats correctly for attempt 1, 2, and beyond."""
    ticket = _make_ticket(ticket_id="T046")
    diagnostics = "AssertionError: expected True, got False"

    # Attempt 1 (default)
    prompt_1 = build_verification_failure_prompt(ticket, diagnostics)
    assert "Gatekeeper verification failed for ticket T046." in prompt_1
    assert ".agents/skills/diagnosing-bugs/SKILL.md" not in prompt_1
    assert "AssertionError: expected True, got False" in prompt_1

    # Attempt 2
    prompt_2 = build_verification_failure_prompt(ticket, diagnostics, attempt=2)
    expected_prefix_2 = (
        "Gatekeeper verification failed (attempt 2). "
        "Before making further edits, read and follow '.agents/skills/diagnosing-bugs/SKILL.md' "
        "using your file reading tool to diagnose and isolate the root cause.\n\n"
    )
    assert prompt_2.startswith(expected_prefix_2)
    assert "AssertionError: expected True, got False" in prompt_2

    # Attempt 3
    prompt_3 = build_verification_failure_prompt(ticket, diagnostics, attempt=3)
    expected_prefix_3 = (
        "Gatekeeper verification failed (attempt 3). "
        "Before making further edits, read and follow '.agents/skills/diagnosing-bugs/SKILL.md' "
        "using your file reading tool to diagnose and isolate the root cause.\n\n"
    )
    assert prompt_3.startswith(expected_prefix_3)


def test_multi_cycle_resource_accumulation(tmp_path: Path) -> None:
    """Resources accessed across multiple cycles accumulate, satisfying soft warnings on subsequent ready."""
    ticket = _make_ticket(ticket_id="T046", security_required=False)
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    runtime_paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(runtime_paths)
    gateway = FakeInterventionGateway()

    ready_path = runtime_paths.ready_signal_path(ticket.id)

    def _on_call(t: Ticket, count: int) -> None:
        ready_path.write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["runner/accum.py"],
                "self_review_notes": f"Cycle {count}",
                "new_gotchas": [],
                "timestamp": "2026-09-18T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    # Cycle 1 accessed code-review (missing AGENTS.md), fails verification
    # Cycle 2 accessed AGENTS.md, passes verification
    cycle_runner = _StubCycleRunner(
        [
            WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_accum",
                resources_accessed=frozenset({"code-review"}),
            ),
            WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_accum",
                resources_accessed=frozenset({"AGENTS.md"}),
            ),
        ],
        on_call=_on_call,
    )
    executor = _StubExecutor([
        _failing_report(tail="Initial failure"),
        _passing_report(),
    ])

    notices: list[str] = []
    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,  # type: ignore
        intervention_gateway=gateway,
        notify=notices.append,
        max_attempts=3,
    )

    outcome = asyncio.run(processor(ticket))

    assert outcome.is_approved is True
    # In Cycle 1, AGENTS.md was missing, so its warning was emitted
    assert any("AGENTS.md" in n for n in notices)
    # code-review was NOT in notices because it was accessed in Cycle 1
    assert not any("code-review" in n for n in notices)

