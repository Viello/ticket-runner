from collections.abc import Mapping
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
from typing import Any

from runner.adapters.markdown.parser import ARCHIVED_DIRECTORY_NAME, TicketMarkdownParser
from runner.adapters.markdown.serializer import TicketMarkdownSerializer
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
        serializer: TicketMarkdownSerializer | None = None,
    ) -> None:
        self._root_dir = Path(root_dir)
        self._parser = parser or TicketMarkdownParser()
        self._serializer = serializer or TicketMarkdownSerializer()

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

    def _resolve_ticket_path(self, ticket: Ticket | Path | str) -> Path:
        """Resolve a ticket argument to an existing ticket file Path."""
        if isinstance(ticket, Ticket):
            source_path = Path(ticket.path)
        elif isinstance(ticket, Path):
            source_path = ticket
        elif isinstance(ticket, str):
            candidate = Path(ticket)
            if candidate.is_file():
                source_path = candidate
            elif (self._root_dir / candidate).is_file():
                source_path = self._root_dir / candidate
            else:
                matched: list[Path] = []
                ticket_str = ticket.strip()
                if self.exists():
                    for spec_dir in self._get_spec_directories():
                        for f in spec_dir.iterdir():
                            if self._is_valid_ticket_file(f):
                                if f.stem.startswith(ticket_str) or f.name.startswith(ticket_str):
                                    matched.append(f)
                if len(matched) == 1:
                    source_path = matched[0]
                elif len(matched) > 1:
                    raise TicketFormatError(
                        f"Ambiguous ticket identifier '{ticket}': matches multiple files: {[str(m) for m in matched]}"
                    )
                else:
                    source_path = candidate
        else:
            raise TicketFormatError(f"Unsupported ticket argument type: {type(ticket).__name__}")

        if not source_path.is_file():
            raise TicketFormatError(f"Ticket file not found: '{source_path}'")

        if source_path.parent.name == ARCHIVED_DIRECTORY_NAME:
            raise TicketFormatError(
                f"Ticket file '{source_path}' is already in '{ARCHIVED_DIRECTORY_NAME}' directory"
            )

        return source_path

    def _format_completed_at(self, completed_at: datetime | str | None) -> str:
        """Format and validate completed_at into a timezone-aware UTC ISO-8601 string ending in 'Z'."""
        if completed_at is None:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(completed_at, datetime):
            if completed_at.tzinfo is None:
                dt = completed_at.replace(tzinfo=timezone.utc)
            else:
                dt = completed_at.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(completed_at, str):
            text = completed_at.strip()
            if not text:
                raise TicketFormatError("Completed timestamp string must not be empty")
            try:
                if text.endswith("Z"):
                    parsed = datetime.fromisoformat(text[:-1] + "+00:00")
                elif "+" in text or text.count("-") >= 3:
                    parsed = datetime.fromisoformat(text)
                else:
                    raise ValueError("Timestamp must specify UTC timezone ('Z')")
                if parsed.tzinfo is None:
                    raise ValueError("Timestamp must be timezone-aware")
                return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception as exc:
                raise TicketFormatError(
                    f"Invalid Completed timestamp '{completed_at}': must be timezone-aware UTC ISO-8601 (ending in 'Z'): {exc}"
                ) from exc
        raise TicketFormatError(
            f"completed_at must be a datetime, ISO-8601 string, or None, got: {completed_at!r}"
        )

    def _format_skipped_metadata(
        self, details: str | Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Convert failure details into header metadata dictionary with Status: skipped."""
        metadata: dict[str, Any] = {"Status": TicketStatus.SKIPPED}
        if details is None:
            return metadata

        if isinstance(details, Mapping):
            for key, value in details.items():
                k = str(key).strip()
                if k.islower():
                    k = k.replace("_", " ").title()
                if isinstance(value, str):
                    flattened = " ".join(line.strip() for line in value.splitlines() if line.strip())
                    metadata[k] = flattened
                elif isinstance(value, (int, float)):
                    metadata[k] = str(value)
                elif isinstance(value, datetime):
                    if value.tzinfo is None:
                        dt = value.replace(tzinfo=timezone.utc)
                    else:
                        dt = value.astimezone(timezone.utc)
                    metadata[k] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    metadata[k] = str(value)
        elif isinstance(details, str):
            text = " ".join(line.strip() for line in details.splitlines() if line.strip())
            if text:
                metadata["Failure"] = text
        else:
            text = str(details).strip()
            if text:
                metadata["Failure"] = text

        return metadata

    def _relocate_ticket(self, source_path: Path, metadata: Mapping[str, Any]) -> Path:
        """Stamp header metadata and relocate ticket file into completed/ subfolder."""
        completed_dir = source_path.parent / ARCHIVED_DIRECTORY_NAME
        destination_path = completed_dir / source_path.name

        if destination_path.exists():
            raise TicketFormatError(
                f"Destination ticket file already exists: '{destination_path}'"
            )

        if not completed_dir.exists():
            completed_dir.mkdir(parents=True, exist_ok=True)

        gitkeep_path = completed_dir / ".gitkeep"
        if not gitkeep_path.exists():
            gitkeep_path.write_text("", encoding="utf-8")

        # Update metadata atomically on source file
        self._serializer.update_header(source_path, metadata)

        # Move to completed/ directory
        try:
            os.replace(source_path, destination_path)
        except OSError:
            shutil.move(str(source_path), str(destination_path))

        return destination_path

    def finalize_completed(
        self,
        ticket: Ticket | Path | str,
        completed_at: datetime | str | None = None,
    ) -> Path:
        """Mark a ticket as completed, stamp timestamp, and relocate to completed/.

        Args:
            ticket: Ticket entity, file Path, or identifier string.
            completed_at: Optional completion timestamp (datetime or ISO-8601 string).
                Defaults to current UTC time.

        Returns:
            Destination Path of the relocated ticket file.

        Raises:
            TicketFormatError: If ticket not found, already archived, destination
                collides, or timestamp formatting fails.
        """
        source_path = self._resolve_ticket_path(ticket)
        timestamp_str = self._format_completed_at(completed_at)
        metadata = {
            "Status": TicketStatus.COMPLETED,
            "Completed": timestamp_str,
        }
        return self._relocate_ticket(source_path, metadata)

    def finalize_skipped(
        self,
        ticket: Ticket | Path | str,
        details: str | Mapping[str, Any] | None = None,
    ) -> Path:
        """Mark a ticket as skipped, stamp failure details, and relocate to completed/.

        Args:
            ticket: Ticket entity, file Path, or identifier string.
            details: Optional failure reason or dictionary of failure metadata.

        Returns:
            Destination Path of the relocated ticket file.

        Raises:
            TicketFormatError: If ticket not found, already archived, or destination
                collides.
        """
        source_path = self._resolve_ticket_path(ticket)
        metadata = self._format_skipped_metadata(details)
        return self._relocate_ticket(source_path, metadata)
