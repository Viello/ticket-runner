"""Output sanitization engine for sandbox scaffolding and synchronization."""

from __future__ import annotations

import re
from typing import NamedTuple

FILE_KINDS: tuple[str, ...] = (
    "agents_md",
    "welcome_ticket",
    "ticket_runner_yaml",
    "gitignore",
    "skill_md",
    "python_src",
    "python_test",
)


class SanitizeRule(NamedTuple):
    """Rule defining a transformation applied to content for a given file kind."""

    file_kind: str
    pattern: re.Pattern[str]
    replacement: str
    rationale: str


WELCOME_TICKET_SPEC_PLACEHOLDER: str = "N/A (sandbox demo)"

SANITIZE_RULES: list[SanitizeRule] = [
    SanitizeRule(
        file_kind="agents_md",
        pattern=re.compile(r"\s*\(ADR\s*\d{4}\)"),
        replacement="",
        rationale=(
            "Strip project-local ADR references that dangle or collide in "
            "vendored copies while preserving sentence-terminating punctuation."
        ),
    ),
    SanitizeRule(
        file_kind="welcome_ticket",
        pattern=re.compile(r"docs/specs/[\w.-]+\.md"),
        replacement=WELCOME_TICKET_SPEC_PLACEHOLDER,
        rationale=(
            "Replace non-existent docs/specs path with a non-empty placeholder "
            "to satisfy domain ticket validation and markdown parser inference."
        ),
    ),
]


def apply_sanitization(text: str, file_kind: str) -> str:
    """Apply sanitization rules matching file_kind to input text.

    Args:
        text: The source content to sanitize.
        file_kind: One of FILE_KINDS or an arbitrary kind tag. Unknown kinds
            are returned unchanged.

    Returns:
        The sanitized text string. Pure and idempotent.
    """
    result = text
    for rule in SANITIZE_RULES:
        if rule.file_kind == file_kind:
            result = rule.pattern.sub(rule.replacement, result)
    return result
