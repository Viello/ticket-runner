"""Ticket markdown parser with spec linkage resolution."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import Ticket, TicketStatus, parse_ticket_status

ARCHIVED_DIRECTORY_NAME = "completed"

HEADER_PATTERN = re.compile(r"^#\s*(?P<id>T\d{3,})(?:\s*(?:[—–-]|:)\s*(?P<title>\S.*?))?\s*$")
METADATA_LINE_PATTERN = re.compile(
    r"^(?P<indent>\s*)(?:(?P<bold_inside>\*\*(?P<key_inside>[A-Za-z][A-Za-z0-9 _-]*?):\*\*)|(?P<bold_outside>\*\*(?P<key_outside>[A-Za-z][A-Za-z0-9 _-]*?)\*\*:)|(?P<flat_key>[A-Za-z][A-Za-z0-9 _-]*?):)(?P<value>.*)$"
)
SECTION_PATTERN = re.compile(r"^#{2,3}\s+(?P<name>.+?)\s*$")
CHECKBOX_PATTERN = re.compile(r"^\s*-\s*\[(?P<tick>[ xX])\]\s*(?P<text>\S.*?)\s*$")
BULLET_PATTERN = re.compile(r"^\s*-\s+(?P<text>\S.*?)\s*$")

SECTION_FIELDS = {
    "requirements": "requirements",
    "what to build": "requirements",
    "jump-start": "jump_start",
    "jump start": "jump_start",
    "jumpstart": "jump_start",
    "acceptance criteria": "acceptance_criteria",
    "smoke scenarios": "smoke_scenarios",
    "gotchas": "gotchas",
}

DIALECT_STATUS_MARKERS = ("ready-for-agent", "ready-for-human", "done")


def _raise_specimen_b_error(path: Path) -> None:
    raise TicketFormatError(
        f"Ticket file '{path}' uses the interactive 'to-tickets' (Human+AI) format, "
        "which is not supported for autonomous execution by Ticket Runner. "
        "Execute this ticket interactively with '/implement' or re-author it for "
        "autonomous execution using '/to-ticket-runner'."
    )


class TicketMarkdownParser:
    """Parses individual ticket markdown files into Ticket entities."""

    def parse(self, path: Path | str) -> Ticket:
        """Parse a ticket file into a Ticket.

        Args:
            path: Path to the ticket markdown file.

        Returns:
            Parsed and validated Ticket entity.

        Raises:
            TicketFormatError: If the file is unreadable, malformed, or uses the interactive dialect.
        """
        ticket_path = Path(path)
        try:
            with ticket_path.open("r", encoding="utf-8-sig", newline="") as handle:
                text = handle.read()
        except OSError as exc:
            raise TicketFormatError(f"Cannot read ticket file '{ticket_path}': {exc}") from exc

        lines = text.splitlines()

        # Check early dialect markers on raw text or lines
        self._check_raw_dialect_markers(lines, ticket_path)

        title_index = self._title_index(lines, ticket_path)
        ticket_id, title = self._parse_title(lines[title_index], ticket_path)
        metadata, region_end = self._parse_metadata(lines, title_index, ticket_path)
        sections = self._parse_sections(lines[region_end:])

        return Ticket(
            id=ticket_id,
            title=title,
            status=self._parse_status(metadata, ticket_path),
            spec_path=self._resolve_spec_path(metadata, ticket_path),
            requirements=sections["requirements"],
            acceptance_criteria=sections["acceptance_criteria"],
            gotchas=sections["gotchas"],
            path=ticket_path,
            security_required=self._parse_security_required(metadata),
            reasoning=self._parse_reasoning(metadata),
            mode=self._parse_mode(metadata, ticket_path),
            status_note=self._parse_status_note(metadata),
            jump_start=sections["jump_start"],
            checked_criteria=sections["checked_criteria"],
        )

    def _check_raw_dialect_markers(self, lines: list[str], path: Path) -> None:
        has_headings = any(re.match(r"^#{2,3}\s+", line) for line in lines)
        has_inline_sections = any(
            re.match(r"^\s*\*\*(?:what to build|jump-start|jump start):\*\*", line, re.IGNORECASE)
            for line in lines
        )
        if has_inline_sections and not has_headings:
            _raise_specimen_b_error(path)

    def _title_index(self, lines: list[str], path: Path) -> int:
        for index, line in enumerate(lines):
            if line.strip():
                return index
        raise TicketFormatError(f"Ticket file '{path}' has no header line")

    def _parse_title(self, line: str, path: Path) -> tuple[str, str]:
        match = HEADER_PATTERN.match(line)
        if match is None:
            raise TicketFormatError(
                f"Malformed ticket header in '{path}': expected '# T<NNN> — <Title>', "
                f"got: {line.strip()!r}"
            )
        ticket_id = match.group("id")
        title = match.group("title") or ticket_id
        return ticket_id, title

    def _parse_metadata(
        self, lines: list[str], title_index: int, path: Path
    ) -> tuple[dict[str, str], int]:
        metadata: dict[str, str] = {}
        index = title_index + 1
        while index < len(lines) and not lines[index].strip():
            index += 1

        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped or stripped.startswith("#"):
                break
            match = METADATA_LINE_PATTERN.match(lines[index])
            if match:
                key = (
                    match.group("key_inside")
                    or match.group("key_outside")
                    or match.group("flat_key")
                )
                if key:
                    metadata.setdefault(key.strip().lower(), match.group("value").strip())
            index += 1

        if "labels" in metadata or "parent" in metadata:
            _raise_specimen_b_error(path)

        return metadata, index

    def _parse_status(self, metadata: dict[str, str], path: Path) -> TicketStatus:
        raw = metadata.get("status")
        if raw is None:
            raise TicketFormatError(f"Missing 'Status:' header in ticket file '{path}'")
        clean = raw.strip().lower()
        if any(clean.startswith(marker) for marker in DIALECT_STATUS_MARKERS):
            _raise_specimen_b_error(path)
        return parse_ticket_status(raw, source=f"ticket file '{path}'")

    def _parse_mode(self, metadata: dict[str, str], path: Path) -> str:
        raw = metadata.get("mode")
        if raw is None:
            return "AFK"
        clean = raw.strip().upper()
        if clean not in ("AFK", "HITL"):
            raise TicketFormatError(
                f"Invalid Mode value {raw!r} in ticket file '{path}'. Expected 'AFK' or 'HITL'."
            )
        return clean

    def _parse_status_note(self, metadata: dict[str, str]) -> str | None:
        note = metadata.get("status note") or metadata.get("status_note")
        return note.strip() if note is not None else None

    def _parse_security_required(self, metadata: dict[str, str]) -> bool:
        raw = metadata.get("security")
        if raw is None:
            return False
        tokens = raw.strip().split()
        if not tokens:
            return False
        return tokens[0].lower() in ("required", "true", "yes")

    def _parse_reasoning(self, metadata: dict[str, str]) -> str:
        raw = metadata.get("reasoning")
        if raw is None:
            return ""
        return raw.strip()

    def _resolve_spec_path(self, metadata: dict[str, str], path: Path) -> str:
        explicit = metadata.get("spec", "").strip()
        if explicit:
            return explicit
        directory = path.parent
        if directory.name == ARCHIVED_DIRECTORY_NAME and directory.parent.name:
            directory = directory.parent
        return f"docs/specs/{directory.name}.md"

    def _parse_sections(self, lines: list[str]) -> dict[str, Any]:
        section_lines: dict[str, list[str]] = {
            "requirements": [],
            "jump_start": [],
            "acceptance_criteria": [],
            "smoke_scenarios": [],
            "gotchas": [],
        }
        current: str | None = None
        for line in lines:
            heading = SECTION_PATTERN.match(line)
            if heading:
                current = SECTION_FIELDS.get(heading.group("name").strip().lower())
                continue
            if current is not None and current in section_lines:
                section_lines[current].append(line)

        # 1. requirements
        req_items: list[str] = []
        current_para: list[str] = []

        def flush_para() -> None:
            if current_para:
                text = " ".join(line.strip() for line in current_para if line.strip())
                if text:
                    req_items.append(text)
                current_para.clear()

        for line in section_lines["requirements"]:
            stripped = line.strip()
            if not stripped:
                flush_para()
                continue
            bullet_match = BULLET_PATTERN.match(line)
            if bullet_match:
                flush_para()
                req_items.append(bullet_match.group("text").strip())
            else:
                current_para.append(stripped)
        flush_para()

        # 2. jump_start
        jump_items: list[str] = []
        current_jump: list[str] = []

        def flush_jump() -> None:
            if current_jump:
                text = " ".join(line.strip() for line in current_jump if line.strip())
                if text:
                    jump_items.append(text)
                current_jump.clear()

        for line in section_lines["jump_start"]:
            stripped = line.strip()
            if not stripped:
                flush_jump()
                continue
            bullet_match = BULLET_PATTERN.match(line)
            if bullet_match:
                flush_jump()
                jump_items.append(bullet_match.group("text").strip())
            else:
                if line.startswith((" ", "\t")) and jump_items and not current_jump:
                    jump_items[-1] = f"{jump_items[-1]} {stripped}"
                else:
                    current_jump.append(stripped)
        flush_jump()

        # 3. acceptance_criteria & checked_criteria
        ac_items: list[str] = []
        checked_set: set[str] = set()

        for line in section_lines["acceptance_criteria"]:
            stripped = line.strip()
            if not stripped:
                continue
            cb_match = CHECKBOX_PATTERN.match(line)
            if cb_match:
                tick = cb_match.group("tick")
                text = cb_match.group("text").strip()
                ac_items.append(text)
                if tick.lower() == "x":
                    checked_set.add(text)
                continue
            bullet_match = BULLET_PATTERN.match(line)
            if bullet_match:
                text = bullet_match.group("text").strip()
                ac_items.append(text)
                continue
            if line.startswith((" ", "\t")) and ac_items:
                prev = ac_items[-1]
                updated = f"{prev} {stripped}"
                ac_items[-1] = updated
                if prev in checked_set:
                    checked_set.remove(prev)
                    checked_set.add(updated)

        # 4. gotchas
        gotcha_items: list[str] = []
        for line in section_lines["gotchas"]:
            bullet_match = BULLET_PATTERN.match(line)
            if bullet_match:
                gotcha_items.append(bullet_match.group("text").strip())
            elif line.startswith((" ", "\t")) and gotcha_items:
                gotcha_items[-1] = f"{gotcha_items[-1]} {line.strip()}"

        return {
            "requirements": tuple(req_items),
            "jump_start": tuple(jump_items),
            "acceptance_criteria": tuple(ac_items),
            "checked_criteria": frozenset(checked_set),
            "gotchas": tuple(gotcha_items),
        }

