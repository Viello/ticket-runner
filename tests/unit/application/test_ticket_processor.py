"""Unit tests for TicketProcessor application interactor (T032)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationLoop,
    VerificationReport,
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
from runner.domain.signal import ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_intervention import FakeInterventionGateway


def _make_ticket(
    ticket_id: str = "T032",
    title: str = "Ready-path ticket processor",
    spec_path: str = "docs/specs/04-signal-protocol-and-gatekeeper.md",
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
