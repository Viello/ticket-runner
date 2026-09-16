"""TicketRepository protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runner.domain.ticket import Ticket


@runtime_checkable
class TicketRepository(Protocol):
    """Abstract protocol for discovering and selecting tickets from a queue."""

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
