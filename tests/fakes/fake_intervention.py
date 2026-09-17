"""FakeInterventionGateway test double for scripted answers and decisions."""

from __future__ import annotations

from dataclasses import dataclass

from runner.domain.signal import QuestionSignal
from runner.domain.ticket import Ticket
from runner.ports.intervention import InterventionAction, InterventionDecision


@dataclass(frozen=True)
class InterventionRecord:
    """Recorded request_intervention invocation payload."""

    ticket: Ticket
    diagnostics: str
    attempt: int


class FakeInterventionGateway:
    """In-memory InterventionGateway serving queued answers and decisions.

    Every prompt payload and diagnostics payload is recorded; exhausting the
    queues raises AssertionError so a silently mis-scripted test fails loudly.
    """

    def __init__(
        self,
        answers: list[str] | None = None,
        decisions: list[InterventionDecision | str] | None = None,
    ) -> None:
        self._answers = list(answers or [])
        self._decisions = [self._coerce(decision) for decision in (decisions or [])]
        self.question_prompts: list[QuestionSignal] = []
        self.request_records: list[InterventionRecord] = []

    @staticmethod
    def _coerce(decision: InterventionDecision | str) -> InterventionDecision:
        if isinstance(decision, InterventionDecision):
            return decision
        return InterventionDecision(action=InterventionAction(decision))

    def ask_question(self, question: QuestionSignal) -> str:
        """Return the next queued answer and record the prompt payload."""
        self.question_prompts.append(question)
        if not self._answers:
            raise AssertionError(
                "FakeInterventionGateway.ask_question called with no scripted "
                "answers remaining"
            )
        return self._answers.pop(0)

    def request_intervention(
        self, ticket: Ticket, diagnostics: str, attempt: int
    ) -> InterventionDecision:
        """Return the next queued decision and record the diagnostics payload."""
        self.request_records.append(
            InterventionRecord(ticket=ticket, diagnostics=diagnostics, attempt=attempt)
        )
        if not self._decisions:
            raise AssertionError(
                "FakeInterventionGateway.request_intervention called with no "
                "scripted decisions remaining"
            )
        return self._decisions.pop(0)