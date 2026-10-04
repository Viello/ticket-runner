"""Unit tests for the Signal domain entities and strict payload validation."""

import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from runner.domain.exceptions import SignalFormatError, TicketRunnerError
from runner.domain.signal import QuestionSignal, QuestionType, ReadySignal, SignalStatus

UTC = timezone.utc


def _ready_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": "T026",
        "status": "ready_for_verification",
        "modified_files": [
            "runner/domain/signal.py",
            "tests/unit/domain/test_signal.py",
        ],
        "self_review_notes": "Added strict signal validation; reviews passed.",
        "new_gotchas": ["Z-suffixed timestamps need normalizing before fromisoformat."],
        "scope": "domain",
        "timestamp": "2026-09-16T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def _question_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "ticket_id": "T026",
        "question": "Skeleton placeholder or centered spinner?",
        "type": "choice",
        "options": ["A: Skeleton placeholder rows", "B: Centered spinner"],
        "status": "pending",
        "answer": None,
        "created_at": "2026-09-16T10:00:00Z",
    }
    payload.update(overrides)
    return payload


def _ready_signal(**overrides: object) -> ReadySignal:
    fields: dict[str, object] = {
        "ticket_id": "T026",
        "status": SignalStatus.READY_FOR_VERIFICATION,
        "modified_files": ("runner/domain/signal.py",),
        "self_review_notes": "Reviews passed.",
        "new_gotchas": (),
        "timestamp": datetime(2026, 9, 16, 10, 0, tzinfo=UTC),
        "scope": "domain",
    }
    fields.update(overrides)
    return ReadySignal(**fields)  # type: ignore[arg-type]


def _question_signal(**overrides: object) -> QuestionSignal:
    fields: dict[str, object] = {
        "ticket_id": "T026",
        "question": "Skeleton or spinner?",
        "type": QuestionType.CHOICE,
        "options": ("A: Skeleton", "B: Spinner"),
        "status": SignalStatus.PENDING,
        "answer": None,
        "created_at": datetime(2026, 9, 16, 10, 0, tzinfo=UTC),
    }
    fields.update(overrides)
    return QuestionSignal(**fields)  # type: ignore[arg-type]


# --- Exception hierarchy ---


def test_signal_format_error_is_rooted_at_ticket_runner_error() -> None:
    assert issubclass(SignalFormatError, TicketRunnerError)


# --- ReadySignal: valid payloads ---


def test_ready_signal_parses_full_payload_from_json_text() -> None:
    signal = ReadySignal.parse(json.dumps(_ready_payload()), "T026")

    assert signal.ticket_id == "T026"
    assert signal.status is SignalStatus.READY_FOR_VERIFICATION
    assert signal.modified_files == (
        "runner/domain/signal.py",
        "tests/unit/domain/test_signal.py",
    )
    assert signal.self_review_notes == "Added strict signal validation; reviews passed."
    assert signal.new_gotchas == (
        "Z-suffixed timestamps need normalizing before fromisoformat.",
    )
    assert signal.scope == "domain"
    assert signal.timestamp == datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


def test_ready_signal_parses_mapping() -> None:
    signal = ReadySignal.parse(_ready_payload(), "T026")

    assert signal.ticket_id == "T026"
    assert signal.scope == "domain"


def test_ready_signal_scope_is_optional() -> None:
    payload = _ready_payload()
    del payload["scope"]

    assert ReadySignal.parse(payload, "T026").scope is None


def test_ready_signal_explicit_null_scope_parses() -> None:
    assert ReadySignal.parse(_ready_payload(scope=None), "T026").scope is None


def test_ready_signal_tolerates_unknown_extra_fields() -> None:
    payload = _ready_payload(extra={"nested": [1, 2, 3]}, attempt=2)

    signal = ReadySignal.parse(payload, "T026")

    assert signal.ticket_id == "T026"


def test_ready_signal_tolerates_legacy_manual_verification_payload() -> None:
    payload = _ready_payload(
        manual_verification=[
            {
                "name": "Legacy scenario",
                "setup": "None",
                "steps": "Run command",
                "expected": "Pass",
                "auto_covered": True,
            }
        ]
    )

    signal = ReadySignal.parse(json.dumps(payload), "T026")

    assert signal.ticket_id == "T026"
    assert not hasattr(signal, "manual_verification")
    assert not hasattr(signal, "manual_verification_is_default")


def test_ready_signal_schema_excludes_manual_verification() -> None:
    assert "manual_verification" not in ReadySignal.__dataclass_fields__



@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-16T10:00:00Z",
        "2026-09-16T10:00:00+00:00",
        "2026-09-16T12:30:00+02:00",
        "2026-09-16T10:00:00",
    ],
)
def test_ready_signal_accepts_iso8601_timestamps(timestamp: str) -> None:
    signal = ReadySignal.parse(_ready_payload(timestamp=timestamp), "T026")

    assert isinstance(signal.timestamp, datetime)


def test_ready_signal_normalizes_trailing_z_to_utc() -> None:
    signal = ReadySignal.parse(_ready_payload(timestamp="2026-09-16T10:00:00Z"), "T026")

    assert signal.timestamp.utcoffset() == timedelta(0)


def test_ready_signal_is_frozen() -> None:
    signal = _ready_signal()

    with pytest.raises(FrozenInstanceError):
        signal.scope = "ui"  # type: ignore[misc]


# --- ReadySignal: violations ---


@pytest.mark.parametrize(
    "field",
    ["ticket_id", "status", "modified_files", "self_review_notes", "new_gotchas", "timestamp"],
)
def test_ready_signal_rejects_missing_fields(field: str) -> None:
    payload = _ready_payload()
    del payload[field]

    with pytest.raises(SignalFormatError, match=field):
        ReadySignal.parse(payload, "T026")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_id", None),
        ("status", 3),
        ("modified_files", "runner/domain/signal.py"),
        ("modified_files", [1, 2]),
        ("modified_files", None),
        ("self_review_notes", None),
        ("new_gotchas", "one gotcha"),
        ("new_gotchas", [["nested"]]),
        ("timestamp", 20260916),
        ("timestamp", None),
    ],
)
def test_ready_signal_rejects_wrong_types(field: str, value: object) -> None:
    with pytest.raises(SignalFormatError, match=field):
        ReadySignal.parse(_ready_payload(**{field: value}), "T026")


@pytest.mark.parametrize(
    "timestamp",
    ["yesterday", "2026-13-01T10:00:00Z", "16/09/2026 10:00", "", "   "],
)
def test_ready_signal_rejects_non_iso8601_timestamps(timestamp: str) -> None:
    with pytest.raises(SignalFormatError, match="timestamp"):
        ReadySignal.parse(_ready_payload(timestamp=timestamp), "T026")


@pytest.mark.parametrize("status", ["pending", "answered", "done", "READY_FOR_VERIFICATION", ""])
def test_ready_signal_rejects_unknown_status(status: str) -> None:
    with pytest.raises(SignalFormatError, match="status"):
        ReadySignal.parse(_ready_payload(status=status), "T026")


def test_ready_signal_rejects_ticket_id_mismatch_even_when_otherwise_valid() -> None:
    with pytest.raises(SignalFormatError, match="does not match"):
        ReadySignal.parse(_ready_payload(ticket_id="T999"), "T026")


@pytest.mark.parametrize("scope", ["Domain", "domain scope", "", "   ", "T026", "t026", "domain_x"])
def test_ready_signal_rejects_invalid_scope(scope: str) -> None:
    with pytest.raises(SignalFormatError, match="scope"):
        ReadySignal.parse(_ready_payload(scope=scope), "T026")


def test_ready_signal_rejects_invalid_json_text() -> None:
    with pytest.raises(SignalFormatError, match="JSON"):
        ReadySignal.parse("{not json", "T026")


def test_ready_signal_rejects_non_object_json() -> None:
    with pytest.raises(SignalFormatError, match="object"):
        ReadySignal.parse("[]", "T026")


def test_ready_signal_rejects_pathologically_nested_json() -> None:
    payload = "[" * 20000 + "]" * 20000

    with pytest.raises(SignalFormatError):
        ReadySignal.parse(payload, "T026")


def test_ready_signal_rejects_unsupported_source_type() -> None:
    with pytest.raises(SignalFormatError, match="payload"):
        ReadySignal.parse(b'{"ticket_id": "T026"}', "T026")  # type: ignore[arg-type]


def test_json_decode_error_never_escapes_parsing() -> None:
    with pytest.raises(SignalFormatError):
        ReadySignal.parse('{"ticket_id": "T026",', "T026")
    with pytest.raises(SignalFormatError):
        QuestionSignal.parse('{"ticket_id": "T026",', "T026")


# --- ReadySignal: constructor invariants ---


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"ticket_id": ""}, "ticket_id"),
        ({"status": SignalStatus.PENDING}, "status"),
        ({"status": "ready"}, "status"),
        ({"modified_files": ["ok.py", 1]}, "modified_files"),
        ({"new_gotchas": ("fine", None)}, "new_gotchas"),
        ({"timestamp": "yesterday"}, "timestamp"),
        ({"scope": "T026"}, "scope"),
        ({"scope": "UPPER"}, "scope"),
    ],
)
def test_ready_signal_constructor_rejects_invalid_values(
    overrides: dict[str, object], field: str
) -> None:
    with pytest.raises(SignalFormatError, match=field):
        _ready_signal(**overrides)


def test_ready_signal_constructor_coerces_sequences_and_status() -> None:
    signal = ReadySignal(
        ticket_id="T026",
        status="ready_for_verification",
        modified_files=["a.py"],
        self_review_notes="",
        new_gotchas=["g"],
        timestamp="2026-09-16T10:00:00Z",
    )

    assert signal.status is SignalStatus.READY_FOR_VERIFICATION
    assert signal.modified_files == ("a.py",)
    assert signal.new_gotchas == ("g",)
    assert signal.scope is None


# --- QuestionSignal: valid payloads ---


def test_question_signal_parses_choice_payload() -> None:
    signal = QuestionSignal.parse(_question_payload(), "T026")

    assert signal.ticket_id == "T026"
    assert signal.question == "Skeleton placeholder or centered spinner?"
    assert signal.type is QuestionType.CHOICE
    assert signal.options == ("A: Skeleton placeholder rows", "B: Centered spinner")
    assert signal.status is SignalStatus.PENDING
    assert signal.answer is None
    assert signal.created_at == datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


def test_question_signal_parses_text_payload_with_null_options() -> None:
    payload = _question_payload(type="text", options=None)

    signal = QuestionSignal.parse(payload, "T026")

    assert signal.type is QuestionType.TEXT
    assert signal.options is None


def test_question_signal_parses_text_payload_with_absent_options() -> None:
    payload = _question_payload(type="text")
    del payload["options"]

    signal = QuestionSignal.parse(payload, "T026")

    assert signal.type is QuestionType.TEXT
    assert signal.options is None


def test_question_signal_parses_answered_payload() -> None:
    payload = _question_payload(status="answered", answer="A")

    signal = QuestionSignal.parse(payload, "T026")

    assert signal.status is SignalStatus.ANSWERED
    assert signal.answer == "A"
    assert signal.options == ("A: Skeleton placeholder rows", "B: Centered spinner")


def test_question_signal_parses_mapping_and_tolerates_unknown_fields() -> None:
    payload = _question_payload(asker="worker", metadata={"attempt": 1})

    signal = QuestionSignal.parse(payload, "T026")

    assert signal.question == "Skeleton placeholder or centered spinner?"


def test_question_signal_rejects_ticket_id_mismatch_even_when_otherwise_valid() -> None:
    with pytest.raises(SignalFormatError, match="does not match"):
        QuestionSignal.parse(_question_payload(ticket_id="T999"), "T026")


# --- QuestionSignal: violations ---


@pytest.mark.parametrize(
    "field",
    ["ticket_id", "question", "type", "status", "created_at"],
)
def test_question_signal_rejects_missing_fields(field: str) -> None:
    payload = _question_payload()
    del payload[field]

    with pytest.raises(SignalFormatError, match=field):
        QuestionSignal.parse(payload, "T026")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_id", None),
        ("question", None),
        ("question", 5),
        ("type", "yes_no"),
        ("type", 3),
        ("options", ["A", 2]),
        ("status", "waiting"),
        ("created_at", 20260916),
    ],
)
def test_question_signal_rejects_wrong_types_and_unknown_vocabulary(
    field: str, value: object
) -> None:
    with pytest.raises(SignalFormatError, match=field):
        QuestionSignal.parse(_question_payload(**{field: value}), "T026")


@pytest.mark.parametrize(
    "options",
    [None, [], [""], ["A: Skeleton", "   "], "A: Skeleton", "A: Skeleton, B: Spinner"],
)
def test_question_signal_rejects_choice_without_non_empty_options(options: object) -> None:
    with pytest.raises(SignalFormatError, match="options"):
        QuestionSignal.parse(_question_payload(options=options), "T026")


def test_question_signal_rejects_absent_options_for_choice() -> None:
    payload = _question_payload()
    del payload["options"]

    with pytest.raises(SignalFormatError, match="options"):
        QuestionSignal.parse(payload, "T026")


def test_question_signal_rejects_non_null_options_for_text() -> None:
    with pytest.raises(SignalFormatError, match="options"):
        QuestionSignal.parse(
            _question_payload(type="text", options=["A: Skeleton"]), "T026"
        )


@pytest.mark.parametrize("answer", [None, "", "   "])
def test_question_signal_rejects_answered_without_answer(answer: object) -> None:
    with pytest.raises(SignalFormatError, match="answer"):
        QuestionSignal.parse(
            _question_payload(status="answered", answer=answer), "T026"
        )


def test_question_signal_rejects_pending_with_answer() -> None:
    with pytest.raises(SignalFormatError, match="answer"):
        QuestionSignal.parse(_question_payload(status="pending", answer="A"), "T026")


@pytest.mark.parametrize(
    "timestamp",
    ["yesterday", "2026-13-01T10:00:00Z", "", "   "],
)
def test_question_signal_rejects_non_iso8601_timestamps(timestamp: str) -> None:
    with pytest.raises(SignalFormatError, match="created_at"):
        QuestionSignal.parse(_question_payload(created_at=timestamp), "T026")


def test_question_signal_rejects_invalid_json_text() -> None:
    with pytest.raises(SignalFormatError, match="JSON"):
        QuestionSignal.parse("not json at all", "T026")


def test_question_signal_rejects_non_object_json() -> None:
    with pytest.raises(SignalFormatError, match="object"):
        QuestionSignal.parse('"just a string"', "T026")


# --- QuestionSignal: constructor invariants ---


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"ticket_id": ""}, "ticket_id"),
        ({"question": "   "}, "question"),
        ({"type": "yes_no"}, "type"),
        ({"type": QuestionType.CHOICE, "options": None}, "options"),
        ({"type": QuestionType.CHOICE, "options": ()}, "options"),
        ({"type": QuestionType.CHOICE, "options": ("",)}, "options"),
        ({"type": QuestionType.TEXT, "options": ("A",)}, "options"),
        ({"status": SignalStatus.READY_FOR_VERIFICATION}, "status"),
        ({"status": SignalStatus.ANSWERED, "answer": None}, "answer"),
        ({"status": SignalStatus.PENDING, "answer": "A"}, "answer"),
    ],
)
def test_question_signal_constructor_rejects_invalid_values(
    overrides: dict[str, object], field: str
) -> None:
    with pytest.raises(SignalFormatError, match=field):
        _question_signal(**overrides)


def test_question_signal_constructor_coerces_strings_and_sequences() -> None:
    signal = QuestionSignal(
        ticket_id="T026",
        question="Skeleton or spinner?",
        type="choice",
        options=["A", "B"],
        status="answered",
        answer="A",
        created_at="2026-09-16T10:00:00Z",
    )

    assert signal.type is QuestionType.CHOICE
    assert signal.status is SignalStatus.ANSWERED
    assert signal.options == ("A", "B")
    assert signal.answer == "A"
    assert signal.created_at == datetime(2026, 9, 16, 10, 0, tzinfo=UTC)


def test_question_signal_is_frozen() -> None:
    signal = _question_signal()

    with pytest.raises(FrozenInstanceError):
        signal.answer = "A"  # type: ignore[misc]
