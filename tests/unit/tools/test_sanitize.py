"""Unit tests for runner.tools.sanitize."""

from __future__ import annotations

import re
import pytest

from runner.tools.sanitize import (
    FILE_KINDS,
    SANITIZE_RULES,
    SanitizeRule,
    apply_sanitization,
)


def test_file_kinds_registry() -> None:
    expected_kinds = (
        "agents_md",
        "welcome_ticket",
        "ticket_runner_yaml",
        "gitignore",
        "skill_md",
        "python_src",
        "python_test",
    )
    assert isinstance(FILE_KINDS, tuple)
    assert set(FILE_KINDS) == set(expected_kinds)
    assert len(FILE_KINDS) == 7


def test_sanitize_rules_structure() -> None:
    assert isinstance(SANITIZE_RULES, list)
    assert len(SANITIZE_RULES) >= 2
    for rule in SANITIZE_RULES:
        assert isinstance(rule, SanitizeRule)
        assert rule.file_kind in FILE_KINDS
        assert isinstance(rule.pattern, re.Pattern)
        assert isinstance(rule.replacement, str)
        assert isinstance(rule.rationale, str)
        assert rule.rationale.strip() != ""


def test_sanitize_agents_md_rule() -> None:
    sample = (
        "- OpenCode is invoked as a subprocess (ADR 0001).\n"
        "- Worker messages are durable (ADR 0004).\n"
        "- Only Gatekeeper passes tickets (ADR 0002).\n"
        "- Push guardrail installed (ADR 0005). Never push.\n"
        "- Single commit per ticket (ADR 0012).\n"
    )
    sanitized = apply_sanitization(sample, "agents_md")
    assert "(ADR" not in sanitized
    assert "- OpenCode is invoked as a subprocess.\n" in sanitized
    assert "- Worker messages are durable.\n" in sanitized
    assert "- Only Gatekeeper passes tickets.\n" in sanitized
    assert "- Push guardrail installed. Never push.\n" in sanitized
    assert "- Single commit per ticket.\n" in sanitized


def test_sanitize_welcome_ticket_rule() -> None:
    sample = (
        "# T001 — Hello World Welcome Ticket\n"
        "**Type:** wayfinder:task (AFK)\n"
        "Status: pending\n"
        "Spec: docs/specs/00-welcome.md\n"
        "Blocked by: none\n"
    )
    sanitized = apply_sanitization(sample, "welcome_ticket")
    assert "docs/specs/00-welcome.md" not in sanitized
    assert "docs/specs/" not in sanitized
    assert "Spec: N/A (sandbox demo)\n" in sanitized


def test_file_kind_dispatch_isolation() -> None:
    agents_text = "- Feature description (ADR 0001)."
    ticket_text = "Spec: docs/specs/00-welcome.md"

    # agents_md rule must not trigger for welcome_ticket
    assert apply_sanitization(agents_text, "welcome_ticket") == agents_text

    # welcome_ticket rule must not trigger for agents_md
    assert apply_sanitization(ticket_text, "agents_md") == ticket_text

    # No-op kinds do not alter either
    for kind in ("ticket_runner_yaml", "gitignore", "skill_md", "python_src", "python_test"):
        assert apply_sanitization(agents_text, kind) == agents_text
        assert apply_sanitization(ticket_text, kind) == ticket_text


def test_unknown_kind_passthrough() -> None:
    text = "Some text with (ADR 0001) and docs/specs/00-welcome.md"
    assert apply_sanitization(text, "unknown_kind") == text
    assert apply_sanitization(text, "") == text


def test_idempotence() -> None:
    samples = {
        "agents_md": "- Rule 1 (ADR 0001).\n- Rule 2 (ADR 0002).",
        "welcome_ticket": "Spec: docs/specs/00-welcome.md\nContent.",
        "ticket_runner_yaml": "project:\n  name: demo\n",
        "gitignore": ".agent/\n",
        "skill_md": "---\nname: implement\n---\n",
        "python_src": "def greet(): pass\n",
        "python_test": "def test_greet(): pass\n",
        "custom": "some random text",
    }
    for kind, text in samples.items():
        pass1 = apply_sanitization(text, kind)
        pass2 = apply_sanitization(pass1, kind)
        assert pass1 == pass2
