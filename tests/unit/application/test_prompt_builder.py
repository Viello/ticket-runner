"""Unit tests for pure prompt-composition builder."""

from pathlib import Path

from runner.adapters.markdown.spec_parser import SpecExcerpt
from runner.application.prompt_builder import PromptBuilder, build_prompt
from runner.domain.signal import QuestionSignal, ReadySignal
from runner.domain.signal_schema import (
    render_question_signal_protocol,
    render_ready_signal_protocol,
)
from runner.domain.ticket import Ticket, TicketStatus


def _make_ticket(
    ticket_id: str = "T017",
    title: str = "Prompt builder and Spec Excerpt extraction",
    security_required: bool = False,
    spec_path: str = "docs/specs/03-worker-orchestration-and-handoff.md",
    requirements: tuple[str, ...] = ("Add pure prompt-builder.", "Add spec parser."),
    acceptance_criteria: tuple[str, ...] = ("Prompt contains required fields.",),
    gotchas: tuple[str, ...] = ("Do not inline skill body.",),
    jump_start: tuple[str, ...] = (),
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
        jump_start=jump_start,
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


def test_prompt_forbids_queue_file_mutations_and_gotchas_direct_edits() -> None:
    ticket = _make_ticket()
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "No Git Staging, Commits, or Queue File Mutations" in prompt
    assert "docs/tickets/gotchas.md" in prompt
    prompt_lower = prompt.lower()
    assert "do not edit `docs/tickets/gotchas.md` directly" in prompt_lower or "do not edit docs/tickets/gotchas.md directly" in prompt_lower
    assert "modifying, moving, or deleting any ticket markdown file under `docs/tickets/`" in prompt_lower or "modify, move, or delete any ticket markdown file under `docs/tickets/`" in prompt_lower


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
    assert "Explicit Security Mandate" in prompt_sec
    assert "Security: required" in prompt_sec
    assert "Explicit Security Mandate" not in prompt_no_sec
    assert "`Security` axis" in prompt_sec
    assert "`Security` axis" not in prompt_no_sec
    assert "`/security-review`" not in prompt_sec
    assert "`/security-review`" not in prompt_no_sec


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
    for field_name in ReadySignal.__dataclass_fields__:
        assert f"`{field_name}`" in prompt
    assert "\"ready_for_verification\"" in prompt
    assert "never a ticket number" in prompt


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
    for field_name in QuestionSignal.__dataclass_fields__:
        assert f"`{field_name}`" in prompt
    assert "\"choice\"" in prompt
    assert "\"text\"" in prompt
    assert "\"pending\"" in prompt


def test_prompt_renders_ready_signal_protocol_from_domain_authority() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement-ticket-runner/SKILL.md",
    )

    ready_protocol = render_ready_signal_protocol("T032")
    assert ready_protocol in prompt

    for field_name in ReadySignal.__dataclass_fields__:
        assert f"`{field_name}`" in prompt
    assert "\"ready_for_verification\"" in prompt
    assert ".agent/signals/T032_ready.json" in prompt


def test_prompt_renders_question_signal_protocol_from_domain_authority() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement-ticket-runner/SKILL.md",
    )

    question_protocol = render_question_signal_protocol("T032")
    assert question_protocol in prompt

    for field_name in QuestionSignal.__dataclass_fields__:
        assert f"`{field_name}`" in prompt
    assert ".agent/questions/T032.json" in prompt


def test_prompt_protocols_declare_themselves_authoritative() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement-ticket-runner/SKILL.md",
    )

    authority_sentence = (
        "This section is the single authority for this Signal payload schema: if the "
        "execution skill or any other document shows a different example, follow this section."
    )
    assert prompt.count(authority_sentence) >= 2


def test_prompt_teaches_canonical_gotcha_shape_with_string_fallback_without_fix_alias() -> None:
    ticket = _make_ticket(ticket_id="T032")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement-ticket-runner/SKILL.md",
    )

    assert "\"problem\":" in prompt
    assert "\"solution\":" in prompt
    assert "plain strings are also accepted" in prompt
    assert "\"fix\"" not in prompt


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
    # Windows ceiling is 32,767; prompt pointer + inlined invariants keeps command below 10,000 chars
    assert total_length < 10000
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
    assert "Agent backends (OpenCode, Antigravity CLI) are invoked as subprocesses" in prompt
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


def test_prompt_ready_signal_schema_excludes_manual_verification() -> None:
    ticket = _make_ticket(ticket_id="T079")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    assert "`manual_verification`" not in prompt
    assert "auto_covered" not in prompt
    assert "update_notes" not in prompt


def test_prompt_documents_live_qa_verification_contract() -> None:
    ticket = _make_ticket(ticket_id="T079")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        execution_skill=".agents/skills/implement/SKILL.md",
    )

    prompt_lower = prompt.lower()
    assert "smoke scenario" not in prompt_lower
    assert "smoke scenarios" not in prompt_lower
    assert "manual_verification" not in prompt_lower
    assert "/live-qa" in prompt
    assert "The Worker drafts no scenarios and self-reports no manual verification." in prompt


def test_prompt_renders_canonical_specimen_a_sections_with_jump_start() -> None:
    ticket = _make_ticket(
        ticket_id="T124",
        title="Canonical to-ticket-runner Document Model",
        requirements=("The end-to-end behavior from user perspective.",),
        jump_start=(
            "**Files/areas to touch:**",
            "`runner/domain/ticket.py`",
            "**Seams:** Document I/O boundary",
            "**Existing-code anchors:** Ticket dataclass",
        ),
        acceptance_criteria=("First criterion completed",),
        gotchas=("Remember to handle inline rationale in security.",),
    )
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert "### What to build" in prompt
    assert "- The end-to-end behavior from user perspective." in prompt
    assert "### Jump-start" in prompt
    assert "- **Files/areas to touch:**" in prompt
    assert "- `runner/domain/ticket.py`" in prompt
    assert "- **Seams:** Document I/O boundary" in prompt
    assert "### Acceptance criteria" in prompt
    assert "- First criterion completed" in prompt
    assert "### Ticket Gotchas" in prompt
    assert "- Remember to handle inline rationale in security." in prompt


def test_prompt_omits_jump_start_when_empty() -> None:
    ticket = _make_ticket(
        ticket_id="T099",
        jump_start=(),
    )
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert "### What to build" in prompt
    assert "### Acceptance criteria" in prompt
    assert "### Ticket Gotchas" in prompt
    assert "### Jump-start" not in prompt


def test_prompt_states_spec_17_checkbox_tick_permission_boundary() -> None:
    ticket = _make_ticket(ticket_id="T127")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert "flip satisfied criteria from `- [ ]` to `- [x]` under `## Acceptance criteria` in the active ticket file" in prompt
    assert "before emitting `.agent/signals/T127_ready.json`" in prompt
    assert "strictly forbidden from modifying any other line or section of the active ticket file" in prompt
    assert "editing `docs/tickets/gotchas.md` directly" in prompt
    assert "touching any other file under `docs/tickets/`" in prompt


def test_prompt_instructs_review_and_severity_gated_escalation_when_security_required() -> None:
    ticket = _make_ticket(ticket_id="T127", security_required=True)
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert ".agents/skills/code-review/SKILL.md" in prompt
    assert ".agents/skills/security-review/SKILL.md" in prompt
    assert "Standards" in prompt
    assert "Spec" in prompt
    assert "Security" in prompt
    assert "Low and Medium findings never interrupt the human" in prompt
    assert "Critical and High findings must be remediated in-pass" in prompt
    assert "Only if remediation is blocked" in prompt
    assert ".agent/questions/T127.json" in prompt


def test_prompt_omits_security_axis_when_not_required() -> None:
    ticket = _make_ticket(ticket_id="T127", security_required=False)
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert ".agents/skills/code-review/SKILL.md" in prompt
    assert ".agents/skills/security-review/SKILL.md" not in prompt
    assert "Standards" in prompt
    assert "Spec" in prompt
    assert "`Security` axis" not in prompt


def test_prompt_default_execution_skill_resolves_to_implement_ticket_runner() -> None:
    ticket = _make_ticket(ticket_id="T127")
    prompt = build_prompt(
        ticket=ticket,
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert ".agents/skills/implement-ticket-runner/SKILL.md" in prompt


def test_prompt_renders_configured_token_budget(tmp_path: Path) -> None:
    from runner.domain.config import TokenBudgetConfig

    agents = tmp_path / "AGENTS.md"
    agents.write_text("## Invariants\n- Stay scoped.\n", encoding="utf-8")

    prompt = build_prompt(
        ticket=_make_ticket(ticket_id="T130"),
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        agents_path=agents,
        token_budget=TokenBudgetConfig(warn=180_000, handoff=190_000, ceiling=200_000),
    )

    assert "warn 180k, handoff 190k, hard ceiling 200k" in prompt


def test_prompt_replaces_stale_token_budget_line_without_duplicating(tmp_path: Path) -> None:
    from runner.domain.config import TokenBudgetConfig

    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "## Invariants\n"
        "- Token budget: warn 120k, handoff 135k, hard ceiling 150k; handoff writes the checkpoint.\n"
        "- Stay scoped.\n",
        encoding="utf-8",
    )

    prompt = build_prompt(
        ticket=_make_ticket(ticket_id="T131"),
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
        agents_path=agents,
        token_budget=TokenBudgetConfig(warn=180_000, handoff=190_000, ceiling=200_000),
    )

    assert prompt.count("- Token budget:") == 1
    assert "warn 180k, handoff 190k, hard ceiling 200k" in prompt
    assert "warn 120k" not in prompt


def test_prompt_builder_instance_forwards_token_budget(tmp_path: Path) -> None:
    from runner.domain.config import TokenBudgetConfig

    agents = tmp_path / "AGENTS.md"
    agents.write_text("## Invariants\n- Stay scoped.\n", encoding="utf-8")

    builder = PromptBuilder(
        agents_path=agents,
        token_budget=TokenBudgetConfig(warn=180_000, handoff=190_000, ceiling=200_000),
    )

    prompt = builder.build(
        ticket=_make_ticket(ticket_id="T132"),
        spec_excerpt=SAMPLE_SPEC_EXCERPT,
        gotchas_path=SAMPLE_GOTCHAS_PATH,
    )

    assert "warn 180k, handoff 190k, hard ceiling 200k" in prompt




def test_implement_ticket_runner_skill_mandates_explicit_file_read_for_code_review_and_agents_md() -> None:
    """Execution skill must name '.agents/skills/code-review/SKILL.md' and 'AGENTS.md' for file-reading tool access."""
    skill_path = Path(".agents/skills/implement-ticket-runner/SKILL.md")
    content = skill_path.read_text(encoding="utf-8")

    assert ".agents/skills/code-review/SKILL.md" in content
    assert "AGENTS.md" in content
    assert "Run `/code-review` before signalling readiness:" not in content


def test_ready_signal_protocol_reminds_worker_to_read_code_review_skill_and_agents_md() -> None:
    """Ready Signal Protocol section reminds the worker to have read code-review/SKILL.md and AGENTS.md."""
    protocol = render_ready_signal_protocol("T008")
    assert ".agents/skills/code-review/SKILL.md" in protocol
    assert "AGENTS.md" in protocol
