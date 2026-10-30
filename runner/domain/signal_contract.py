"""Pure domain contract checker for markdown Signal examples.

Extracts fenced JSON blocks from markdown documents, classifies ready versus
question examples, substitutes documented placeholders, and strictly validates
each classified example against the real Signal parsers.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
import json
import re
from typing import Any

from runner.domain.exceptions import SignalFormatError
from runner.domain.signal import QuestionSignal, ReadySignal, SignalStatus
from runner.domain.signal_schema import FIXED_TIMESTAMP

_FENCE_PATTERN = re.compile(
    r"^[ ]{0,3}(?P<fence>`{3,}|~{3,})json[ \t]*\r?\n(?P<body>[\s\S]*?)\r?\n[ ]{0,3}(?P=fence)[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)

_TICKET_ID_PLACEHOLDER_PATTERN = re.compile(r"<ticket_id>|\{ticket_id\}", re.IGNORECASE)

_TIMESTAMP_PLACEHOLDER_PATTERN = re.compile(
    r"<(?:iso-8601(?:-utc)?(?:-timestamp)?|iso-8601 utc|iso-8601 timestamp|timestamp)>|\{timestamp\}",
    re.IGNORECASE,
)


class SignalExampleKind(Enum):
    """Classification of an extracted Signal example."""

    READY = "ready"
    QUESTION = "question"


def extract_fenced_json_blocks(markdown: str) -> list[dict[str, Any]]:
    """Extract and parse all fenced json blocks from markdown.

    Other code fences (python, bash, yaml, etc.), invalid JSON syntax, and
    non-mapping JSON blocks (lists, primitives) are ignored.
    """
    blocks: list[dict[str, Any]] = []
    for match in _FENCE_PATTERN.finditer(markdown):
        body = match.group("body")
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, RecursionError):
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


def classify_signal_example(block: Mapping[str, Any]) -> SignalExampleKind | None:
    """Classify a JSON mapping as a ready or question Signal example.

    A block is classified as ready when it carries ticket_id and either
    modified_files or the ready status. It is classified as question when
    it carries ticket_id and question. Blocks carrying neither classification
    are ignored (return None).
    """
    if "ticket_id" not in block:
        return None

    status_val = block.get("status")
    has_ready_status = (
        status_val == SignalStatus.READY_FOR_VERIFICATION.value
        or status_val is SignalStatus.READY_FOR_VERIFICATION
    )
    is_ready = "modified_files" in block or has_ready_status
    is_question = "question" in block

    if is_ready and not is_question:
        return SignalExampleKind.READY
    if is_question and not is_ready:
        return SignalExampleKind.QUESTION
    if is_ready and is_question:
        return SignalExampleKind.READY
    return None


def substitute_placeholders(
    value: Any,
    ticket_id: str = "T100",
    timestamp: str = FIXED_TIMESTAMP,
) -> Any:
    """Recursively substitute documented ticket_id and timestamp placeholders.

    Unknown placeholders remain in place so that the downstream Signal parser
    error can explicitly name them in diagnostic messages.
    """
    if isinstance(value, str):
        with_ticket = _TICKET_ID_PLACEHOLDER_PATTERN.sub(ticket_id, value)
        return _TIMESTAMP_PLACEHOLDER_PATTERN.sub(timestamp, with_ticket)
    if isinstance(value, Mapping):
        return {
            substitute_placeholders(k, ticket_id, timestamp): substitute_placeholders(
                v, ticket_id, timestamp
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [substitute_placeholders(item, ticket_id, timestamp) for item in value]
    if isinstance(value, tuple):
        return tuple(substitute_placeholders(item, ticket_id, timestamp) for item in value)
    return value


def validate_markdown_signal_examples(
    markdown: str,
    ticket_id: str = "T100",
) -> list[str]:
    """Validate all classified Signal examples in markdown against real parsers.

    Returns a list of indexed error strings for any violations. If all classified
    examples are valid (or no signal examples are present), returns an empty list.
    """
    blocks = extract_fenced_json_blocks(markdown)
    errors: list[str] = []

    for index, block in enumerate(blocks):
        kind = classify_signal_example(block)
        if kind is None:
            continue

        substituted = substitute_placeholders(block, ticket_id=ticket_id)
        try:
            if kind is SignalExampleKind.READY:
                ReadySignal.parse(substituted, expected_ticket_id=ticket_id)
            elif kind is SignalExampleKind.QUESTION:
                QuestionSignal.parse(substituted, expected_ticket_id=ticket_id)
        except (SignalFormatError, ValueError, TypeError) as exc:
            errors.append(f"Block {index}: {exc}")

    return errors
