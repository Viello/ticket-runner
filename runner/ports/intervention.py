"""InterventionGateway protocol and intervention value objects for human contact."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from runner.domain.signal import QuestionSignal
from runner.domain.ticket import Ticket


class InterventionAction(Enum):
    """Human decisions available when the verification budget is exhausted."""

    RETRY = "retry"
    SKIP = "skip"
    ABORT = "abort"


@dataclass(frozen=True)
class InterventionDecision:
    """Human decision and optional hint after budget exhaustion."""

    action: InterventionAction
    hint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, InterventionAction):
            object.__setattr__(self, "action", InterventionAction(self.action))
        if self.hint is not None and not isinstance(self.hint, str):
            raise TypeError(
                f"InterventionDecision hint must be a string or None, got: {self.hint!r}"
            )


@runtime_checkable
class InterventionGateway(Protocol):
    """Abstract protocol for human contact: clarification questions and intervention menus."""

    def ask_question(self, question: QuestionSignal) -> str:
        """Prompt the human for an answer to a Worker clarification question.

        Args:
            question: Parsed pending QuestionSignal carrying type and options.

        Returns:
            The raw answer text, uninterpreted.

        Raises:
            NonInteractiveError: If no interactive stdin is available.
        """
        ...

    def request_intervention(
        self, ticket: Ticket, diagnostics: str, attempt: int
    ) -> InterventionDecision:
        """Ask the human how to proceed after the verification budget is exhausted.

        Args:
            ticket: Ticket whose verification budget was exhausted.
            diagnostics: Captured failure diagnostics shown in the menu.
            attempt: Number of failed verification attempts that tripped the breaker.

        Returns:
            InterventionDecision with action retry, skip, or abort.

        Raises:
            NonInteractiveError: If no interactive stdin is available and the
                adapter cannot fall back to abort.
        """
        ...

    def prompt_escalation(self, ticket: Ticket, report: str) -> bool:
        """Prompt the human whether to run /diagnosing-bugs upon diagnostic escalation (T066).

        Args:
            ticket: Ticket whose verification failed.
            report: Rendered structured diagnostic report.

        Returns:
            True if operator confirms (Y / Enter), False if operator declines (N).

        Raises:
            NonInteractiveError: If no interactive stdin is available.
        """
        ...
