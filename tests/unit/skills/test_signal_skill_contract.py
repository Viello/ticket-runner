"""Unit tests validating repository skill signal contracts (T132)."""

from __future__ import annotations

from pathlib import Path

from runner.domain.signal_contract import validate_markdown_signal_examples

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_EXECUTION_SKILL = (
    REPO_ROOT / ".agents" / "skills" / "implement-ticket-runner" / "SKILL.md"
)

STALE_QUESTION_BLOCK = """\
```json
{
  "ticket_id": "<ticket_id>",
  "question": "<clear concise description of the blocker and choices>",
  "context": "<relevant files or findings>",
  "timestamp": "<ISO-8601-UTC>"
}
```"""


def test_canonical_execution_skill_passes_contract() -> None:
    assert LOCAL_EXECUTION_SKILL.is_file(), f"Missing {LOCAL_EXECUTION_SKILL}"
    content = LOCAL_EXECUTION_SKILL.read_text(encoding="utf-8")
    errors = validate_markdown_signal_examples(content)
    assert errors == [], f"Expected 0 signal contract errors in canonical skill, got: {errors}"


def test_canonical_execution_skill_fails_if_stale_question_example_reintroduced() -> None:
    assert LOCAL_EXECUTION_SKILL.is_file(), f"Missing {LOCAL_EXECUTION_SKILL}"
    content = LOCAL_EXECUTION_SKILL.read_text(encoding="utf-8")
    tampered = content + f"\n\n## Reintroduced Stale Example\n\n{STALE_QUESTION_BLOCK}\n"
    errors = validate_markdown_signal_examples(tampered)
    assert len(errors) == 1
    assert "missing required field 'type'" in errors[0]
