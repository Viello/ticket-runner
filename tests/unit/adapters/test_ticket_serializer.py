"""Unit tests for the TicketMarkdownSerializer adapter."""

import os
from pathlib import Path

import pytest

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.adapters.markdown.serializer import TicketMarkdownSerializer
from runner.domain.exceptions import TicketFormatError

TICKET_TEMPLATE = """# T006 — Ticket domain entity, markdown parser, and atomic serializer
Status: pending
Spec: docs/specs/02-queue-and-tickets.md
<!-- author note: do not reformat -->

### Requirements
- Define `TicketStatus` with exactly four values.
- Keep repo style: frozen dataclasses.

### Acceptance Criteria
- Updates preserve custom formatting byte-for-byte.

### Gotchas
- Status: lines inside sections are body text, not metadata.
"""


def _write_ticket(tmp_path: Path, content: str = TICKET_TEMPLATE) -> Path:
    ticket_dir = tmp_path / "docs" / "tickets" / "02-queue-and-tickets"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    path = ticket_dir / "T006-ticket-entity-parser-and-serializer.md"
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return path


def _read(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def test_update_status_preserves_all_other_content(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    TicketMarkdownSerializer().update_header(path, {"Status": "completed"})

    expected = TICKET_TEMPLATE.replace("Status: pending", "Status: completed", 1)
    assert _read(path) == expected


def test_update_inserts_completed_after_status(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    TicketMarkdownSerializer().update_header(
        path,
        {"Status": "completed", "Completed": "2026-09-16T10:00:00Z"},
    )

    expected = TICKET_TEMPLATE.replace(
        "Status: pending\n",
        "Status: completed\nCompleted: 2026-09-16T10:00:00Z\n",
        1,
    )
    assert _read(path) == expected


def test_update_replaces_existing_metadata_in_place(tmp_path: Path) -> None:
    content = TICKET_TEMPLATE.replace(
        "Status: pending\n",
        "Status: running\nCompleted: 2026-01-01T00:00:00Z\n",
    )
    path = _write_ticket(tmp_path, content)

    TicketMarkdownSerializer().update_header(
        path,
        {"Status": "completed", "Completed": "2026-09-16T10:00:00Z"},
    )

    result = _read(path)
    assert "Status: completed" in result
    assert "Status: running" not in result
    assert result.count("Completed:") == 1
    assert "Completed: 2026-09-16T10:00:00Z" in result
    assert "Completed: 2026-01-01T00:00:00Z" not in result


def test_update_inserts_missing_status_before_spec(tmp_path: Path) -> None:
    content = TICKET_TEMPLATE.replace("Status: pending\n", "")
    path = _write_ticket(tmp_path, content)

    TicketMarkdownSerializer().update_header(path, {"Status": "completed"})

    expected = content.replace(
        "Spec: docs/specs/02-queue-and-tickets.md\n",
        "Status: completed\nSpec: docs/specs/02-queue-and-tickets.md\n",
        1,
    )
    assert _read(path) == expected


def test_update_appends_unknown_metadata_at_header_end(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    TicketMarkdownSerializer().update_header(path, {"Failure": "3 attempts exhausted"})

    expected = TICKET_TEMPLATE.replace(
        "<!-- author note: do not reformat -->\n",
        "<!-- author note: do not reformat -->\nFailure: 3 attempts exhausted\n",
        1,
    )
    assert _read(path) == expected


def test_update_preserves_body_metadata_like_lines(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    TicketMarkdownSerializer().update_header(path, {"Status": "skipped"})

    result = _read(path)
    assert result.count("Status:") == 2
    assert "- Status: lines inside sections are body text, not metadata." in result


def test_update_preserves_crlf_line_endings(tmp_path: Path) -> None:
    crlf_content = TICKET_TEMPLATE.replace("\n", "\r\n")
    path = _write_ticket(tmp_path, crlf_content)

    TicketMarkdownSerializer().update_header(
        path,
        {"Status": "completed", "Completed": "2026-09-16T10:00:00Z"},
    )

    expected = crlf_content.replace(
        "Status: pending\r\n",
        "Status: completed\r\nCompleted: 2026-09-16T10:00:00Z\r\n",
        1,
    )
    result = _read(path)
    assert result == expected
    assert result.count("\r\n") == result.count("\n")


def test_update_preserves_missing_trailing_newline(tmp_path: Path) -> None:
    content = TICKET_TEMPLATE.rstrip("\n")
    path = _write_ticket(tmp_path, content)

    TicketMarkdownSerializer().update_header(path, {"Status": "completed"})

    expected = content.replace("Status: pending", "Status: completed", 1)
    assert _read(path) == expected
    assert not _read(path).endswith("\n")


def test_update_leaves_no_temp_artifacts(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    TicketMarkdownSerializer().update_header(path, {"Status": "completed"})

    assert list(path.parent.glob("*.tmp")) == []


def test_update_replaces_target_atomically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _write_ticket(tmp_path)
    recorded: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        recorded.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr("runner.adapters.markdown.atomic_write.os.replace", spy)

    TicketMarkdownSerializer().update_header(path, {"Status": "completed"})

    assert len(recorded) == 1
    temp_path, target_path = recorded[0]
    assert target_path == path
    assert temp_path.name == path.name + ".tmp"
    assert not temp_path.exists()


def test_update_cleans_up_temp_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_ticket(tmp_path)

    def locked_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr("runner.adapters.markdown.atomic_write.os.replace", locked_replace)

    with pytest.raises(TicketFormatError, match="atomically"):
        TicketMarkdownSerializer().update_header(path, {"Status": "completed"})

    assert _read(path) == TICKET_TEMPLATE
    assert list(path.parent.glob("*.tmp")) == []


def test_atomic_write_removes_temp_when_encoding_fails(tmp_path: Path) -> None:
    target = tmp_path / "ticket.md"
    target.write_text("original", encoding="utf-8")

    with pytest.raises(UnicodeEncodeError):
        atomic_write_text(target, "not ascii encodable: ✓", encoding="ascii")

    assert target.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.glob("*.tmp")) == []


def test_update_rejects_invalid_status_without_touching_file(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    with pytest.raises(TicketFormatError, match="bogus"):
        TicketMarkdownSerializer().update_header(path, {"Status": "bogus"})

    assert _read(path) == TICKET_TEMPLATE
    assert list(path.parent.glob("*.tmp")) == []


def test_update_rejects_multiline_values(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    with pytest.raises(TicketFormatError, match="newline"):
        TicketMarkdownSerializer().update_header(path, {"Failure": "line one\nline two"})

    assert _read(path) == TICKET_TEMPLATE


def test_update_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "docs" / "tickets" / "T999-absent.md"

    with pytest.raises(TicketFormatError, match="T999-absent.md"):
        TicketMarkdownSerializer().update_header(missing, {"Status": "completed"})


def test_update_accepts_integer_metadata_value(tmp_path: Path) -> None:
    path = _write_ticket(tmp_path)

    TicketMarkdownSerializer().update_header(path, {"Attempts": 3})

    result = _read(path)
    assert "Attempts: 3" in result


def test_update_removes_metadata_when_value_is_none(tmp_path: Path) -> None:
    content = TICKET_TEMPLATE.replace(
        "Status: pending\n",
        "Status: pending\nCompleted: 2026-09-16T10:00:00Z\n",
    )
    path = _write_ticket(tmp_path, content)

    TicketMarkdownSerializer().update_header(path, {"Completed": None})

    result = _read(path)
    assert "Completed:" not in result
    assert "Status: pending" in result
