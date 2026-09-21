"""In-memory fake implementation of TicketRepository for testing."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from runner.domain.ticket import Ticket, TicketStatus


class FakeTicketRepository:
    """In-memory test double conforming to TicketRepository."""

    def __init__(
        self,
        tickets: list[Ticket] | None = None,
        exists_val: bool = True,
        error: Exception | None = None,
    ) -> None:
        self._tickets: list[Ticket] = list(tickets) if tickets is not None else []
        self._exists = exists_val
        self._error = error

    def add_ticket(self, ticket: Ticket) -> None:
        """Add a ticket to the in-memory repository."""
        self._tickets.append(ticket)

    def exists(self) -> bool:
        """Return whether the backing repository exists."""
        return self._exists

    def _extract_spec_slug(self, ticket: Ticket) -> str:
        """Derive spec slug from ticket path or spec_path."""
        if ticket.path and ticket.path.parent.name:
            if ticket.path.parent.name == "completed" and ticket.path.parent.parent.name:
                return ticket.path.parent.parent.name
            return ticket.path.parent.name
        if ticket.spec_path:
            return Path(ticket.spec_path).stem
        return "default"

    def get_active_spec_slug(self) -> str | None:
        """Return first spec slug that has pending tickets."""
        if self._error:
            raise self._error
        by_spec: dict[str, list[Ticket]] = defaultdict(list)
        for t in self._tickets:
            if t.status == TicketStatus.PENDING:
                by_spec[self._extract_spec_slug(t)].append(t)
        if not by_spec:
            return None
        sorted_specs = sorted(by_spec.keys())
        return sorted_specs[0]

    def list_pending(self, spec_slug: str | None = None) -> list[Ticket]:
        """List pending tickets sorted by numeric identifier."""
        if self._error:
            raise self._error
        target_spec = spec_slug or self.get_active_spec_slug()
        if target_spec is None:
            return []
        pending = [
            t for t in self._tickets
            if t.status == TicketStatus.PENDING and self._extract_spec_slug(t) == target_spec
        ]
        return sorted(pending, key=lambda t: (int(t.id[1:]), t.id))

    def list_all_pending(self) -> list[Ticket]:
        """List all pending tickets across all specs in execution order."""
        if self._error:
            raise self._error
        by_spec: dict[str, list[Ticket]] = defaultdict(list)
        for t in self._tickets:
            if t.status == TicketStatus.PENDING:
                by_spec[self._extract_spec_slug(t)].append(t)
        result: list[Ticket] = []
        for spec in sorted(by_spec.keys()):
            sorted_tickets = sorted(by_spec[spec], key=lambda t: (int(t.id[1:]), t.id))
            result.extend(sorted_tickets)
        return result

    def select_next_pending(self, spec_slug: str | None = None) -> Ticket | None:
        """Select lowest-identifier pending ticket."""
        pending = self.list_pending(spec_slug=spec_slug)
        return pending[0] if pending else None

    def is_completed(self, ticket_id: str) -> bool:
        """Check whether a ticket is already completed or in completed/."""
        if self._error:
            raise self._error
        target_id = ticket_id.strip()
        for t in self._tickets:
            if t.id == target_id:
                if t.status in (TicketStatus.COMPLETED, TicketStatus.SKIPPED):
                    return True
                if t.path and t.path.parent.name == "completed":
                    return True
        return False

    def _find_ticket(self, ticket: Ticket | Path | str) -> Ticket:
        target_id = ticket.id if isinstance(ticket, Ticket) else Path(str(ticket)).stem.split("-")[0]
        for t in self._tickets:
            if t.id == target_id or str(t.path) == str(ticket) or t.path.name == Path(str(ticket)).name:
                return t
        from runner.domain.exceptions import TicketFormatError
        raise TicketFormatError(f"Ticket '{ticket}' not found in repository")

    def finalize_completed(
        self,
        ticket: Ticket | Path | str,
        completed_at: datetime | str | None = None,
    ) -> Path:
        """Simulate marking a ticket completed and relocating."""
        if self._error:
            raise self._error
        target = self._find_ticket(ticket)
        dest_path = target.path.parent / "completed" / target.path.name
        idx = self._tickets.index(target)
        object.__setattr__(target, "status", TicketStatus.COMPLETED)
        object.__setattr__(target, "path", dest_path)
        self._tickets[idx] = target
        return dest_path

    def finalize_skipped(
        self,
        ticket: Ticket | Path | str,
        details: str | Mapping[str, Any] | None = None,
    ) -> Path:
        """Simulate marking a ticket skipped and relocating."""
        if self._error:
            raise self._error
        target = self._find_ticket(ticket)
        dest_path = target.path.parent / "completed" / target.path.name
        idx = self._tickets.index(target)
        object.__setattr__(target, "status", TicketStatus.SKIPPED)
        object.__setattr__(target, "path", dest_path)
        self._tickets[idx] = target
        return dest_path
