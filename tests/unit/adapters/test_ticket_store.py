"""Unit tests for the DirectoryTicketStore adapter."""

from pathlib import Path
import pytest

from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.domain.exceptions import TicketFormatError
from runner.domain.ticket import TicketStatus
from runner.ports.ticket_repository import TicketRepository


def _write_ticket(
    parent: Path,
    filename: str,
    ticket_id: str,
    status: str = "pending",
    title: str | None = None,
    spec: str | None = None,
) -> Path:
    """Helper to write a ticket file to disk."""
    parent.mkdir(parents=True, exist_ok=True)
    file_path = parent / filename
    title_part = f" — {title}" if title else ""
    spec_line = f"Spec: {spec}\n" if spec else ""
    content = (
        f"# {ticket_id}{title_part}\n"
        f"Status: {status}\n"
        f"{spec_line}\n"
        "### Requirements\n"
        "- Sample requirement.\n"
    )
    with file_path.open("w", encoding="utf-8", newline="") as f:
        f.write(content)
    return file_path


def test_conforms_to_ticket_repository_protocol(tmp_path: Path) -> None:
    store = DirectoryTicketStore(root_dir=tmp_path)
    assert isinstance(store, TicketRepository)

    from tests.fakes.fake_ticket_repository import FakeTicketRepository
    fake = FakeTicketRepository()
    assert isinstance(fake, TicketRepository)


def test_absent_root_directory_returns_empty_results(tmp_path: Path) -> None:
    absent = tmp_path / "does_not_exist"
    store = DirectoryTicketStore(root_dir=absent)

    assert store.exists() is False
    assert store.list_pending() == []
    assert store.list_all_pending() == []
    assert store.select_next_pending() is None
    assert store.get_active_spec_slug() is None


def test_empty_queue_directory_returns_empty_results(tmp_path: Path) -> None:
    store = DirectoryTicketStore(root_dir=tmp_path)

    assert store.exists() is True
    assert store.list_pending() == []
    assert store.list_all_pending() == []
    assert store.select_next_pending() is None
    assert store.get_active_spec_slug() is None


def test_numeric_identifier_ordering(tmp_path: Path) -> None:
    spec_dir = tmp_path / "01-sample"
    # Write out of order: T010, T002, T001, T009
    _write_ticket(spec_dir, "T010-ten.md", "T010", title="Ten")
    _write_ticket(spec_dir, "T002-two.md", "T002", title="Two")
    _write_ticket(spec_dir, "T001-one.md", "T001", title="One")
    _write_ticket(spec_dir, "T009-nine.md", "T009", title="Nine")

    store = DirectoryTicketStore(root_dir=tmp_path)
    pending = store.list_pending()

    # T010 must order after T009 (numeric order, not raw string)
    assert [t.id for t in pending] == ["T001", "T002", "T009", "T010"]
    assert store.select_next_pending().id == "T001"


def test_skip_completed_subfolder_and_nested_archive(tmp_path: Path) -> None:
    spec_dir = tmp_path / "01-sample"
    _write_ticket(spec_dir, "T002-active.md", "T002", status="pending")

    # In completed subfolder
    completed_dir = spec_dir / "completed"
    _write_ticket(completed_dir, "T001-archived.md", "T001", status="pending")

    # Nested subfolder under completed
    nested_completed = completed_dir / "archive-2026"
    _write_ticket(nested_completed, "T000-deep.md", "T000", status="pending")

    store = DirectoryTicketStore(root_dir=tmp_path)
    pending = store.list_pending()

    assert [t.id for t in pending] == ["T002"]
    assert store.select_next_pending().id == "T002"


def test_skip_gotchas_lock_and_tmp_artifacts(tmp_path: Path) -> None:
    spec_dir = tmp_path / "01-sample"
    _write_ticket(spec_dir, "T001-valid.md", "T001", status="pending")

    # Artifacts in root and spec dir
    (tmp_path / "gotchas.md").write_text("# Global Gotchas\n", encoding="utf-8")
    (tmp_path / ".queue.lock").write_text("lock", encoding="utf-8")
    (spec_dir / "gotchas.md").write_text("# Gotchas\n", encoding="utf-8")
    (spec_dir / ".queue.lock").write_text("lock", encoding="utf-8")
    (spec_dir / "T001.tmp").write_text("temp", encoding="utf-8")
    (spec_dir / "T001-valid.md.tmp").write_text("temp", encoding="utf-8")
    (spec_dir / ".hidden.md").write_text("# Hidden\nStatus: pending\n", encoding="utf-8")

    store = DirectoryTicketStore(root_dir=tmp_path)
    pending = store.list_pending()

    assert [t.id for t in pending] == ["T001"]
    assert store.select_next_pending().id == "T001"


def test_mixed_statuses_returns_lowest_pending_ticket(tmp_path: Path) -> None:
    spec_dir = tmp_path / "01-sample"
    _write_ticket(spec_dir, "T001-done.md", "T001", status="completed")
    _write_ticket(spec_dir, "T002-active.md", "T002", status="running")
    _write_ticket(spec_dir, "T003-pending.md", "T003", status="pending")
    _write_ticket(spec_dir, "T004-pending.md", "T004", status="pending")
    _write_ticket(spec_dir, "T005-skip.md", "T005", status="skipped")

    store = DirectoryTicketStore(root_dir=tmp_path)
    pending = store.list_pending()

    assert [t.id for t in pending] == ["T003", "T004"]
    next_ticket = store.select_next_pending()
    assert next_ticket is not None
    assert next_ticket.id == "T003"


def test_all_completed_or_skipped_returns_empty(tmp_path: Path) -> None:
    spec_dir = tmp_path / "01-sample"
    _write_ticket(spec_dir, "T001-done.md", "T001", status="completed")
    _write_ticket(spec_dir, "T002-skip.md", "T002", status="skipped")

    store = DirectoryTicketStore(root_dir=tmp_path)
    assert store.list_pending() == []
    assert store.select_next_pending() is None


def test_multiple_specs_active_spec_queue_selection(tmp_path: Path) -> None:
    spec1 = tmp_path / "01-spec"
    spec2 = tmp_path / "02-spec"
    spec3 = tmp_path / "03-spec"

    # spec1 is fully completed
    _write_ticket(spec1, "T001.md", "T001", status="completed")

    # spec2 has pending tickets
    _write_ticket(spec2, "T008.md", "T008", status="pending")
    _write_ticket(spec2, "T007.md", "T007", status="pending")

    # spec3 also has pending tickets
    _write_ticket(spec3, "T014.md", "T014", status="pending")

    store = DirectoryTicketStore(root_dir=tmp_path)

    # Active spec queue is 02-spec (first spec with pending tickets)
    assert store.get_active_spec_slug() == "02-spec"

    # list_pending defaults to active spec queue
    active_pending = store.list_pending()
    assert [t.id for t in active_pending] == ["T007", "T008"]
    assert store.select_next_pending().id == "T007"

    # list_all_pending returns across all specs in order
    all_pending = store.list_all_pending()
    assert [t.id for t in all_pending] == ["T007", "T008", "T014"]


def test_filter_by_explicit_spec_slug(tmp_path: Path) -> None:
    spec1 = tmp_path / "01-spec"
    spec2 = tmp_path / "02-spec"

    _write_ticket(spec1, "T001.md", "T001", status="pending")
    _write_ticket(spec2, "T007.md", "T007", status="pending")

    store = DirectoryTicketStore(root_dir=tmp_path)

    assert [t.id for t in store.list_pending(spec_slug="02-spec")] == ["T007"]
    assert store.select_next_pending(spec_slug="02-spec").id == "T007"

    assert store.list_pending(spec_slug="nonexistent") == []
    assert store.select_next_pending(spec_slug="nonexistent") is None


def test_malformed_ticket_surfaces_path_in_error(tmp_path: Path) -> None:
    spec_dir = tmp_path / "01-sample"
    spec_dir.mkdir(parents=True)
    broken_file = spec_dir / "T001-broken.md"
    broken_file.write_text("Not a valid ticket format", encoding="utf-8")

    store = DirectoryTicketStore(root_dir=tmp_path)

    with pytest.raises(TicketFormatError) as exc_info:
        store.list_pending()

    error_message = str(exc_info.value)
    assert "T001-broken.md" in error_message


def test_direct_spec_directory_as_root(tmp_path: Path) -> None:
    # Directly targeting a spec directory without parent specs
    spec_dir = tmp_path / "docs" / "tickets" / "01-sample"
    _write_ticket(spec_dir, "T002.md", "T002", status="pending")
    _write_ticket(spec_dir, "T001.md", "T001", status="pending")

    store = DirectoryTicketStore(root_dir=spec_dir)

    assert store.exists() is True
    assert store.get_active_spec_slug() == "01-sample"
    assert [t.id for t in store.list_pending()] == ["T001", "T002"]
    assert store.select_next_pending().id == "T001"
