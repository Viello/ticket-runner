from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from runner.domain.ticket import Ticket


@runtime_checkable
class TicketRepository(Protocol):
    """Abstract protocol for discovering, selecting, and relocating tickets in a queue."""

    def list_pending(self, spec_slug: str | None = None) -> list[Ticket]:
        """List pending tickets in execution order.

        Args:
            spec_slug: Optional spec directory slug. If omitted, lists pending
                tickets for the active spec queue.

        Returns:
            List of pending Ticket entities sorted by numeric identifier.
        """
        ...

    def list_all_pending(self) -> list[Ticket]:
        """List all pending tickets across all spec queues in execution order.

        Returns:
            List of all pending Ticket entities sorted by spec and numeric identifier.
        """
        ...

    def select_next_pending(self, spec_slug: str | None = None) -> Ticket | None:
        """Return the next pending ticket to execute, or None if queue is empty.

        Args:
            spec_slug: Optional spec directory slug. If omitted, selects from
                the active spec queue.

        Returns:
            Lowest-identifier pending Ticket, or None if no pending tickets exist.
        """
        ...

    def get_active_spec_slug(self) -> str | None:
        """Return the directory slug of the active spec queue, or None if exhausted."""
        ...

    def exists(self) -> bool:
        """Check if the backing queue directory exists."""
        ...

    def finalize_completed(
        self,
        ticket: Ticket | Path | str,
        completed_at: datetime | str | None = None,
    ) -> Path:
        """Mark a ticket as completed and relocate to the completed/ subfolder.

        Args:
            ticket: Ticket entity, file Path, or identifier string.
            completed_at: Optional completion timestamp (datetime or ISO-8601 string).
                Defaults to current UTC time.

        Returns:
            Destination Path of the relocated ticket file.
        """
        ...

    def finalize_skipped(
        self,
        ticket: Ticket | Path | str,
        details: str | Mapping[str, Any] | None = None,
    ) -> Path:
        """Mark a ticket as skipped with failure details and relocate to completed/.

        Args:
            ticket: Ticket entity, file Path, or identifier string.
            details: Optional failure reason or dictionary of failure metadata.

        Returns:
            Destination Path of the relocated ticket file.
        """
        ...
