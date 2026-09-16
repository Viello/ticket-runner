"""Unit tests for GotchasStore and gotchas markdown normalizer."""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.adapters.markdown.gotchas_store import (
    DEFAULT_GOTCHAS_PATH,
    DEFAULT_SKELETON,
    GotchasStore,
    normalize_entry,
)
from runner.domain.exceptions import TicketFormatError


def _read_raw(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_raw(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)


def test_default_path() -> None:
    """Verify default store path points to docs/tickets/gotchas.md."""
    store = GotchasStore()
    assert store.path == DEFAULT_GOTCHAS_PATH


def test_load_returns_empty_string_when_file_missing(tmp_path: Path) -> None:
    """Verify load returns empty string when gotchas.md does not exist."""
    store = GotchasStore(tmp_path / "docs" / "tickets" / "gotchas.md")
    assert not store.path.exists()
    assert store.load() == ""


def test_load_returns_content_when_file_exists(tmp_path: Path) -> None:
    """Verify load returns entire file content when file exists."""
    target = tmp_path / "gotchas.md"
    content = "# Global Gotchas & Lessons Learned\n\n---\n\n### Sample\n- **Problem**: P\n- **Solution**: S\n"
    _write_raw(target, content)

    store = GotchasStore(target)
    assert store.load() == content


def test_append_creates_missing_file_with_skeleton_and_entry(tmp_path: Path) -> None:
    """Verify missing gotchas.md is initialized with standard skeleton before first entry."""
    target = tmp_path / "docs" / "tickets" / "gotchas.md"
    assert not target.exists()

    store = GotchasStore(target)
    entry = "### First Gotcha\n- **Problem**: Problem 1\n- **Solution**: Solution 1"
    appended = store.append([entry])

    assert len(appended) == 1
    assert target.is_file()

    content = _read_raw(target)
    assert content.startswith(DEFAULT_SKELETON)
    assert "### First Gotcha" in content
    assert "- **Problem**: Problem 1" in content
    assert "- **Solution**: Solution 1" in content
    assert content.endswith("\n")


def test_append_preserves_existing_content_and_headers(tmp_path: Path) -> None:
    """Verify existing content and section structure are preserved 100% byte-for-byte."""
    target = tmp_path / "gotchas.md"
    existing_header = DEFAULT_SKELETON + "\n### Existing Section\n- **Problem**: Pre-existing\n- **Solution**: Solved\n"
    _write_raw(target, existing_header)

    store = GotchasStore(target)
    new_entry = "### Newly Discovered Lesson\n- **Problem**: Brand new problem\n- **Solution**: Brand new fix"
    appended = store.append([new_entry])

    assert len(appended) == 1
    content = _read_raw(target)
    assert content.startswith(existing_header)
    assert "### Newly Discovered Lesson" in content
    assert "- **Problem**: Brand new problem" in content


def test_append_skips_exact_duplicates_already_in_file(tmp_path: Path) -> None:
    """Verify exact duplicate entries already in file are not appended again."""
    target = tmp_path / "gotchas.md"
    existing = DEFAULT_SKELETON + "\n### Duplicate Check\n- **Problem**: Problem A\n- **Solution**: Solution A\n"
    _write_raw(target, existing)

    store = GotchasStore(target)
    dup_entry = "### Duplicate Check\n- **Problem**: Problem A\n- **Solution**: Solution A"
    appended = store.append([dup_entry])

    assert appended == []
    assert _read_raw(target) == existing


def test_append_skips_duplicates_by_title(tmp_path: Path) -> None:
    """Verify entries matching an existing section title are skipped to prevent file bloat."""
    target = tmp_path / "gotchas.md"
    existing = DEFAULT_SKELETON + "\n### Duplicate Title\n- **Problem**: Problem A\n- **Solution**: Solution A\n"
    _write_raw(target, existing)

    store = GotchasStore(target)
    # Different problem text, but exact same title
    same_title_entry = "### Duplicate Title\n- **Problem**: Different variation\n- **Solution**: Another fix"
    appended = store.append([same_title_entry])

    assert appended == []
    assert _read_raw(target) == existing


def test_append_deduplicates_within_same_batch(tmp_path: Path) -> None:
    """Verify duplicates provided in the same new_gotchas batch are only appended once."""
    target = tmp_path / "gotchas.md"
    store = GotchasStore(target)

    batch = [
        "### Unique Gotcha One\n- **Problem**: P1\n- **Solution**: S1",
        "### Unique Gotcha One\n- **Problem**: P1\n- **Solution**: S1",
        "### Unique Gotcha Two\n- **Problem**: P2\n- **Solution**: S2",
    ]
    appended = store.append(batch)

    assert len(appended) == 2
    content = _read_raw(target)
    assert content.count("### Unique Gotcha One") == 1
    assert content.count("### Unique Gotcha Two") == 1


def test_append_empty_list_leaves_missing_file_untouched(tmp_path: Path) -> None:
    """Verify calling append([]) on missing file does not create it."""
    target = tmp_path / "gotchas.md"
    store = GotchasStore(target)
    appended = store.append([])
    assert appended == []
    assert not target.exists()


def test_append_empty_list_leaves_existing_file_untouched(tmp_path: Path) -> None:
    """Verify calling append([]) on existing file leaves it untouched."""
    target = tmp_path / "gotchas.md"
    _write_raw(target, DEFAULT_SKELETON)
    store = GotchasStore(target)
    appended = store.append([])
    assert appended == []
    assert _read_raw(target) == DEFAULT_SKELETON


def test_append_ignores_blank_entries(tmp_path: Path) -> None:
    """Verify empty or whitespace-only strings are ignored."""
    target = tmp_path / "gotchas.md"
    store = GotchasStore(target)
    appended = store.append(["", "   ", "\n\n"])
    assert appended == []
    assert not target.exists()


def test_preserves_crlf_line_endings(tmp_path: Path) -> None:
    """Verify existing CRLF endings in gotchas.md are preserved during append."""
    target = tmp_path / "gotchas.md"
    crlf_skeleton = DEFAULT_SKELETON.replace("\n", "\r\n")
    target.write_bytes(crlf_skeleton.encode("utf-8"))

    store = GotchasStore(target)
    store.append(["### CRLF Check\n- **Problem**: Windows line endings\n- **Solution**: Preserve them"])

    raw_bytes = target.read_bytes()
    assert b"\r\n" in raw_bytes
    content = raw_bytes.decode("utf-8")
    assert "\n" not in content.replace("\r\n", "")
    assert "### CRLF Check\r\n- **Problem**: Windows line endings\r\n- **Solution**: Preserve them" in content


def test_supports_unicode_characters(tmp_path: Path) -> None:
    """Verify Unicode symbols like ✓, ✗, and em-dash are written and read properly."""
    target = tmp_path / "gotchas.md"
    store = GotchasStore(target)

    entry = (
        "### Console Unicode Symbols (✓ / ✗)\n"
        "- **Problem**: Printing ✓ or ✗ fails on cp1252 consoles.\n"
        "- **Solution**: Use UTF-8 reconfigure or fallback markers [PASS] / [FAIL]."
    )
    appended = store.append([entry])
    assert len(appended) == 1

    content = store.load()
    assert "✓" in content
    assert "✗" in content
    assert "### Console Unicode Symbols (✓ / ✗)" in content


def test_atomic_write_cleans_up_temp_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify atomic write cleans up sibling .tmp on failure and original file is intact."""
    target = tmp_path / "gotchas.md"
    original_content = DEFAULT_SKELETON + "\n### Original\n- **Problem**: P\n- **Solution**: S\n"
    _write_raw(target, original_content)

    def failing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise PermissionError(13, "Access denied")

    monkeypatch.setattr("runner.adapters.markdown.atomic_write.os.replace", failing_replace)

    store = GotchasStore(target)
    with pytest.raises(TicketFormatError, match="atomically"):
        store.append(["### New Entry\n- **Problem**: P2\n- **Solution**: S2"])

    assert _read_raw(target) == original_content
    assert list(tmp_path.glob("*.tmp")) == []


def test_load_sections_parses_existing_sections(tmp_path: Path) -> None:
    """Verify load_sections extracts distinct markdown sections."""
    target = tmp_path / "gotchas.md"
    _write_raw(
        target,
        DEFAULT_SKELETON
        + "\n### Section One\n- **Problem**: P1\n- **Solution**: S1\n\n"
        + "### Section Two\n- **Problem**: P2\n- **Solution**: S2\n",
    )

    store = GotchasStore(target)
    sections = store.load_sections()
    assert len(sections) == 2
    assert sections[0].startswith("### Section One")
    assert sections[1].startswith("### Section Two")


# --- Normalization tests ---


def test_normalize_entry_already_formatted() -> None:
    """Verify an entry already formatted as ### Title with Problem/Solution is preserved."""
    raw = (
        "### Windows Subprocess Resolution\n"
        "- **Problem**: Calling asyncio on Windows fails without extension.\n"
        "- **Solution**: Resolve path with shutil.which."
    )
    normalized = normalize_entry(raw)
    assert normalized == raw


def test_normalize_entry_preserves_custom_markdown_under_heading() -> None:
    """Verify custom markdown under ### heading is preserved uncorrupted."""
    raw = (
        "### Custom Markdown Architecture\n"
        "Here are architectural notes:\n"
        "- Note 1: `use_lock()`\n"
        "- Note 2: **always** release\n\n"
        "```python\nlock.release()\n```"
    )
    normalized = normalize_entry(raw)
    assert normalized == raw


def test_normalize_entry_title_with_problem_solution_plain_text() -> None:
    """Verify title line followed by plain Problem/Solution lines is normalized."""
    raw = (
        "Windows Subprocess Resolution\n"
        "Problem: Calling asyncio fails on Windows without extension.\n"
        "Solution: Resolve binary path beforehand."
    )
    normalized = normalize_entry(raw)
    assert normalized == (
        "### Windows Subprocess Resolution\n"
        "- **Problem**: Calling asyncio fails on Windows without extension.\n"
        "- **Solution**: Resolve binary path beforehand."
    )


def test_normalize_entry_problem_solution_without_explicit_title() -> None:
    """Verify Problem/Solution without title derives title from problem text."""
    raw = (
        "Problem: Calling asyncio fails on Windows without extension.\n"
        "Solution: Resolve binary path beforehand."
    )
    normalized = normalize_entry(raw)
    assert normalized.startswith("### Calling asyncio fails on Windows without extension\n")
    assert "- **Problem**: Calling asyncio fails on Windows without extension." in normalized
    assert "- **Solution**: Resolve binary path beforehand." in normalized


def test_normalize_entry_semicolon_separated() -> None:
    """Verify freeform text with semicolon separator splits into problem and solution."""
    raw = "msvcrt.locking locks a byte range; seek to 0 and lock a fixed 1-byte range."
    normalized = normalize_entry(raw)
    assert normalized.startswith("### Msvcrt.locking locks a byte range\n")
    assert "- **Problem**: msvcrt.locking locks a byte range." in normalized
    assert "- **Solution**: Seek to 0 and lock a fixed 1-byte range." in normalized


def test_normalize_entry_em_dash_separated() -> None:
    """Verify freeform text with em-dash separator splits into problem and solution."""
    raw = "fcntl is unavailable on Windows — import it lazily inside the POSIX branch."
    normalized = normalize_entry(raw)
    assert normalized.startswith("### Fcntl is unavailable on Windows\n")
    assert "- **Problem**: fcntl is unavailable on Windows." in normalized
    assert "- **Solution**: Import it lazily inside the POSIX branch." in normalized


def test_normalize_entry_single_sentence() -> None:
    """Verify single sentence without solution sets Problem and default Solution."""
    raw = "Table refetch event fires twice if query key is not memoized."
    normalized = normalize_entry(raw)
    assert normalized.startswith("### Table refetch event fires twice if query key\n")
    assert "- **Problem**: Table refetch event fires twice if query key is not memoized." in normalized
    assert "- **Solution**: Not specified." in normalized


def test_normalize_entry_with_inline_colon_title() -> None:
    """Verify freeform text with 'Title: Problem' sets Title and Problem."""
    raw = "Sentinel Lock Cleanup: Ensure lock handle is closed on conflict."
    normalized = normalize_entry(raw)
    assert normalized.startswith("### Sentinel Lock Cleanup\n")
    assert "- **Problem**: Ensure lock handle is closed on conflict." in normalized
    assert "- **Solution**: Not specified." in normalized
