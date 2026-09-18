"""Unit tests for JsonStateStore adapter and FakeStateStore test double."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.filesystem.json_state_store import (
    DEFAULT_MAX_BYTES,
    JsonStateStore,
)
from runner.domain.exceptions import StateFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.ports.state_store import StateStore
from tests.fakes.fake_state_store import FakeStateStore


def test_port_conformance() -> None:
    """Both JsonStateStore and FakeStateStore conform to the StateStore protocol."""
    json_store = JsonStateStore()
    fake_store = FakeStateStore()

    assert isinstance(json_store, StateStore)
    assert isinstance(fake_store, StateStore)


def test_read_missing_file_returns_none(tmp_path: Path) -> None:
    """read() returns None when the file does not exist on disk."""
    store = JsonStateStore(path=tmp_path / "state.json")
    assert store.read() is None


def test_roundtrip_valid_object(tmp_path: Path) -> None:
    """Valid JSON object roundtrips exactly, is UTF-8, and leaves no .tmp sibling."""
    state_file = tmp_path / "state.json"
    store = JsonStateStore(path=state_file)

    doc: dict[str, Any] = {
        "selected_model": "deepseek/deepseek-chat",
        "nested": {
            "retries": 3,
            "active": True,
            "items": ["a", "b", "c"],
        },
        "unicode_label": "DeepSeek 🧠 ñoñó",
    }
    store.write(doc)

    assert state_file.is_file()
    assert not (tmp_path / "state.json.tmp").exists()

    # Raw bytes check: UTF-8 encoding and POSIX LF line endings
    raw_bytes = state_file.read_bytes()
    assert "DeepSeek 🧠 ñoñó".encode("utf-8") in raw_bytes
    assert b"\r\n" not in raw_bytes

    loaded = store.read()
    assert loaded == doc
    assert loaded is not None
    assert loaded["selected_model"] == "deepseek/deepseek-chat"
    assert loaded["nested"]["retries"] == 3
    assert loaded["nested"]["active"] is True
    assert loaded["nested"]["items"] == ["a", "b", "c"]
    assert loaded["unicode_label"] == "DeepSeek 🧠 ñoñó"


def test_write_creates_parent_directory(tmp_path: Path) -> None:
    """write() creates missing parent directories on demand."""
    deep_path = tmp_path / "nested" / "sub" / "state.json"
    store = JsonStateStore(path=deep_path)

    store.write({"initialized": True})
    assert deep_path.is_file()
    assert store.read() == {"initialized": True}


def test_write_overwrites_exact_document(tmp_path: Path) -> None:
    """write() overwrites exactly without reading or merging pre-existing keys."""
    state_file = tmp_path / "state.json"
    store = JsonStateStore(path=state_file)

    store.write({"key1": "original", "key2": 123})
    assert store.read() == {"key1": "original", "key2": 123}

    # Second write omits key1; it must NOT be preserved by the adapter
    store.write({"key3": "replacement"})
    assert store.read() == {"key3": "replacement"}


@pytest.mark.parametrize(
    "bad_content",
    [
        "{not valid json",
        '{"unclosed": "string',
        "",
        "   \n  \t ",
    ],
)
def test_malformed_json_raises_state_format_error(tmp_path: Path, bad_content: str) -> None:
    """Syntactically malformed JSON content raises StateFormatError."""
    state_file = tmp_path / "state.json"
    state_file.write_text(bad_content, encoding="utf-8")

    store = JsonStateStore(path=state_file)
    with pytest.raises(StateFormatError, match="malformed|empty"):
        store.read()


def test_invalid_utf8_raises_state_format_error(tmp_path: Path) -> None:
    """Non-UTF-8 bytes raise StateFormatError."""
    state_file = tmp_path / "state.json"
    state_file.write_bytes(b"\xff\xfe\x00\x01\x80\x81")

    store = JsonStateStore(path=state_file)
    with pytest.raises(StateFormatError, match="not valid UTF-8"):
        store.read()


@pytest.mark.parametrize(
    "root_value",
    [
        "[]",
        '["item1", "item2"]',
        '"string_root"',
        "12345",
        "true",
        "false",
        "null",
    ],
)
def test_non_object_root_raises_state_format_error(tmp_path: Path, root_value: str) -> None:
    """Valid JSON with a non-object root (list, string, number, bool, null) raises StateFormatError."""
    state_file = tmp_path / "state.json"
    state_file.write_text(root_value, encoding="utf-8")

    store = JsonStateStore(path=state_file)
    with pytest.raises(StateFormatError, match="expected JSON object"):
        store.read()


def test_deeply_nested_payload_raises_state_format_error(tmp_path: Path) -> None:
    """Deeply nested payload exceeding recursion limit raises StateFormatError, never leaks RecursionError."""
    state_file = tmp_path / "state.json"
    # Construct nesting deep enough to exceed the interpreter recursion limit
    depth = 25_000
    nested = '{"a":' * depth + '1' + '}' * depth
    state_file.write_text(nested, encoding="utf-8")

    store = JsonStateStore(path=state_file, max_bytes=10 * 1024 * 1024)
    with pytest.raises(StateFormatError, match="malformed"):
        store.read()


def test_payload_exceeding_byte_cap_raises_state_format_error(tmp_path: Path) -> None:
    """Payloads exceeding configured byte cap raise StateFormatError without exhausting memory."""
    state_file = tmp_path / "state.json"
    payload = {"long_content": "x" * 200}
    state_file.write_text(json.dumps(payload), encoding="utf-8")

    store = JsonStateStore(path=state_file, max_bytes=50)
    with pytest.raises(StateFormatError, match="exceeds byte cap"):
        store.read()


def test_default_byte_cap_raises_on_oversized_file(tmp_path: Path) -> None:
    """Default byte cap (1 MiB) prevents reading files larger than 1 MiB."""
    state_file = tmp_path / "state.json"
    # Write 1 MiB + 10 bytes
    state_file.write_bytes(b" " * (DEFAULT_MAX_BYTES + 10))

    store = JsonStateStore(path=state_file)
    with pytest.raises(StateFormatError, match="exceeds byte cap"):
        store.read()


def test_simulated_write_failure_cleans_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A write failure propagates the error and ensures no .tmp sibling remains."""
    state_file = tmp_path / "state.json"
    tmp_file = tmp_path / "state.json.tmp"
    store = JsonStateStore(path=state_file)

    def fail_replace(src: Any, dst: Any) -> None:
        # Verify the temp file exists at the point of replacement failure
        assert Path(src).exists()
        raise PermissionError("Simulated locked destination file")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(PermissionError, match="Simulated locked destination file"):
        store.write({"key": "value"})

    assert not state_file.exists()
    assert not tmp_file.exists()


def test_init_with_runtime_paths_and_defaults(tmp_path: Path) -> None:
    """JsonStateStore resolves path from RuntimePaths, custom path, or default."""
    rp = RuntimePaths(root_dir=tmp_path / "agent_dir")
    store_from_rp = JsonStateStore(rp)
    assert store_from_rp.path == tmp_path / "agent_dir" / "state.json"

    store_from_path = JsonStateStore(path=tmp_path / "custom.json")
    assert store_from_path.path == tmp_path / "custom.json"

    default_store = JsonStateStore()
    assert default_store.path == Path(".agent/state.json")


def test_fake_state_store_in_memory_semantics() -> None:
    """FakeStateStore exercises all port methods and test helper seams."""
    fake = FakeStateStore()

    # Initial state is empty / None
    assert fake.read() is None

    # Initial state passed to constructor
    fake_seeded = FakeStateStore({"selected_model": "test/model"})
    assert fake_seeded.read() == {"selected_model": "test/model"}

    # Write updates state and records calls
    fake.write({"key": "val1"})
    assert fake.read() == {"key": "val1"}
    assert fake.write_calls == [{"key": "val1"}]

    fake.write({"key": "val2"})
    assert fake.read() == {"key": "val2"}
    assert fake.write_calls == [{"key": "val1"}, {"key": "val2"}]

    # seed_state allows updating or clearing
    fake.seed_state({"reset": True})
    assert fake.read() == {"reset": True}
    fake.seed_state(None)
    assert fake.read() is None

    # Injected errors
    fake_read_err = FakeStateStore(read_error=StateFormatError("Corrupt"))
    with pytest.raises(StateFormatError, match="Corrupt"):
        fake_read_err.read()

    fake_write_err = FakeStateStore(write_error=OSError("Disk full"))
    with pytest.raises(OSError, match="Disk full"):
        fake_write_err.write({"test": 1})
