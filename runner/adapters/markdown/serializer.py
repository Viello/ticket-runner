"""Non-destructive serializer for ticket header metadata."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import TicketStatus, parse_ticket_status

METADATA_KEY_ORDER = ("Status", "Completed", "Spec")
METADATA_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9 _-]*$")
METADATA_LINE_PATTERN = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _-]*):(?P<value>.*)$")
HEADING_PATTERN = re.compile(r"^\s*#")


class TicketMarkdownSerializer:
    """Updates only the header metadata region of a ticket file.

    All remaining markdown, comments, spacing, and line endings are preserved
    exactly as authored.
    """

    def update_header(
        self,
        path: Path | str,
        metadata: Mapping[str, str | TicketStatus],
    ) -> None:
        """Update or insert header metadata lines with an atomic write.

        Args:
            path: Path to the ticket markdown file.
            metadata: Mapping of header keys (e.g. 'Status', 'Completed') to values.

        Raises:
            TicketFormatError: If the file is missing/unreadable or metadata is invalid.
        """
        target = Path(path)
        if not target.is_file():
            raise TicketFormatError(f"Ticket file not found: '{target}'")

        try:
            with target.open("r", encoding="utf-8", newline="") as handle:
                text = handle.read()
        except OSError as exc:
            raise TicketFormatError(f"Cannot read ticket file '{target}': {exc}") from exc

        try:
            atomic_write_text(target, self._apply_metadata(target, text, metadata))
        except OSError as exc:
            raise TicketFormatError(
                f"Failed to update ticket file '{target}' atomically: {exc}. "
                "Ensure no other process (such as a text editor) has the file open."
            ) from exc

    def _apply_metadata(
        self,
        path: Path,
        text: str,
        metadata: Mapping[str, str | TicketStatus],
    ) -> str:
        lines = text.splitlines(keepends=True)
        region_start = self._metadata_region_start(lines, path)
        region_end = region_start
        while region_end < len(lines):
            stripped = lines[region_end].strip()
            if not stripped or HEADING_PATTERN.match(lines[region_end]):
                break
            region_end += 1

        newline = self._detect_newline(lines)
        normalized = self._normalize_metadata(path, metadata)

        for key in sorted(normalized, key=self._key_rank):
            value = normalized[key]
            existing = self._find_metadata_line(lines, region_start, region_end, key)
            if existing is not None:
                index, original_key = existing
                _, ending = self._split_ending(lines[index])
                lines[index] = f"{original_key}: {value}{ending}"
                continue
            insert_at = self._insertion_index(lines, region_start, region_end, key)
            if insert_at > 0:
                body, ending = self._split_ending(lines[insert_at - 1])
                if not ending:
                    lines[insert_at - 1] = body + newline
            lines.insert(insert_at, f"{key}: {value}{newline}")
            region_end += 1

        return "".join(lines)

    def _metadata_region_start(self, lines: list[str], path: Path) -> int:
        for index, line in enumerate(lines):
            if line.strip():
                return index + 1
        raise TicketFormatError(f"Ticket file '{path}' has no header line")

    def _normalize_metadata(
        self,
        path: Path,
        metadata: Mapping[str, str | TicketStatus],
    ) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for key, value in metadata.items():
            if not isinstance(key, str) or not METADATA_KEY_PATTERN.match(key):
                raise TicketFormatError(f"Invalid ticket metadata key {key!r} for '{path}'")
            if isinstance(value, TicketStatus):
                text = value.value
            elif isinstance(value, str):
                text = value.strip()
            else:
                raise TicketFormatError(
                    f"Ticket metadata value for '{key}' must be a string or TicketStatus, got: {value!r}"
                )
            if not text:
                raise TicketFormatError(f"Ticket metadata value for '{key}' must not be empty")
            if "\r" in text or "\n" in text:
                raise TicketFormatError(
                    f"Ticket metadata value for '{key}' must not contain newline characters"
                )
            if key.lower() == "status":
                text = parse_ticket_status(text, source=f"ticket file '{path}'").value
            normalized[key] = text
        return normalized

    def _find_metadata_line(
        self, lines: list[str], region_start: int, region_end: int, key: str
    ) -> tuple[int, str] | None:
        for index in range(region_start, region_end):
            match = METADATA_LINE_PATTERN.match(lines[index])
            if match and match.group("key").strip().lower() == key.lower():
                return index, match.group("key")
        return None

    def _insertion_index(
        self, lines: list[str], region_start: int, region_end: int, key: str
    ) -> int:
        rank = self._key_rank(key)
        position = region_start
        for index in range(region_start, region_end):
            if self._line_rank(lines[index]) > rank:
                break
            position = index + 1
        return position

    def _key_rank(self, key: str) -> int:
        for index, canonical in enumerate(METADATA_KEY_ORDER):
            if key.lower() == canonical.lower():
                return index
        return len(METADATA_KEY_ORDER)

    def _line_rank(self, line: str) -> int:
        match = METADATA_LINE_PATTERN.match(line)
        if match is None:
            return -1
        return self._key_rank(match.group("key").strip())

    @staticmethod
    def _detect_newline(lines: list[str]) -> str:
        for line in lines:
            _, ending = TicketMarkdownSerializer._split_ending(line)
            if ending:
                return ending
        return "\n"

    @staticmethod
    def _split_ending(line: str) -> tuple[str, str]:
        if line.endswith("\r\n"):
            return line[:-2], "\r\n"
        if line.endswith("\n"):
            return line[:-1], "\n"
        if line.endswith("\r"):
            return line[:-1], "\r"
        return line, ""
