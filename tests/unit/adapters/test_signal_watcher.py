"""Unit tests for the filesystem SignalRepository adapter and its in-memory fake."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.domain.exceptions import SignalFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import QuestionSignal, QuestionType, ReadySignal, SignalStatus
from runner.ports.signal_repository import SignalRepository
from tests.fakes.fake_signal_repository import FakeSignalRepository

UTC = timezone.utc
TICKET_ID = "T027"


def _ready_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": TICKET_ID,
        "status": "ready_for_verification",
        "modified_files": ["runner/ports/signal_repository.py"],
        "self_review_notes": "Adapter and fake agree.",
        "new_gotchas": [],
        "timestamp": "2026-09-17T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def _question_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": TICKET_ID,
        "question": "Which signal store?",
        "type": "choice",
        "options": ["filesystem", "memory"],
        "status": "pending",
        "answer": None,
        "created_at": "2026-09-17T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def _ready_signal(**overrides: object) -> ReadySignal:
    fields: dict[str, object] = {
        "ticket_id": TICKET_ID,
        "status": SignalStatus.READY_FOR_VERIFICATION,
        "modified_files": ("runner/ports/signal_repository.py",),
        "self_review_notes": "Adapter and fake agree.",
        "new_gotchas": (),
        "timestamp": datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
        "scope": None,
    }
    fields.update(overrides)
    return ReadySignal(**fields)  # type: ignore[arg-type]


def _question_signal(**overrides: object) -> QuestionSignal:
    fields: dict[str, object] = {
        "ticket_id": TICKET_ID,
        "question": "Which signal store?",
        "type": QuestionType.CHOICE,
        "options": ("filesystem", "memory"),
        "status": SignalStatus.PENDING,
        "answer": None,
        "created_at": datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return QuestionSignal(**fields)  # type: ignore[arg-type]


def _write_raw(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _write_json(path: Path, payload: object) -> None:
    _write_raw(path, json.dumps(payload, indent=2) + "\n")


def _vanishing_read_text(path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make Path.read_text fail for one path as if it vanished mid-operation."""
    original_read_text = Path.read_text

    def vanishing_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == path:
            raise FileNotFoundError(str(self))
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", vanishing_read_text)


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def runtime_paths(tmp_path: Path) -> RuntimePaths:
    return RuntimePaths(root_dir=tmp_path / ".agent")


@pytest.fixture
def repository(runtime_paths: RuntimePaths) -> FilesystemSignalRepository:
    return FilesystemSignalRepository(runtime_paths)


# --- Protocol conformance ---


def test_adapter_and_fake_conform_to_signal_repository_protocol(
    repository: FilesystemSignalRepository,
) -> None:
    assert isinstance(repository, SignalRepository)
    assert isinstance(FakeSignalRepository(), SignalRepository)


# --- read_ready ---


def test_read_ready_round_trips_hand_written_json(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    _write_json(
        runtime_paths.ready_signal_path(TICKET_ID),
        _ready_payload(scope="adapters"),
    )

    signal = repository.read_ready(TICKET_ID)

    assert signal == _ready_signal(scope="adapters")


def test_read_ready_missing_file_returns_none(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    assert repository.read_ready(TICKET_ID) is None
    assert not runtime_paths.signals_dir.exists()


def test_read_ready_does_not_consume_the_file(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.ready_signal_path(TICKET_ID)
    _write_json(path, _ready_payload())

    repository.read_ready(TICKET_ID)

    assert path.is_file()


@pytest.mark.parametrize(
    "raw_text",
    [
        pytest.param("{ not json", id="invalid-json"),
        pytest.param("[]", id="non-object"),
        pytest.param(json.dumps({"ticket_id": TICKET_ID}), id="missing-fields"),
        pytest.param(json.dumps(_ready_payload(status="pending")), id="wrong-status"),
        pytest.param(json.dumps(_ready_payload(ticket_id="T999")), id="ticket-mismatch"),
    ],
)
def test_read_ready_malformed_file_raises_signal_format_error_naming_the_path(
    runtime_paths: RuntimePaths,
    repository: FilesystemSignalRepository,
    raw_text: str,
) -> None:
    path = runtime_paths.ready_signal_path(TICKET_ID)
    _write_raw(path, raw_text)

    with pytest.raises(SignalFormatError) as exc_info:
        repository.read_ready(TICKET_ID)

    assert str(path) in str(exc_info.value)


def test_read_ready_invalid_utf8_raises_signal_format_error(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.ready_signal_path(TICKET_ID)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe{")

    with pytest.raises(SignalFormatError):
        repository.read_ready(TICKET_ID)


def test_read_ready_treats_mid_operation_disappearance_as_absence(
    runtime_paths: RuntimePaths,
    repository: FilesystemSignalRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = runtime_paths.ready_signal_path(TICKET_ID)
    _write_json(path, _ready_payload())
    _vanishing_read_text(path, monkeypatch)

    assert repository.read_ready(TICKET_ID) is None


# --- read_pending_question ---


def test_read_pending_question_round_trips_hand_written_json(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    _write_json(runtime_paths.question_path(TICKET_ID), _question_payload())

    question = repository.read_pending_question(TICKET_ID)

    assert question == _question_signal()


def test_read_pending_question_text_type_round_trips_without_options(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    _write_json(
        runtime_paths.question_path(TICKET_ID),
        _question_payload(type="text", options=None),
    )

    question = repository.read_pending_question(TICKET_ID)

    assert question is not None
    assert question.type is QuestionType.TEXT
    assert question.options is None


def test_read_pending_question_missing_file_returns_none(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    assert repository.read_pending_question(TICKET_ID) is None
    assert not runtime_paths.questions_dir.exists()


def test_read_pending_question_hides_answered_files_without_deleting_them(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload(status="answered", answer="filesystem"))

    assert repository.read_pending_question(TICKET_ID) is None
    assert path.is_file()


@pytest.mark.parametrize(
    "raw_text",
    [
        pytest.param("{ not json", id="invalid-json"),
        pytest.param(json.dumps(_question_payload(type="choice", options=None)), id="choice-without-options"),
        pytest.param(json.dumps(_question_payload(status="answered", answer=None)), id="answered-without-answer"),
        pytest.param(json.dumps(_question_payload(ticket_id="T999")), id="ticket-mismatch"),
    ],
)
def test_read_pending_question_malformed_file_raises_signal_format_error_naming_the_path(
    runtime_paths: RuntimePaths,
    repository: FilesystemSignalRepository,
    raw_text: str,
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_raw(path, raw_text)

    with pytest.raises(SignalFormatError) as exc_info:
        repository.read_pending_question(TICKET_ID)

    assert str(path) in str(exc_info.value)


def test_read_pending_question_treats_mid_operation_disappearance_as_absence(
    runtime_paths: RuntimePaths,
    repository: FilesystemSignalRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload())
    _vanishing_read_text(path, monkeypatch)

    assert repository.read_pending_question(TICKET_ID) is None


# --- consume_ready ---


def test_consume_ready_deletes_only_the_ready_signal(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    ready_path = runtime_paths.ready_signal_path(TICKET_ID)
    question_path = runtime_paths.question_path(TICKET_ID)
    _write_json(ready_path, _ready_payload())
    _write_json(question_path, _question_payload())
    (ready_path.parent / f"{ready_path.name}.tmp").write_text("partial", encoding="utf-8")

    repository.consume_ready(TICKET_ID)

    assert not ready_path.exists()
    assert list(runtime_paths.signals_dir.glob("*.tmp")) == []
    assert question_path.is_file()


def test_consume_ready_is_idempotent_and_survives_absent_artifacts(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    repository.consume_ready(TICKET_ID)
    repository.consume_ready(TICKET_ID)

    assert repository.read_ready(TICKET_ID) is None
    assert not runtime_paths.signals_dir.exists()


# --- write_answer ---


def test_write_answer_flips_status_and_answer_while_preserving_every_other_field(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    payload = _question_payload(extra_note="kept for audit")
    _write_json(path, payload)

    answered = repository.write_answer(TICKET_ID, "filesystem")

    assert answered.status is SignalStatus.ANSWERED
    assert answered.answer == "filesystem"
    assert repository.read_pending_question(TICKET_ID) is None

    on_disk = _read_json(path)
    assert on_disk == {**payload, "status": "answered", "answer": "filesystem"}


def test_write_answer_preserves_created_at_text_verbatim(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload())

    repository.write_answer(TICKET_ID, "filesystem")

    on_disk = _read_json(path)
    assert on_disk["created_at"] == "2026-09-17T10:00:00Z"


def test_write_answer_emits_stable_utf8_json_with_trailing_newline(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload(question="Skeleton o esqueleto?"))

    repository.write_answer(TICKET_ID, "filesystem")
    first = path.read_bytes()
    repository.write_answer(TICKET_ID, "filesystem")

    assert path.read_bytes() == first
    assert first.endswith(b"\n")
    assert not first.endswith(b"\r\n")
    assert "Skeleton o esqueleto?" in first.decode("utf-8")
    assert _read_json(path)["answer"] == "filesystem"


def test_write_answer_leaves_no_tmp_siblings(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload())

    repository.write_answer(TICKET_ID, "filesystem")

    assert list(runtime_paths.questions_dir.glob("*.tmp")) == []


def test_write_answer_without_a_question_file_raises_signal_format_error(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    with pytest.raises(SignalFormatError):
        repository.write_answer(TICKET_ID, "filesystem")


def test_write_answer_malformed_question_file_raises_signal_format_error(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload(type="choice", options=None))

    with pytest.raises(SignalFormatError) as exc_info:
        repository.write_answer(TICKET_ID, "filesystem")

    assert str(path) in str(exc_info.value)


def test_write_answer_rejects_blank_answer_without_rewriting_the_file(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    path = runtime_paths.question_path(TICKET_ID)
    _write_json(path, _question_payload())

    with pytest.raises(SignalFormatError):
        repository.write_answer(TICKET_ID, "   ")

    on_disk = _read_json(path)
    assert on_disk["status"] == "pending"
    assert on_disk["answer"] is None
    assert list(runtime_paths.questions_dir.glob("*.tmp")) == []


# --- purge ---


def test_purge_removes_both_artifacts_including_tmp_siblings(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    ready_path = runtime_paths.ready_signal_path(TICKET_ID)
    question_path = runtime_paths.question_path(TICKET_ID)
    _write_json(ready_path, _ready_payload())
    _write_json(question_path, _question_payload(status="answered", answer="filesystem"))
    (ready_path.parent / f"{ready_path.name}.tmp").write_text("partial", encoding="utf-8")
    (question_path.parent / f"{question_path.name}.tmp").write_text("partial", encoding="utf-8")

    repository.purge(TICKET_ID)

    assert not ready_path.exists()
    assert not question_path.exists()
    assert list(runtime_paths.signals_dir.glob("*.tmp")) == []
    assert list(runtime_paths.questions_dir.glob("*.tmp")) == []


def test_purge_is_idempotent_and_creates_directories_for_writes(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    assert not runtime_paths.signals_dir.exists()
    assert not runtime_paths.questions_dir.exists()

    repository.purge(TICKET_ID)
    repository.purge(TICKET_ID)

    assert runtime_paths.signals_dir.is_dir()
    assert runtime_paths.questions_dir.is_dir()
    assert not runtime_paths.ready_signal_path(TICKET_ID).exists()
    assert not runtime_paths.question_path(TICKET_ID).exists()


def test_purge_does_not_touch_other_tickets(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    other_ready = runtime_paths.ready_signal_path("T099")
    other_question = runtime_paths.question_path("T099")
    _write_json(other_ready, _ready_payload(ticket_id="T099"))
    _write_json(other_question, _question_payload(ticket_id="T099"))
    _write_json(runtime_paths.ready_signal_path(TICKET_ID), _ready_payload())
    _write_json(runtime_paths.question_path(TICKET_ID), _question_payload())

    repository.purge(TICKET_ID)

    assert other_ready.is_file()
    assert other_question.is_file()


def test_constructor_creates_no_directories(tmp_path: Path) -> None:
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    FilesystemSignalRepository(runtime_paths)

    assert not runtime_paths.signals_dir.exists()
    assert not runtime_paths.questions_dir.exists()


# --- FakeSignalRepository ---


def test_fake_seeds_and_reads_signals_like_the_adapter() -> None:
    fake = FakeSignalRepository()
    fake.seed_ready(_ready_signal())
    fake.seed_question(_question_signal())

    assert fake.read_ready(TICKET_ID) == _ready_signal()
    assert fake.read_pending_question(TICKET_ID) == _question_signal()
    assert fake.read_ready("T999") is None
    assert fake.read_pending_question("T999") is None


def test_fake_consume_ready_and_purge_remove_seeded_artifacts() -> None:
    fake = FakeSignalRepository()
    fake.seed_ready(_ready_signal())
    fake.seed_question(_question_signal())

    fake.consume_ready(TICKET_ID)

    assert fake.read_ready(TICKET_ID) is None
    assert fake.read_pending_question(TICKET_ID) == _question_signal()
    assert fake.consumed_ready == [TICKET_ID]

    fake.purge(TICKET_ID)

    assert fake.read_pending_question(TICKET_ID) is None
    assert fake.purged_tickets == [TICKET_ID]


def test_fake_write_answer_records_calls_and_flips_only_status_and_answer() -> None:
    fake = FakeSignalRepository()
    fake.seed_question(_question_signal())

    answered = fake.write_answer(TICKET_ID, "filesystem")
    fake.write_answer(TICKET_ID, "memory")

    assert fake.write_answer_calls == [(TICKET_ID, "filesystem"), (TICKET_ID, "memory")]
    assert fake.read_pending_question(TICKET_ID) is None
    assert answered == replace(
        _question_signal(), status=SignalStatus.ANSWERED, answer="filesystem"
    )


def test_fake_write_answer_without_a_seeded_question_raises_signal_format_error() -> None:
    fake = FakeSignalRepository()

    with pytest.raises(SignalFormatError):
        fake.write_answer(TICKET_ID, "filesystem")


def test_fake_write_answer_rejects_blank_answer_like_the_domain() -> None:
    fake = FakeSignalRepository()
    fake.seed_question(_question_signal())

    with pytest.raises(SignalFormatError):
        fake.write_answer(TICKET_ID, "   ")

    assert fake.read_pending_question(TICKET_ID) == _question_signal()


def test_fake_raises_injected_read_errors_for_malformed_fixtures() -> None:
    ready_error = SignalFormatError("Ready signal is not valid JSON")
    question_error = SignalFormatError("Question signal is missing field 'question'")
    fake = FakeSignalRepository(
        read_ready_error=ready_error,
        read_question_error=question_error,
    )

    with pytest.raises(SignalFormatError, match="not valid JSON"):
        fake.read_ready(TICKET_ID)
    with pytest.raises(SignalFormatError, match="missing field"):
        fake.read_pending_question(TICKET_ID)


def test_adapter_and_fake_agree_on_the_full_signal_lifecycle(
    runtime_paths: RuntimePaths, repository: FilesystemSignalRepository
) -> None:
    ready_path = runtime_paths.ready_signal_path(TICKET_ID)
    question_path = runtime_paths.question_path(TICKET_ID)
    _write_json(ready_path, _ready_payload())
    _write_json(question_path, _question_payload())

    fake = FakeSignalRepository()
    fake.seed_ready(_ready_signal())
    fake.seed_question(_question_signal())

    assert repository.read_ready(TICKET_ID) == fake.read_ready(TICKET_ID)

    repository.consume_ready(TICKET_ID)
    fake.consume_ready(TICKET_ID)
    assert repository.read_ready(TICKET_ID) is None
    assert fake.read_ready(TICKET_ID) is None

    assert repository.read_pending_question(TICKET_ID) == fake.read_pending_question(TICKET_ID)

    assert repository.write_answer(TICKET_ID, "filesystem") == fake.write_answer(
        TICKET_ID, "filesystem"
    )
    assert repository.read_pending_question(TICKET_ID) is None
    assert fake.read_pending_question(TICKET_ID) is None

    repository.purge(TICKET_ID)
    fake.purge(TICKET_ID)
    assert repository.read_ready(TICKET_ID) is None
    assert fake.read_ready(TICKET_ID) is None
    assert repository.read_pending_question(TICKET_ID) is None
    assert fake.read_pending_question(TICKET_ID) is None
    assert not ready_path.exists()
    assert not question_path.exists()
