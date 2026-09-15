"""Ticket domain entity, status enumeration, and invariants."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

from runner.domain.exceptions import TicketFormatError

TICKET_ID_PATTERN = re.compile(r"^T\d{3,}$")

_SECTION_FIELDS = ("requirements", "acceptance_criteria", "gotchas")


class TicketStatus(Enum):
    """Execution status values for a Ticket."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"


def parse_ticket_status(value: object, source: str | None = None) -> TicketStatus:
    """Coerce a raw value into a TicketStatus, raising TicketFormatError when unknown.

    Args:
        value: Raw status value such as ``"pending"`` or a TicketStatus member.
        source: Optional context (e.g. a file path) appended to the error message.
    """
    try:
        return TicketStatus(value)
    except (ValueError, TypeError):
        valid = ", ".join(status.value for status in TicketStatus)
        location = f" in {source}" if source else ""
        raise TicketFormatError(
            f"Invalid Status value {value!r}{location}. Valid statuses: {valid}"
        ) from None


@dataclass(frozen=True)
class Ticket:
    """A discrete unit of work parsed from a ticket markdown file."""

    id: str
    title: str
    status: TicketStatus
    spec_path: str
    requirements: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    gotchas: tuple[str, ...]
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not TICKET_ID_PATTERN.match(self.id):
            raise TicketFormatError(
                f"Malformed ticket identifier: {self.id!r}. Expected format 'T<NNN>' (e.g. 'T006')"
            )

        if not isinstance(self.title, str) or not self.title.strip():
            raise TicketFormatError(f"Ticket title must be a non-empty string, got: {self.title!r}")

        if not isinstance(self.spec_path, str) or not self.spec_path.strip():
            raise TicketFormatError(
                f"Ticket spec_path must be a non-empty string, got: {self.spec_path!r}"
            )

        if not isinstance(self.status, TicketStatus):
            object.__setattr__(self, "status", parse_ticket_status(self.status))

        for field in _SECTION_FIELDS:
            value = getattr(self, field)
            if isinstance(value, str):
                raise TicketFormatError(
                    f"Ticket {field} must be a tuple of strings, got a single string: {value!r}"
                )
            if not isinstance(value, tuple):
                try:
                    value = tuple(value)
                except TypeError:
                    raise TicketFormatError(
                        f"Ticket {field} must be a sequence of strings, got: {value!r}"
                    ) from None
                object.__setattr__(self, field, value)
            for entry in value:
                if not isinstance(entry, str):
                    raise TicketFormatError(
                        f"Ticket {field} entries must be strings, got: {entry!r}"
                    )

        if not isinstance(self.path, Path):
            try:
                object.__setattr__(self, "path", Path(self.path))
            except TypeError:
                raise TicketFormatError(f"Ticket path must be a Path, got: {self.path!r}") from None
