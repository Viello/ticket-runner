"""In-memory fake implementation of SignalRepository for testing."""

from __future__ import annotations

from dataclasses import replace

from runner.domain.exceptions import SignalFormatError
from runner.domain.signal import QuestionSignal, ReadySignal, SignalStatus


class FakeSignalRepository:
    """In-memory test double conforming to SignalRepository."""

    def __init__(
        self,
        read_ready_error: Exception | None = None,
        read_question_error: Exception | None = None,
    ) -> None:
        self._ready: dict[str, ReadySignal] = {}
        self._questions: dict[str, QuestionSignal] = {}
        self._read_ready_error = read_ready_error
        self._read_question_error = read_question_error
        self.write_answer_calls: list[tuple[str, str]] = []
        self.consumed_ready: list[str] = []
        self.purged_tickets: list[str] = []

    def seed_ready(self, signal: ReadySignal) -> None:
        """Seed a ready Signal as if the Worker had written it."""
        self._ready[signal.ticket_id] = signal

    def seed_question(self, signal: QuestionSignal) -> None:
        """Seed a question Signal as if the Worker had written it."""
        self._questions[signal.ticket_id] = signal

    def read_ready(self, ticket_id: str) -> ReadySignal | None:
        """Return the seeded ready Signal, or raise the injected malformed fixture error."""
        if self._read_ready_error is not None:
            raise self._read_ready_error
        return self._ready.get(ticket_id)

    def read_pending_question(self, ticket_id: str) -> QuestionSignal | None:
        """Return the seeded question unless it is answered, or raise the injected error."""
        if self._read_question_error is not None:
            raise self._read_question_error
        question = self._questions.get(ticket_id)
        if question is None or question.status is SignalStatus.ANSWERED:
            return None
        return question

    def consume_ready(self, ticket_id: str) -> None:
        """Record the consumption and drop the seeded ready Signal."""
        self.consumed_ready.append(ticket_id)
        self._ready.pop(ticket_id, None)

    def write_answer(self, ticket_id: str, answer: str) -> QuestionSignal:
        """Record the call and flip the seeded question to answered."""
        self.write_answer_calls.append((ticket_id, answer))
        question = self._questions.get(ticket_id)
        if question is None:
            raise SignalFormatError(f"Question signal for ticket '{ticket_id}' not found")
        answered = replace(question, status=SignalStatus.ANSWERED, answer=answer)
        self._questions[ticket_id] = answered
        return answered

    def purge(self, ticket_id: str) -> None:
        """Record the purge and drop both seeded artifacts."""
        self.purged_tickets.append(ticket_id)
        self._ready.pop(ticket_id, None)
        self._questions.pop(ticket_id, None)
