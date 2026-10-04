"""Signal domain entities and strict validation of Worker-to-Runner payloads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import json
import re
from typing import Any

from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.domain.exceptions import SignalFormatError

TICKET_NUMBER_PATTERN = re.compile(r"^[tT]\d{3,}$")
SCOPE_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

_READY_LABEL = "Ready signal"
_QUESTION_LABEL = "Question signal"


class SignalStatus(Enum):
    """Status values for Signal files."""

    READY_FOR_VERIFICATION = "ready_for_verification"
    PENDING = "pending"
    ANSWERED = "answered"


class QuestionType(Enum):
    """Question kinds a Worker may ask."""

    CHOICE = "choice"
    TEXT = "text"


_READY_STATUSES = (SignalStatus.READY_FOR_VERIFICATION,)
_QUESTION_STATUSES = (SignalStatus.PENDING, SignalStatus.ANSWERED)

_PREVIEW_LIMIT = 120


def _preview(value: object) -> str:
    """Bound a value's repr so diagnostics stay single-line and actionable."""
    text = repr(value)
    if len(text) <= _PREVIEW_LIMIT:
        return text
    return f"{text[:_PREVIEW_LIMIT]}...(truncated)"


def _validate_text(value: object, field: str, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SignalFormatError(
            f"{label} field '{field}' must be a string, got: {_preview(value)}"
        )
    if not allow_empty and not value.strip():
        raise SignalFormatError(
            f"{label} field '{field}' must be a non-empty string, got: {_preview(value)}"
        )
    return value


def _validate_string_tuple(value: object, field: str, label: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise SignalFormatError(
            f"{label} field '{field}' must be an array of strings, got: {_preview(value)}"
        )
    for entry in value:
        if not isinstance(entry, str):
            raise SignalFormatError(
                f"{label} field '{field}' entries must be strings, got: {_preview(entry)}"
            )
    return tuple(value)


def _coerce_timestamp(value: object, field: str, label: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if candidate:
            try:
                return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            except ValueError:
                pass
    raise SignalFormatError(
        f"{label} field '{field}' must be an ISO-8601 timestamp, got: {_preview(value)}"
    )


def _coerce_enum(
    enum_cls: type[Enum],
    value: object,
    allowed: tuple[Enum, ...],
    field: str,
    label: str,
) -> Any:
    if isinstance(value, enum_cls):
        member: Enum | None = value
    else:
        try:
            member = enum_cls(value)
        except (ValueError, TypeError):
            member = None
    if member is None or member not in allowed:
        expected = " or ".join(repr(item.value) for item in allowed)
        shown = value.value if isinstance(value, enum_cls) else value
        raise SignalFormatError(
            f"{label} field '{field}' must be {expected}, got: {_preview(shown)}"
        )
    return member


def _coerce_status(
    value: object, label: str, allowed: tuple[SignalStatus, ...]
) -> SignalStatus:
    return _coerce_enum(SignalStatus, value, allowed, "status", label)


def _coerce_question_type(value: object, label: str) -> QuestionType:
    return _coerce_enum(QuestionType, value, tuple(QuestionType), "type", label)


def _validate_scope(value: object, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SignalFormatError(
            f"{label} field 'scope' must be a non-empty lowercase token, got: {_preview(value)}"
        )
    if TICKET_NUMBER_PATTERN.match(value):
        raise SignalFormatError(
            f"{label} field 'scope' must not be a ticket number, got: {_preview(value)}"
        )
    if not SCOPE_PATTERN.match(value):
        raise SignalFormatError(
            f"{label} field 'scope' must be a lowercase token (letters, digits, hyphens), "
            f"got: {_preview(value)}"
        )
    return value


def _validate_options(
    value: object, question_type: QuestionType, label: str
) -> tuple[str, ...] | None:
    if question_type is QuestionType.CHOICE:
        options = () if value is None else _validate_string_tuple(value, "options", label)
        if not options or any(not entry.strip() for entry in options):
            raise SignalFormatError(
                f"{label} field 'options' must be a non-empty array of non-empty strings "
                f"for choice questions"
            )
        return options
    if value is not None:
        raise SignalFormatError(
            f"{label} field 'options' must be null or absent for text questions, "
            f"got: {_preview(value)}"
        )
    return None


def _validate_answer(
    value: object, status: SignalStatus, label: str
) -> str | None:
    if status is SignalStatus.ANSWERED:
        if not isinstance(value, str) or not value.strip():
            raise SignalFormatError(
                f"{label} field 'answer' must be a non-empty string when status is 'answered', "
                f"got: {_preview(value)}"
            )
        return value
    if value is not None:
        raise SignalFormatError(
            f"{label} field 'answer' must be null or absent when status is 'pending', "
            f"got: {_preview(value)}"
        )
    return None


def _validate_manual_verification(value: object, label: str) -> tuple[dict, ...]:
    """Validate and coerce the manual_verification field.

    Each entry must be a dict. The four core string fields (name, setup, steps, expected)
    are validated as strings. Two optional extension fields are also accepted:
    - ``auto_covered`` (bool, defaults to False): whether the automated test suite also
      exercises this scenario end-to-end.
    - ``update_notes`` (str, defaults to ""): free-text note when this scenario supersedes
      a prior ticket's smoke log entry.
    Returns a tuple of dicts, or raises SignalFormatError.
    Accepts _MISSING_SENTINEL to represent "field absent from payload".
    """
    _STRING_FIELDS = frozenset({"name", "setup", "steps", "expected", "update_notes"})

    if value is _MISSING_SENTINEL or value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise SignalFormatError(
            f"{label} field 'manual_verification' must be an array of dicts, got: {_preview(value)}"
        )
    result: list[dict] = []
    for i, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise SignalFormatError(
                f"{label} field 'manual_verification[{i}]' must be a dict, got: {_preview(entry)}"
            )
        sanitized: dict = {}
        for k, v in entry.items():
            if k == "auto_covered":
                # Accept bool or bool-coercible int; normalise to Python bool
                if not isinstance(v, (bool, int)) or isinstance(v, float):
                    raise SignalFormatError(
                        f"{label} field 'manual_verification[{i}][auto_covered]' must be a boolean,"
                        f" got: {_preview(v)}"
                    )
                sanitized[k] = bool(v)
            elif k in _STRING_FIELDS:
                if not isinstance(v, str):
                    raise SignalFormatError(
                        f"{label} field 'manual_verification[{i}][{k}]' must be a string, got: {_preview(v)}"
                    )
                # Strip ANSI escape sequences
                s = re.sub(r"\x1b\[[0-9;]*m", "", v)
                if k == "name":
                    # Sanitize scenario name: strip carriage returns and newlines to prevent git header injection
                    s = s.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
                sanitized[k] = s
            else:
                # Unknown keys: validate as string and pass through for forward compatibility
                if not isinstance(v, str):
                    raise SignalFormatError(
                        f"{label} field 'manual_verification[{i}][{k}]' must be a string, got: {_preview(v)}"
                    )
                sanitized[k] = re.sub(r"\x1b\[[0-9;]*m", "", v)
        result.append(sanitized)
    return tuple(result)


def _validate_ticket_match(actual: str, expected: object, label: str) -> None:
    if not isinstance(expected, str) or not expected.strip():
        raise SignalFormatError(
            f"{label} expected ticket_id must be a non-empty string, got: {_preview(expected)}"
        )
    if actual != expected:
        raise SignalFormatError(
            f"{label} ticket_id {actual!r} does not match the expected ticket {expected!r}"
        )


def _decode_payload(source: object, label: str) -> Mapping[str, Any]:
    if isinstance(source, Mapping):
        return source
    if isinstance(source, str):
        try:
            decoded = json.loads(source)
        except RecursionError:
            raise SignalFormatError(
                f"{label} is not valid JSON: payload nesting is too deep"
            ) from None
        except json.JSONDecodeError as exc:
            raise SignalFormatError(
                f"{label} is not valid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"
            ) from None
        if not isinstance(decoded, Mapping):
            raise SignalFormatError(
                f"{label} JSON must be an object, got: {_preview(decoded)}"
            )
        return decoded
    raise SignalFormatError(
        f"{label} payload must be JSON text or a mapping, got: {_preview(source)}"
    )


def _require_present(payload: Mapping[str, Any], field: str, label: str) -> Any:
    if field not in payload:
        raise SignalFormatError(f"{label} is missing required field '{field}'")
    return payload[field]


def _require_text(payload: Mapping[str, Any], field: str, label: str) -> str:
    return _validate_text(_require_present(payload, field, label), field, label)


_MISSING_SENTINEL = object()


def _has_manual_verification_key(payload: Mapping[str, Any]) -> bool:
    """Check if 'manual_verification' key exists in the raw payload dict."""
    return "manual_verification" in payload


@dataclass(frozen=True)
class ReadySignal:
    """Worker declaration that implementation is ready for Gatekeeper verification."""

    ticket_id: str
    status: SignalStatus
    modified_files: tuple[str, ...]
    self_review_notes: str
    new_gotchas: tuple[str, ...]
    timestamp: datetime
    scope: str | None = None
    manual_verification: tuple[dict, ...] = ()
    _manual_verification_was_present: bool = False

    def __post_init__(self) -> None:
        label = _READY_LABEL
        _validate_text(self.ticket_id, "ticket_id", label)
        object.__setattr__(
            self,
            "status",
            _coerce_status(self.status, label, _READY_STATUSES),
        )
        object.__setattr__(
            self,
            "modified_files",
            _validate_string_tuple(self.modified_files, "modified_files", label),
        )
        _validate_text(self.self_review_notes, "self_review_notes", label, allow_empty=True)
        object.__setattr__(
            self,
            "new_gotchas",
            _validate_string_tuple(self.new_gotchas, "new_gotchas", label),
        )
        object.__setattr__(
            self,
            "timestamp",
            _coerce_timestamp(self.timestamp, "timestamp", label),
        )
        object.__setattr__(self, "scope", _validate_scope(self.scope, label))
        object.__setattr__(
            self,
            "manual_verification",
            _validate_manual_verification(self.manual_verification, label),
        )

    @property
    def manual_verification_is_default(self) -> bool:
        """Return True when manual_verification was not present in the payload."""
        return not self._manual_verification_was_present

    @classmethod
    def parse(
        cls, source: str | Mapping[str, Any], expected_ticket_id: str
    ) -> ReadySignal:
        """Strictly parse a ready Signal payload. Pure: no I/O, no path construction."""
        label = _READY_LABEL
        payload = _decode_payload(source, label)
        ticket_id = _require_text(payload, "ticket_id", label)
        _validate_ticket_match(ticket_id, expected_ticket_id, label)
        return cls(
            ticket_id=ticket_id,
            status=_require_present(payload, "status", label),
            modified_files=_require_present(payload, "modified_files", label),
            self_review_notes=_require_present(payload, "self_review_notes", label),
            new_gotchas=_require_present(payload, "new_gotchas", label),
            timestamp=_require_present(payload, "timestamp", label),
            scope=payload.get("scope"),
            manual_verification=payload.get("manual_verification", ()),
            _manual_verification_was_present=_has_manual_verification_key(payload),
        )


@dataclass(frozen=True)
class QuestionSignal:
    """Worker clarification question awaiting a human answer."""

    ticket_id: str
    question: str
    type: QuestionType
    options: tuple[str, ...] | None
    status: SignalStatus
    answer: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        label = _QUESTION_LABEL
        _validate_text(self.ticket_id, "ticket_id", label)
        _validate_text(self.question, "question", label)
        question_type = _coerce_question_type(self.type, label)
        object.__setattr__(self, "type", question_type)
        object.__setattr__(
            self, "options", _validate_options(self.options, question_type, label)
        )
        status = _coerce_status(self.status, label, _QUESTION_STATUSES)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "answer", _validate_answer(self.answer, status, label))
        object.__setattr__(
            self,
            "created_at",
            _coerce_timestamp(self.created_at, "created_at", label),
        )

    @classmethod
    def parse(
        cls, source: str | Mapping[str, Any], expected_ticket_id: str
    ) -> QuestionSignal:
        """Strictly parse a question Signal payload. Pure: no I/O, no path construction."""
        label = _QUESTION_LABEL
        payload = _decode_payload(source, label)
        ticket_id = _require_text(payload, "ticket_id", label)
        _validate_ticket_match(ticket_id, expected_ticket_id, label)
        return cls(
            ticket_id=ticket_id,
            question=_require_present(payload, "question", label),
            type=_require_present(payload, "type", label),
            options=payload.get("options"),
            status=_require_present(payload, "status", label),
            answer=payload.get("answer"),
            created_at=_require_present(payload, "created_at", label),
        )
