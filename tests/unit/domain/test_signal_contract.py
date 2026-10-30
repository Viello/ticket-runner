"""Unit tests for pure domain markdown signal example contract checking (T132)."""

from __future__ import annotations

from runner.domain.signal_contract import (
    SignalExampleKind,
    classify_signal_example,
    extract_fenced_json_blocks,
    substitute_placeholders,
    validate_markdown_signal_examples,
)
from runner.domain.signal_schema import FIXED_TIMESTAMP

STALE_QUESTION_BLOCK = """\
{
  "ticket_id": "<ticket_id>",
  "question": "<clear concise description of the blocker and choices>",
  "context": "<relevant files or findings>",
  "timestamp": "<ISO-8601-UTC>"
}"""

VALID_READY_BLOCK = """\
{
  "ticket_id": "<ticket_id>",
  "status": "ready_for_verification",
  "modified_files": [
    "runner/domain/signal.py"
  ],
  "self_review_notes": "Standards and Spec clean.",
  "new_gotchas": [
    {
      "problem": "Schemas drifted.",
      "solution": "Domain authority."
    }
  ],
  "timestamp": "<ISO-8601-UTC>"
}"""

VALID_QUESTION_BLOCK = """\
{
  "ticket_id": "<ticket_id>",
  "question": "Which option?",
  "type": "choice",
  "options": ["A: First", "B: Second"],
  "status": "pending",
  "answer": null,
  "created_at": "<ISO-8601-UTC>"
}"""


def test_extract_fenced_json_blocks_only_returns_valid_mapping_json() -> None:
    markdown = """\
# Title

```python
x = 1
```

```
plain text fence
```

```json
{
  "key1": "val1"
}
```

```json
[1, 2, 3]
```

```json
"just a string"
```

```json
{not valid json
```

```JSON
{
  "key2": 42
}
```

~~~json
{
  "key3": "tilde"
}
~~~
"""
    blocks = extract_fenced_json_blocks(markdown)
    assert len(blocks) == 3
    assert blocks[0] == {"key1": "val1"}
    assert blocks[1] == {"key2": 42}
    assert blocks[2] == {"key3": "tilde"}


def test_extract_fenced_json_blocks_empty_when_no_blocks() -> None:
    assert extract_fenced_json_blocks("") == []
    assert extract_fenced_json_blocks("# Only markdown\nNo code here.") == []


def test_classify_signal_example_ready() -> None:
    # ticket_id and modified_files
    assert classify_signal_example({"ticket_id": "T100", "modified_files": []}) is SignalExampleKind.READY
    # ticket_id and ready status
    assert (
        classify_signal_example({"ticket_id": "T100", "status": "ready_for_verification"})
        is SignalExampleKind.READY
    )
    # ticket_id and both
    assert (
        classify_signal_example(
            {"ticket_id": "T100", "status": "ready_for_verification", "modified_files": []}
        )
        is SignalExampleKind.READY
    )


def test_classify_signal_example_question() -> None:
    # ticket_id and question
    assert classify_signal_example({"ticket_id": "T100", "question": "Why?"}) is SignalExampleKind.QUESTION
    # ticket_id, question, and pending status
    assert (
        classify_signal_example({"ticket_id": "T100", "question": "Why?", "status": "pending"})
        is SignalExampleKind.QUESTION
    )


def test_classify_signal_example_ignored_when_neither() -> None:
    # missing ticket_id
    assert classify_signal_example({"modified_files": []}) is None
    assert classify_signal_example({"question": "Why?"}) is None
    assert classify_signal_example({"status": "ready_for_verification"}) is None
    # ticket_id but neither modified_files, ready status, nor question
    assert classify_signal_example({"ticket_id": "T100", "random": 123}) is None
    assert classify_signal_example({"ticket_id": "T100", "status": "pending"}) is None


def test_substitute_placeholders_recursive() -> None:
    source = {
        "ticket_id": "<ticket_id>",
        "path": "signals/{ticket_id}_ready.json",
        "timestamp": "<ISO-8601-UTC>",
        "created_at": "{timestamp}",
        "other_ts": "<ISO-8601>",
        "notes": "Ticket <ticket_id> at <ISO-8601-UTC-timestamp>",
        "nested": {
            "ticket": "<ticket_id>",
            "list": ["<ticket_id>", "<timestamp>", "<unknown_placeholder>"],
        },
        "unknown": "<custom_val>",
    }
    result = substitute_placeholders(source, ticket_id="T101")
    assert result["ticket_id"] == "T101"
    assert result["path"] == "signals/T101_ready.json"
    assert result["timestamp"] == FIXED_TIMESTAMP
    assert result["created_at"] == FIXED_TIMESTAMP
    assert result["other_ts"] == FIXED_TIMESTAMP
    assert result["notes"] == f"Ticket T101 at {FIXED_TIMESTAMP}"
    assert result["nested"]["ticket"] == "T101"
    assert result["nested"]["list"] == ["T101", FIXED_TIMESTAMP, "<unknown_placeholder>"]
    # Unknown placeholder remains in place
    assert result["unknown"] == "<custom_val>"


def test_validate_markdown_signal_examples_valid_payloads() -> None:
    markdown = f"""\
# Skill Instructions

Ready Signal example:
```json
{VALID_READY_BLOCK}
```

Question Signal example:
```json
{VALID_QUESTION_BLOCK}
```

Unrelated JSON:
```json
{{
  "name": "unrelated",
  "version": 1
}}
```
"""
    errors = validate_markdown_signal_examples(markdown, ticket_id="T100")
    assert errors == []


def test_validate_markdown_signal_examples_stale_question_block() -> None:
    markdown = f"""\
# Blocked section

```json
{STALE_QUESTION_BLOCK}
```
"""
    errors = validate_markdown_signal_examples(markdown, ticket_id="T100")
    assert len(errors) == 1
    # Error should be indexed and name the missing required field 'type'
    assert "Block 0" in errors[0]
    assert "missing required field 'type'" in errors[0]


def test_validate_markdown_signal_examples_stale_ready_block_missing_field() -> None:
    bad_ready = """\
{
  "ticket_id": "<ticket_id>",
  "status": "ready_for_verification",
  "self_review_notes": "All clean.",
  "new_gotchas": [],
  "timestamp": "<ISO-8601-UTC>"
}"""
    markdown = f"""\
```json
{bad_ready}
```
"""
    errors = validate_markdown_signal_examples(markdown, ticket_id="T100")
    assert len(errors) == 1
    assert "Block 0" in errors[0]
    assert "missing required field 'modified_files'" in errors[0]


def test_validate_markdown_signal_examples_unknown_ticket_placeholder_named() -> None:
    bad_ticket = """\
{
  "ticket_id": "<unknown_ticket_id>",
  "status": "ready_for_verification",
  "modified_files": ["foo.py"],
  "self_review_notes": "notes",
  "new_gotchas": [],
  "timestamp": "<ISO-8601-UTC>"
}"""
    markdown = f"""\
```json
{bad_ticket}
```
"""
    errors = validate_markdown_signal_examples(markdown, ticket_id="T100")
    assert len(errors) == 1
    assert "Block 0" in errors[0]
    assert "<unknown_ticket_id>" in errors[0]
