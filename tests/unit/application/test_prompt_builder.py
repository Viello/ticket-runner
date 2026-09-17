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

SAMPLE_GOTCHAS_PATH = "docs/tickets/gotchas.md"


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
        gotchas_path=SAMPLE_GOTCHAS_PATH,
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
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "## Problem Statement" in prompt
    assert "Context windows are limited." in prompt
    assert "## Solution" in prompt
    assert "Manage worker subprocess." in prompt
    assert "docs/specs/03-worker-orchestration-and-handoff.md" in prompt


def test_prompt_contains_global_gotchas_pointer() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "## Global Gotchas & Lessons Learned" in prompt
    assert "docs/tickets/gotchas.md" in prompt
    assert (
        "Review and adhere to all project-wide pitfalls recorded at `docs/tickets/gotchas.md` before implementing."
        in prompt
    )
    assert "Windows Subprocess Executable Resolution" not in prompt


def test_prompt_normalizes_windows_gotchas_path_to_posix() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=Path("docs") / "tickets" / "gotchas.md",
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "docs/tickets/gotchas.md" in prompt
    assert "docs\\tickets\\gotchas.md" not in prompt


def test_prompt_retains_ticket_gotchas_inlined_under_ticket_gotchas() -> None:
    ticket = _make_ticket(gotchas=("Specific ticket gotcha item.",))
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path="docs/tickets/gotchas.md",
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "### Ticket Gotchas" in prompt
    assert "- Specific ticket gotcha item." in prompt
    assert "## Global Gotchas & Lessons Learned" in prompt
    assert (
        "Review and adhere to all project-wide pitfalls recorded at `docs/tickets/gotchas.md` before implementing."
        in prompt
    )


def test_prompt_uses_argument_execution_skill_path_not_hardcoded() -> None:
    ticket = _make_ticket()
    custom_skill = "custom/path/to/my_skill/SKILL.md"

    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
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
        gotchas_path=SAMPLE_GOTCHAS_PATH,
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
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agent/signals/T042_ready.json" in prompt
    assert "self_review_notes" in prompt


def test_prompt_contains_diagnosing_bugs_skill_pointer() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agents/skills/diagnosing-bugs/SKILL.md" in prompt


def test_prompt_mandatory_code_review_present_in_both_modes() -> None:
    ticket_no_sec = _make_ticket(security_required=False)
    ticket_sec = _make_ticket(security_required=True)

    prompt_no_sec = build_prompt(
        ticket=ticket_no_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )
    prompt_sec = build_prompt(
        ticket=ticket_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agents/skills/code-review/SKILL.md" in prompt_no_sec
    assert ".agents/skills/code-review/SKILL.md" in prompt_sec
    assert "`/code-review`" not in prompt_no_sec
    assert "`/code-review`" not in prompt_sec


def test_prompt_conditional_security_review_toggle() -> None:
    ticket_sec = _make_ticket(security_required=True)
    ticket_no_sec = _make_ticket(security_required=False)

    prompt_sec = build_prompt(
        ticket=ticket_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )
    prompt_no_sec = build_prompt(
        ticket=ticket_no_sec,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agents/skills/security-review/SKILL.md" in prompt_sec
    assert ".agents/skills/security-review/SKILL.md" not in prompt_no_sec
    assert "`/security-review`" not in prompt_sec
    assert "`/security-review`" not in prompt_no_sec
    assert ".agents/skills/security-review/SKILL.md" not in prompt_no_sec


def test_prompt_builder_invocation_variants() -> None:
    ticket = _make_ticket()
    skill = ".agents/skills/implement/SKILL.md"

    # 1. build_prompt function
    res1 = build_prompt(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GOTCHAS_PATH, skill)

    # 2. PromptBuilder instance without default
    res2 = PromptBuilder().build(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GOTCHAS_PATH, skill)

    # 3. PromptBuilder instance with default
    res3 = PromptBuilder(execution_skill=skill).build(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GOTCHAS_PATH)

    # 4. PromptBuilder classmethod
    res4 = PromptBuilder.build(ticket, SAMPLE_SPEC_EXCERPT, SAMPLE_GOTCHAS_PATH, skill)

    # 5. String spec_excerpt
    res5 = build_prompt(ticket, SAMPLE_SPEC_EXCERPT.text, SAMPLE_GOTCHAS_PATH, skill)

    assert res1 == res2 == res3 == res4 == res5
    assert "docs/tickets/gotchas.md" in res1


def test_prompt_builder_verbatim_ticket_markdown_passthrough() -> None:
    verbatim_req = "Write `<generic>` & 'quotes' and regex `r\"^[a-z]+$\"` without escaping."
    ticket = _make_ticket(requirements=(verbatim_req,))

    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert verbatim_req in prompt


def test_prompt_documents_full_ready_signal_schema() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
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
        gotchas_path=SAMPLE_GOTCHAS_PATH,
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


def test_prompt_command_length_with_real_gotchas_remains_well_below_ceiling() -> None:
    from runner.adapters.opencode.opencode_worker import build_opencode_run_command

    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path="docs/tickets/gotchas.md",
        execution_skill=".agents/skills/implement/SKILL.md",
    )
    cmd = build_opencode_run_command(prompt)
    total_length = sum(len(arg) for arg in cmd) + len(cmd) - 1
    # Windows ceiling is 32,767; prompt pointer + inlined invariants keeps command below 6,000 chars
    assert total_length < 7000
    assert total_length < 32767


def test_prompt_inlines_agents_md_invariants() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "## Invariants" in prompt
    assert "OpenCode is invoked as a subprocess" in prompt
    assert "Gatekeeper" in prompt


def test_prompt_startup_section_explicit_file_reading_directives() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    # Startup section explicitly instructs reading execution skill, followed by AGENTS.md, using file-reading tool
    assert "read" in prompt.lower()
    assert ".agents/skills/implement/SKILL.md" in prompt
    assert "AGENTS.md" in prompt
    assert "(pointer only; do not inline or modify)" not in prompt


def test_prompt_review_section_file_reading_directives_and_self_review_notes() -> None:
    ticket = _make_ticket(security_required=True)
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agents/skills/code-review/SKILL.md" in prompt
    assert ".agents/skills/security-review/SKILL.md" in prompt
    assert "self_review_notes" in prompt
    assert "`/code-review`" not in prompt
    assert "`/security-review`" not in prompt


def test_prompt_debugging_guidance_explicit_read_directive() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert ".agents/skills/diagnosing-bugs/SKILL.md" in prompt
    assert "read" in prompt.lower()
    assert "consult `.agents/skills/diagnosing-bugs/SKILL.md`" not in prompt


def test_prompt_resilient_invariants_fallback_when_agents_md_missing_or_corrupt(tmp_path: Path) -> None:
    from runner.application.prompt_builder import extract_invariants

    missing_path = tmp_path / "NON_EXISTENT_AGENTS.md"
    extracted_missing = extract_invariants(missing_path)
    assert "## Invariants" in extracted_missing
    assert "Gatekeeper" in extracted_missing

    corrupt_path = tmp_path / "CORRUPT_AGENTS.md"
    corrupt_path.write_text("# Heading without invariants\nSome text\n", encoding="utf-8")
    extracted_corrupt = extract_invariants(corrupt_path)
    assert "## Invariants" in extracted_corrupt
    assert "Gatekeeper" in extracted_corrupt

    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
        agents_path=missing_path,
    )
    assert "## Invariants" in prompt


