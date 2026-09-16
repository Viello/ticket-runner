"""Unit tests for RuntimePaths frozen value object and directory helpers."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest

from runner.domain.runtime_paths import DEFAULT_AGENT_DIR, RuntimePaths


def test_default_root_dir() -> None:
    paths = RuntimePaths()
    assert paths.root_dir == DEFAULT_AGENT_DIR
    assert paths.root_dir == Path(".agent")


def test_custom_root_dir_and_string_coercion() -> None:
    paths_str = RuntimePaths(root_dir="custom/agent")
    assert paths_str.root_dir == Path("custom/agent")

    custom_path = Path("another/location/.agent")
    paths_obj = RuntimePaths(root_dir=custom_path)
    assert paths_obj.root_dir == custom_path


def test_directory_properties() -> None:
    paths = RuntimePaths()
    assert paths.signals_dir == Path(".agent/signals")
    assert paths.questions_dir == Path(".agent/questions")
    assert paths.checkpoints_dir == Path(".agent/checkpoints")
    assert paths.logs_dir == Path(".agent/logs")


def test_ready_signal_path_embeds_ticket_id() -> None:
    paths = RuntimePaths()
    assert paths.ready_signal_path("T015") == Path(".agent/signals/T015_ready.json")
    assert paths.ready_signal_path("T999") == Path(".agent/signals/T999_ready.json")


def test_question_path_embeds_ticket_id() -> None:
    paths = RuntimePaths()
    assert paths.question_path("T015") == Path(".agent/questions/T015.json")
    # Both question_path and question_file_path aliases supported
    assert paths.question_file_path("T015") == Path(".agent/questions/T015.json")


def test_checkpoint_path_embeds_ticket_id() -> None:
    paths = RuntimePaths()
    assert paths.checkpoint_dir("T015") == Path(".agent/checkpoints/T015")
    assert paths.checkpoint_path("T015") == Path(".agent/checkpoints/T015/handoff.md")


def test_session_log_paths_embed_ticket_and_session_ids() -> None:
    paths = RuntimePaths()
    expected_jsonl = Path(".agent/logs/T015_session_ses_01ABC.jsonl")
    assert paths.session_log_path("T015", "ses_01ABC") == expected_jsonl
    assert paths.session_jsonl_path("T015", "ses_01ABC") == expected_jsonl

    expected_stderr = Path(".agent/logs/T015_session_ses_01ABC.stderr.log")
    assert paths.session_stderr_path("T015", "ses_01ABC") == expected_stderr
    assert paths.session_stderr_log_path("T015", "ses_01ABC") == expected_stderr


def test_is_frozen_value_object() -> None:
    paths = RuntimePaths()
    with pytest.raises(FrozenInstanceError):
        paths.root_dir = Path("other")  # type: ignore[misc]


def test_empty_path_edge_resolution() -> None:
    paths_empty_path = RuntimePaths(root_dir=Path(""))
    assert paths_empty_path.root_dir == Path("")
    assert paths_empty_path.signals_dir == Path("signals")
    assert paths_empty_path.questions_dir == Path("questions")
    assert paths_empty_path.checkpoints_dir == Path("checkpoints")
    assert paths_empty_path.logs_dir == Path("logs")
    assert paths_empty_path.ready_signal_path("T015") == Path("signals/T015_ready.json")
    assert paths_empty_path.question_path("T015") == Path("questions/T015.json")
    assert paths_empty_path.checkpoint_path("T015") == Path("checkpoints/T015/handoff.md")
    assert paths_empty_path.session_log_path("T015", "ses_01") == Path("logs/T015_session_ses_01.jsonl")
    assert paths_empty_path.session_stderr_path("T015", "ses_01") == Path("logs/T015_session_ses_01.stderr.log")

    paths_empty_str = RuntimePaths(root_dir="")
    assert paths_empty_str.root_dir == Path("")
    assert paths_empty_str.signals_dir == Path("signals")
    assert paths_empty_str.ready_signal_path("T015") == Path("signals/T015_ready.json")


def test_no_disk_io_on_init_or_path_computation(tmp_path: Path) -> None:
    agent_root = tmp_path / ".agent"
    paths = RuntimePaths(root_dir=agent_root)

    # Calling path methods must not create anything on disk
    _ = paths.signals_dir
    _ = paths.questions_dir
    _ = paths.checkpoints_dir
    _ = paths.logs_dir
    _ = paths.ready_signal_path("T015")
    _ = paths.question_path("T015")
    _ = paths.checkpoint_path("T015")
    _ = paths.session_log_path("T015", "ses_01")
    _ = paths.session_stderr_path("T015", "ses_01")

    assert not agent_root.exists()


def test_directory_creation_helpers_on_demand(tmp_path: Path) -> None:
    agent_root = tmp_path / "sandbox" / ".agent"
    paths = RuntimePaths(root_dir=agent_root)

    assert not agent_root.exists()

    signals = paths.ensure_signals_dir()
    assert signals == agent_root / "signals"
    assert signals.is_dir()

    questions = paths.ensure_questions_dir()
    assert questions == agent_root / "questions"
    assert questions.is_dir()

    checkpoints_dir = paths.ensure_checkpoints_dir()
    assert checkpoints_dir == agent_root / "checkpoints"
    assert checkpoints_dir.is_dir()

    ticket_cp = paths.ensure_checkpoint_dir("T015")
    assert ticket_cp == agent_root / "checkpoints" / "T015"
    assert ticket_cp.is_dir()

    logs = paths.ensure_logs_dir()
    assert logs == agent_root / "logs"
    assert logs.is_dir()


def test_ensure_parent_dir(tmp_path: Path) -> None:
    paths = RuntimePaths(root_dir=tmp_path / ".agent")

    target = tmp_path / "somewhere" / "nested" / "file.txt"
    parent = paths.ensure_parent_dir(target)
    assert parent == tmp_path / "somewhere" / "nested"
    assert parent.is_dir()

    # Empty parent edge: Path("file.txt").parent is Path("")
    standalone = Path("file.txt")
    p = paths.ensure_parent_dir(standalone)
    assert p == Path("")


def test_ensure_all_dirs(tmp_path: Path) -> None:
    agent_root = tmp_path / "sandbox" / ".agent"
    paths = RuntimePaths(root_dir=agent_root)

    paths.ensure_all_dirs(ticket_id="T015")
    assert paths.signals_dir.is_dir()
    assert paths.questions_dir.is_dir()
    assert paths.checkpoints_dir.is_dir()
    assert paths.checkpoint_dir("T015").is_dir()
    assert paths.logs_dir.is_dir()
