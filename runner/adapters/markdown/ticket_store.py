"""Directory-based ticket queue repository implementation."""

from __future__ import annotations

from pathlib import Path
import re

from runner.adapters.markdown.parser import ARCHIVED_DIRECTORY_NAME, TicketMarkdownParser
from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.ticket_repository import TicketRepository

NUMERIC_PATTERN = re.compile(r"\d+")


def _ticket_sort_key(ticket: Ticket) -> tuple[int, str]:
    """Sort key using parsed integer identifier for proper numeric ordering."""
    match = NUMERIC_PATTERN.search(ticket.id)
    numeric_val = int(match.group()) if match else 0
    return numeric_val, ticket.id


class DirectoryTicketStore(TicketRepository):
    """Scans and manages tickets stored as markdown files under docs/tickets/<spec-slug>/."""

    def __init__(
        self,
        root_dir: Path | str,
        parser: TicketMarkdownParser | None = None,
    ) -> None:
        self._root_dir = Path(root_dir)
        self._parser = parser or TicketMarkdownParser()

    @property
    def root_dir(self) -> Path:
        """Root directory of the ticket repository."""
        return self._root_dir

    def exists(self) -> bool:
        """Check if the backing queue directory exists."""
        return self._root_dir.is_dir()

    def _is_valid_ticket_file(self, path: Path) -> bool:
        """Check whether a path is a candidate ticket markdown file."""
        if not path.is_file():
            return False
        name = path.name
        if name.startswith("."):
            return False
        if name.endswith(".lock") or name.endswith(".tmp"):
            return False
        if name.lower() == "gotchas.md":
            return False
        return path.suffix.lower() == ".md"

    def _get_spec_directories(self) -> list[Path]:
        """Discover spec directories under root_dir.

        If root_dir itself contains direct ticket files or has no non-archive subdirectories,
        it is treated as the single active spec directory. Otherwise, returns sorted child
        directories excluding 'completed' and hidden folders.
        """
        if not self.exists():
            return []

        child_dirs = sorted(
            [
                d
                for d in self._root_dir.iterdir()
                if d.is_dir()
                and d.name != ARCHIVED_DIRECTORY_NAME
                and not d.name.startswith(".")
            ],
            key=lambda d: d.name,
        )

        direct_ticket_files = [
            f for f in self._root_dir.iterdir() if self._is_valid_ticket_file(f)
        ]

        if direct_ticket_files and not child_dirs:
            return [self._root_dir]

        if not child_dirs and self.exists():
            return [self._root_dir]

        return child_dirs

    def _scan_spec_dir(self, spec_dir: Path) -> list[Ticket]:
        """Scan a single spec directory for tickets, ignoring completed/ subfolders."""
        if not spec_dir.is_dir():
            return []

        tickets: list[Ticket] = []
        for file_path in spec_dir.iterdir():
            if not self._is_valid_ticket_file(file_path):
                continue
            try:
                ticket = self._parser.parse(file_path)
            except TicketFormatError as exc:
                if str(file_path) not in str(exc) and file_path.name not in str(exc):
                    raise TicketFormatError(f"Malformed ticket file '{file_path}': {exc}") from exc
                raise
            tickets.append(ticket)

        return tickets

    def get_active_spec_slug(self) -> str | None:
        """Return the directory slug of the first spec containing pending tickets."""
        if not self.exists():
            return None

        for spec_dir in self._get_spec_directories():
            tickets = self._scan_spec_dir(spec_dir)
            has_pending = any(t.status == TicketStatus.PENDING for t in tickets)
            if has_pending:
                return spec_dir.name

        return None

    def list_pending(self, spec_slug: str | None = None) -> list[Ticket]:
        """List pending tickets in execution order.

        Args:
            spec_slug: Optional spec directory slug. If omitted, returns pending
                tickets for the active spec queue.
        """
        if not self.exists():
            return []

        target_dir: Path | None = None
        if spec_slug is not None:
            if self._root_dir.name == spec_slug:
                target_dir = self._root_dir
            else:
                candidate = self._root_dir / spec_slug
                if candidate.is_dir():
                    target_dir = candidate
                else:
                    return []
        else:
            active_slug = self.get_active_spec_slug()
            if active_slug is None:
                return []
            if self._root_dir.name == active_slug:
                target_dir = self._root_dir
            else:
                target_dir = self._root_dir / active_slug

        tickets = self._scan_spec_dir(target_dir)
        pending = [t for t in tickets if t.status == TicketStatus.PENDING]
        return sorted(pending, key=_ticket_sort_key)

    def list_all_pending(self) -> list[Ticket]:
        """List all pending tickets across all spec directories in execution order."""
        if not self.exists():
            return []

        all_pending: list[Ticket] = []
        for spec_dir in self._get_spec_directories():
            tickets = self._scan_spec_dir(spec_dir)
            pending = [t for t in tickets if t.status == TicketStatus.PENDING]
            all_pending.extend(sorted(pending, key=_ticket_sort_key))

        return all_pending

    def select_next_pending(self, spec_slug: str | None = None) -> Ticket | None:
        """Return the lowest-identifier pending ticket, or None if queue is empty."""
        pending = self.list_pending(spec_slug=spec_slug)
        return pending[0] if pending else None
