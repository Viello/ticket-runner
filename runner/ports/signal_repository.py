from typing import Protocol, runtime_checkable

from runner.domain.signal import QuestionSignal, ReadySignal


@runtime_checkable
class SignalRepository(Protocol):
    """Abstract protocol for reading, consuming, and answering Worker Signals on disk."""

    def read_ready(self, ticket_id: str) -> ReadySignal | None:
        """Read the Ticket's ready Signal without consuming it.

        Args:
            ticket_id: Ticket identifier owning the Signal.

        Returns:
            Parsed ReadySignal, or None when no ready Signal file exists.

        Raises:
            SignalFormatError: If a ready Signal file exists but is malformed or
                belongs to a different Ticket.
        """
        ...

    def read_pending_question(self, ticket_id: str) -> QuestionSignal | None:
        """Read the Ticket's question Signal when it is still awaiting an answer.

        Args:
            ticket_id: Ticket identifier owning the question.

        Returns:
            Parsed QuestionSignal, or None when the file is absent or already answered.

        Raises:
            SignalFormatError: If a question file exists but is malformed or
                belongs to a different Ticket.
        """
        ...

    def consume_ready(self, ticket_id: str) -> None:
        """Delete the Ticket's ready Signal so it can never be verified twice.

        Idempotent: a missing file is a no-op.

        Args:
            ticket_id: Ticket identifier owning the Signal.
        """
        ...

    def write_answer(self, ticket_id: str, answer: str) -> QuestionSignal:
        """Atomically rewrite the Ticket's pending question as answered.

        Every field other than ``status`` and ``answer`` is preserved verbatim.

        Args:
            ticket_id: Ticket identifier owning the question.
            answer: Human-provided answer text.

        Returns:
            The updated QuestionSignal with ``status`` set to ``answered``.

        Raises:
            SignalFormatError: If no question file exists, it is malformed, or the
                answer is blank.
        """
        ...

    def clean_question(self, ticket_id: str) -> None:
        """Delete the Ticket's question Signal file if pending or malformed.

        Answered question files are retained for audit. Idempotent: absent
        files are tolerated.

        Args:
            ticket_id: Ticket identifier owning the question.
        """
        ...

    def purge(self, ticket_id: str) -> None:
        """Delete both Signal artifacts for the Ticket, creating directories as needed.

        Idempotent: absent files or directories are tolerated.

        Args:
            ticket_id: Ticket identifier owning the artifacts.
        """
        ...
