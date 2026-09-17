"""Unit tests for pure prompt-composition builder."""

from pathlib import Path
import pytest

from runner.adapters.markdown.spec_parser import SpecExcerpt
from runner.application.prompt_builder import PromptBuilder, build_prompt
from runner.domain.ticket import Ticket, TicketStatus


def _make_ticket(
    ticket_id: str = "T017",
    title: str = "Prompt builder and Spec Excerpt extraction",
    security_required: bool = False,
    spec_path: str = "docs/specs/03-worker-orchestration-and-handoff.md",
    requirements: tuple[str, ...] = ("Add pure prompt-builder.", "Add spec parser."),
    acceptance_criteria: tuple[str, ...] = ("Prompt contains required fields.",),
    gotchas: tuple[str, ...] = ("Do not inline skill body.",),
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=title,
        status=TicketStatus.PENDING,
        spec_path=spec_path,
        requirements=requirements,
        acceptance_criteria=acceptance_criteria,
        gotchas=gotchas,
        path=Path(f"docs/tickets/03-worker-orchestration-and-handoff/{ticket_id}-test.md"),
        security_required=security_required,
    )


SAMPLE_SPEC_EXCERPT = SpecExcerpt(
    text="## Problem Statement\n\nContext windows are limited.\n\n## Solution\n\nManage worker subprocess.",
    spec_path="docs/specs/03-worker-orchestration-and-handoff.md",
    problem_statement="Context windows are limited.",
    solution="Manage worker subprocess.",
)

SAMPLE_GLOBAL_GOTCHAS = """### Windows Subprocess Executable Resolution
- **Problem**: FileNotFoundError on Windows.
- **Solution**: Use shutil.which().
"""


def test_prompt_contains_all_core_ticket_fields() -> None:
    ticket = _make_ticket(
        ticket_id="T099",
        title="Custom Ticket Title",
        requirements=("First requirement with `code`.", "Second requirement."),
        acceptance_criteria=("AC criteria 1.", "AC criteria 2."),
        gotchas=("Local gotcha entry.",),
    )

    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "T099" in prompt
    assert "Custom Ticket Title" in prompt
    assert "First requirement with `code`." in prompt
    assert "Second requirement." in prompt
    assert "AC criteria 1." in prompt
    assert "AC criteria 2." in prompt
    assert "Local gotcha entry." in prompt


def test_prompt_contains_spec_excerpt_and_link() -> None:
    ticket = _make_ticket(spec_path="docs/specs/03-worker-orchestration-and-handoff.md")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "## Problem Statement" in prompt
    assert "Context windows are limited." in prompt
    assert "## Solution" in prompt
    assert "Manage worker subprocess." in prompt
    assert "docs/specs/03-worker-orchestration-and-handoff.md" in prompt


def test_prompt_contains_global_gotchas() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "Windows Subprocess Executable Resolution" in prompt
    assert "Use shutil.which()." in prompt


def test_prompt_uses_argument_execution_skill_path_not_hardcoded() -> None:
    ticket = _make_ticket()
    custom_skill = "custom/path/to/my_skill/SKILL.md"

    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=custom_skill,
    )

    assert custom_skill in prompt
    # Inlined skill body should not be present
    assert "disable-model-invocation: true" not in prompt


def test_prompt_forbids_git_add_and_git_commit() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "git add" in prompt
    assert "git commit" in prompt
    # Verify prohibition phrasing
    prompt_lower = prompt.lower()
    assert "forbid" in prompt_lower or "prohibit" in prompt_lower or "do not" in prompt_lower or "never" in prompt_lower


def test_prompt_ready_signal_instruction_with_real_ticket_id() -> None:
    ticket = _make_ticket(ticket_id="T042")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agent/signals/T042_ready.json" in prompt
    assert "self_review_notes" in prompt


def test_prompt_contains_diagnosing_bugs_skill_pointer() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agents/skills/diagnosing-bugs/SKILL.md" in prompt


def test_prompt_mandatory_code_review_present_in_both_modes() -> None:
    ticket_no_sec = _make_ticket(security_required=False)
    ticket_sec = _make_ticket(security_required=True)

    prompt_no_sec = build_prompt(
        ticket=ticket_no_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )
    prompt_sec = build_prompt(
        ticket=ticket_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "/code-review" in prompt_no_sec
    assert "/code-review" in prompt_sec


def test_prompt_conditional_security_review_toggle() -> None:
    ticket_sec = _make_ticket(security_required=True)
    ticket_no_sec = _make_ticket(security_required=False)

    prompt_sec = build_prompt(
        ticket=ticket_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )
    prompt_no_sec = build_prompt(
        ticket=ticket_no_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "/security-review" in prompt_sec
    assert "/security-review" not in prompt_no_sec


def test_prompt_builder_invocation_variants() -> None:
    ticket = _make_ticket()
    skill = ".agents/skills/implement/SKILL.md"

    # 1. build_prompt function
    res1 = build_prompt(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GLOBAL_GOTCHAS, skill)

    # 2. PromptBuilder instance without default
    res2 = PromptBuilder().build(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GLOBAL_GOTCHAS, skill)

    # 3. PromptBuilder instance with default
    res3 = PromptBuilder(execution_skill=skill).build(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GLOBAL_GOTCHAS)

    # 4. PromptBuilder classmethod
    res4 = PromptBuilder.build(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GLOBAL_GOTCHAS, skill)

    # 5. String spec_excerpt
    res5 = build_prompt(ticket, SAMPLE_SPEC_EXCERPT.text, SAMPLE_GLOBAL_GOTCHAS, skill)

    assert res1 == res2 == res3 == res4 == res5


def test_prompt_builder_verbatim_ticket_markdown_passthrough() -> None:
    verbatim_req = "Write `<generic>` & 'quotes' and regex `r\"^[a-z]+$\"` without escaping."
    ticket = _make_ticket(requirements=(verbatim_req,))

    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert verbatim_req in prompt


def test_prompt_documents_full_ready_signal_schema() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    # Signal path with ticket id
    assert ".agent/signals/T032_ready.json" in prompt

    # Required and optional schema fields
    assert "`ticket_id`: \"T032\"" in prompt
    assert "\"ready_for_verification\"" in prompt
    assert "`modified_files`" in prompt
    assert "`self_review_notes`" in prompt
    assert "`new_gotchas`" in prompt
    assert "`timestamp`" in prompt
    assert "`scope`" in prompt
    assert "never use a ticket number" in prompt


def test_prompt_documents_question_protocol_and_schema() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        global_gotchas=SAMPLE_GLOBAL_GOTCHAS,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    # Question protocol path and halt rule
    assert ".agent/questions/T032.json" in prompt
    assert "stop working immediately" in prompt.lower() or "stop working" in prompt.lower()

    # Question schema fields
    assert "`ticket_id`: \"T032\"" in prompt
    assert "`question`" in prompt
    assert "`type`: \"choice\" or \"text\"" in prompt
    assert "`options`" in prompt
    assert "`status`: \"pending\"" in prompt
    assert "`answer`: null" in prompt
    assert "`created_at`" in prompt

