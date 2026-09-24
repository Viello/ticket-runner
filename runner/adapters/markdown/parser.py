"""Ticket markdown parser with spec linkage resolution."""

from __future__ import annotations

from pathlib import Path
import re

from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import Ticket, TicketStatus, parse_ticket_status

ARCHIVED_DIRECTORY_NAME = "completed"

HEADER_PATTERN = re.compile(r"^#\s*(?P<id>T\d{3,})(?:\s*[—–-]\s*(?P<title>\S.*?))?\s*$")
METADATA_PATTERN = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _-]*):\s*(?P<value>.*?)\s*$")
SECTION_PATTERN = re.compile(r"^###\s+(?P<name>.+?)\s*$")
BULLET_PATTERN = re.compile(r"^\s*-\s+(?P<text>\S.*?)\s*$")

SECTION_FIELDS = {
    "requirements": "requirements",
    "acceptance criteria": "acceptance_criteria",
    "gotchas": "gotchas",
}


class TicketMarkdownParser:
    """Parses individual ticket markdown files into Ticket entities."""

    def parse(self, path: Path | str) -> Ticket:
        """Parse a ticket file into a Ticket.

        Args:
            path: Path to the ticket markdown file.

        Returns:
            Parsed and validated Ticket entity.

        Raises:
            TicketFormatError: If the file is unreadable or malformed.
        """
        ticket_path = Path(path)
        try:
            with ticket_path.open("r", encoding="utf-8-sig", newline="") as handle:
                text = handle.read()
        except OSError as exc:
            raise TicketFormatError(f"Cannot read ticket file '{ticket_path}': {exc}") from exc

        lines = text.splitlines()
        title_index = self._title_index(lines, ticket_path)
        ticket_id, title = self._parse_title(lines[title_index], ticket_path)
        metadata, region_end = self._parse_metadata(lines, title_index)
        sections = self._parse_sections(lines[region_end:])
        smoke_scenarios = self._parse_smoke_scenarios(lines[region_end:])

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
            smoke_scenarios=smoke_scenarios,
        )

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

    def _parse_metadata(self, lines: list[str], title_index: int) -> tuple[dict[str, str], int]:
        metadata: dict[str, str] = {}
        index = title_index + 1
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped or stripped.startswith("#"):
                break
            match = METADATA_PATTERN.match(lines[index])
            if match:
                key = match.group("key").strip().lower()
                metadata.setdefault(key, match.group("value").strip())
            index += 1
        return metadata, index

    def _parse_status(self, metadata: dict[str, str], path: Path) -> TicketStatus:
        raw = metadata.get("status")
        if raw is None:
            raise TicketFormatError(f"Missing 'Status:' header in ticket file '{path}'")
        return parse_ticket_status(raw, source=f"ticket file '{path}'")

    def _parse_security_required(self, metadata: dict[str, str]) -> bool:
        raw = metadata.get("security")
        if raw is None:
            return False
        return raw.strip().lower() == "required"

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

    def _parse_sections(self, lines: list[str]) -> dict[str, tuple[str, ...]]:
        found: dict[str, list[str]] = {field: [] for field in SECTION_FIELDS.values()}
        current: str | None = None
        for line in lines:
            heading = SECTION_PATTERN.match(line)
            if heading:
                current = SECTION_FIELDS.get(heading.group("name").strip().lower())
                continue
            if current is None:
                continue
            bullet = BULLET_PATTERN.match(line)
            if bullet:
                found[current].append(bullet.group("text").strip())
        return {field: tuple(entries) for field, entries in found.items()}

    def _parse_smoke_scenarios(self, lines: list[str]) -> tuple[dict[str, Any], ...]:
        in_smoke = False
        scenarios: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        current_field: str | None = None

        scenario_heading_re = re.compile(
            r"^\*\*(?:Scenario:)?\s*(?P<name>.+?)\*\*\s*$|^(?:-\s+)?Scenario:\s*(?P<alt_name>.+?)$",
            re.IGNORECASE,
        )
        field_re = re.compile(
            r"^\s*-\s+(?P<field>Setup|Why|Steps|Expected):\s*(?P<rest>.*)$",
            re.IGNORECASE,
        )

        for line in lines:
            heading = SECTION_PATTERN.match(line)
            if heading:
                name = heading.group("name").strip().lower()
                if name == "smoke scenarios":
                    in_smoke = True
                    continue
                else:
                    in_smoke = False
                    if current:
                        scenarios.append(current)
                        current = None
                    continue

            if not in_smoke:
                continue

            sc_match = scenario_heading_re.match(line.strip())
            if sc_match:
                if current:
                    scenarios.append(current)
                name_val = sc_match.group("name") or sc_match.group("alt_name") or ""
                current = {
                    "name": name_val.strip(),
                    "setup": "",
                    "why": "",
                    "steps": "",
                    "expected": "",
                }
                current_field = None
                continue

            f_match = field_re.match(line)
            if f_match and current is not None:
                field_name = f_match.group("field").lower()
                rest = f_match.group("rest").strip()
                current[field_name] = rest
                current_field = field_name
                continue

            if current is not None and current_field is not None and line.strip():
                if current[current_field]:
                    current[current_field] += "\n" + line.strip()
                else:
                    current[current_field] = line.strip()

        if current:
            scenarios.append(current)

        return tuple(scenarios)
