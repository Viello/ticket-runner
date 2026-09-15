"""Unit tests for the TicketMarkdownParser adapter."""

from pathlib import Path

import pytest

from runner.adapters.markdown.parser import TicketMarkdownParser
from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import TicketStatus

WELL_FORMED_TICKET = """# T006 — Ticket domain entity, markdown parser, and atomic serializer
Status: pending
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Define `TicketStatus` with exactly `pending`, `running`, `completed`, `skipped`.
- Define a frozen `Ticket` domain dataclass.

### Acceptance Criteria
- Parsing a well-formed ticket file yields a `Ticket`.

### Gotchas
- Never record the commit SHA in ticket frontmatter.
"""


def _write_ticket(
    root: Path,
    content: str,
    slug: str = "02-queue-and-tickets",
    filename: str = "T006-ticket-entity-parser-and-serializer.md",
) -> Path:
    ticket_dir = root / "docs" / "tickets" / slug
    ticket_dir.mkdir(parents=True, exist_ok=True)
    path = ticket_dir / filename
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return path


def test_parse_well_formed_ticket(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path, WELL_FORMED_TICKET)

    ticket = TicketMarkdownParser().parse(path)

    assert ticket.id == "T006"
    assert ticket.title == "Ticket domain entity, markdown parser, and atomic serializer"
    assert ticket.status is TicketStatus.PENDING
    assert ticket.spec_path == "docs/specs/02-queue-and-tickets.md"
    assert ticket.requirements == (
        "Define `TicketStatus` with exactly `pending`, `running`, `completed`, `skipped`.",
        "Define a frozen `Ticket` domain dataclass.",
    )
    assert ticket.acceptance_criteria == ("Parsing a well-formed ticket file yields a `Ticket`.",)
    assert ticket.gotchas == ("Never record the commit SHA in ticket frontmatter.",)
    assert ticket.path == path


@pytest.mark.parametrize("status", ["pending", "running", "completed", "skipped"])
def test_parse_every_valid_status(tmp_path: Path, status: str) -> None:
    content = WELL_FORMED_TICKET.replace("Status: pending", f"Status: {status}")
    path = _write_ticket(tmp_path, content)

    assert TicketMarkdownParser().parse(path).status is TicketStatus(status)


def test_explicit_spec_header_wins_over_inference(tmp_path: Path) -> None:
    content = WELL_FORMED_TICKET.replace(
        "Spec: docs/specs/02-queue-and-tickets.md",
        "Spec: docs/specs/custom-spec.md",
    )
    path = _write_ticket(tmp_path, content)

    assert TicketMarkdownParser().parse(path).spec_path == "docs/specs/custom-spec.md"


def test_omitted_spec_header_infers_from_parent_directory(tmp_path: Path) -> None:
    content = WELL_FORMED_TICKET.replace("Spec: docs/specs/02-queue-and-tickets.md\n", "")
    path = _write_ticket(tmp_path, content, slug="03-custom-spec")

    assert TicketMarkdownParser().parse(path).spec_path == "docs/specs/03-custom-spec.md"


def test_omitted_spec_header_infers_through_completed_archive(tmp_path: Path) -> None:
    content = WELL_FORMED_TICKET.replace("Spec: docs/specs/02-queue-and-tickets.md\n", "")
    path = _write_ticket(tmp_path, content, slug="02-queue-and-tickets/completed")

    assert TicketMarkdownParser().parse(path).spec_path == "docs/specs/02-queue-and-tickets.md"


def test_optional_sections_default_to_empty_tuples(tmp_path: Path) -> None:
    content = (
        "# T007 — Scanner\n"
        "Status: pending\n"
        "\n"
        "### Requirements\n"
        "- Scan directories.\n"
    )
    path = _write_ticket(tmp_path, content, filename="T007-scanner.md")

    ticket = TicketMarkdownParser().parse(path)

    assert ticket.requirements == ("Scan directories.",)
    assert ticket.acceptance_criteria == ()
    assert ticket.gotchas == ()


def test_parse_accepts_crlf_line_endings(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path, WELL_FORMED_TICKET.replace("\n", "\r\n"))

    ticket = TicketMarkdownParser().parse(path)

    assert ticket.id == "T006"
    assert ticket.requirements[0].startswith("Define `TicketStatus`")


def test_parse_tolerates_completed_header(tmp_path: Path) -> None:
    content = WELL_FORMED_TICKET.replace(
        "Status: pending\n",
        "Status: completed\nCompleted: 2026-09-16T10:00:00Z\n",
    )
    path = _write_ticket(tmp_path, content, slug="01-doctor-and-git-ops")

    ticket = TicketMarkdownParser().parse(path)

    assert ticket.status is TicketStatus.COMPLETED
    assert ticket.spec_path == "docs/specs/02-queue-and-tickets.md"


def test_metadata_like_lines_in_body_are_ignored(tmp_path: Path) -> None:
    content = WELL_FORMED_TICKET + "\n```\nStatus: completed\nSpec: docs/specs/ignored.md\n```\n"
    path = _write_ticket(tmp_path, content)

    ticket = TicketMarkdownParser().parse(path)

    assert ticket.status is TicketStatus.PENDING
    assert ticket.spec_path == "docs/specs/02-queue-and-tickets.md"


def test_parse_rejects_invalid_status(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path, WELL_FORMED_TICKET.replace("Status: pending", "Status: bogus"))

    with pytest.raises(TicketFormatError, match="bogus"):
        TicketMarkdownParser().parse(path)


def test_parse_rejects_missing_status(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path, WELL_FORMED_TICKET.replace("Status: pending\n", ""))

    with pytest.raises(TicketFormatError, match="Status"):
        TicketMarkdownParser().parse(path)


def test_parse_rejects_malformed_header(tmp_path: Path) -> None:
    content = "Ticket Six\nStatus: pending\n\n### Requirements\n- Something.\n"
    path = _write_ticket(tmp_path, content)

    with pytest.raises(TicketFormatError, match="header"):
        TicketMarkdownParser().parse(path)


def test_parse_rejects_empty_file(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path, "")

    with pytest.raises(TicketFormatError, match="header"):
        TicketMarkdownParser().parse(path)


def test_parse_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "docs" / "tickets" / "T999-absent.md"

    with pytest.raises(TicketFormatError, match="T999-absent.md"):
        TicketMarkdownParser().parse(missing)


def test_parse_reports_file_path_on_format_error(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path, WELL_FORMED_TICKET.replace("Status: pending", "Status: nope"))

    with pytest.raises(TicketFormatError, match="T006-ticket-entity-parser-and-serializer.md"):
        TicketMarkdownParser().parse(path)
