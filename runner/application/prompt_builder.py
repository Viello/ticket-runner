"""Pure prompt-composition module for OpenCode Worker sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runner.adapters.markdown.spec_parser import SpecExcerpt
from runner.domain.ticket import Ticket


def _format_bullets(items: tuple[str, ...] | list[str], default_empty: str = "- None") -> str:
    if not items:
        return default_empty
    bullets: list[str] = []
    for item in items:
        clean = item.strip()
        if clean.startswith("- "):
            bullets.append(clean)
        else:
            bullets.append(f"- {clean}")
    return "\n".join(bullets)


def _format_global_gotchas(global_gotchas: str) -> str:
    clean = global_gotchas.strip()
    if not clean:
        return "## Global Gotchas & Lessons Learned\n\nNone recorded."
    if clean.startswith("# Global Gotchas"):
        return clean
    return f"## Global Gotchas & Lessons Learned\n\n{clean}"


def build_prompt(
    ticket: Ticket,
    spec_excerpt: SpecExcerpt | str,
    global_gotchas: str,
    execution_skill: str | Path,
    *,
    spec_path: str | None = None,
) -> str:
    """Render a pure scoped prompt for an OpenCode Worker session.

    Args:
        ticket: Active Ticket domain entity.
        spec_excerpt: SpecExcerpt object or excerpt markdown string.
        global_gotchas: Global gotchas text from docs/tickets/gotchas.md.
        execution_skill: Path to the configured execution skill file.
        spec_path: Optional explicit path to the spec file; inferred if omitted.

    Returns:
        Rendered prompt string containing all operational rules and scoped context.
    """
    skill_path = Path(execution_skill).as_posix()

    if isinstance(spec_excerpt, SpecExcerpt):
        excerpt_text = spec_excerpt.text.strip()
        resolved_spec_path = spec_path or spec_excerpt.spec_path or ticket.spec_path
    else:
        excerpt_text = str(spec_excerpt).strip()
        resolved_spec_path = spec_path or ticket.spec_path

    resolved_spec_path = Path(resolved_spec_path).as_posix()

    requirements_text = _format_bullets(ticket.requirements)
    ac_text = _format_bullets(ticket.acceptance_criteria)
    gotchas_text = _format_bullets(ticket.gotchas)
    formatted_global_gotchas = _format_global_gotchas(global_gotchas)

    security_review_line = ""
    if ticket.security_required:
        security_review_line = (
            "\n   - Mandatory `/security-review`: Conduct a `/security-review` self-check as required "
            "by ticket frontmatter (`Security: required`) before signaling completion."
        )

    prompt = f"""# Ticket Task: {ticket.id} — {ticket.title}

## Execution Skill & Discipline
Follow the execution skill instructions located at `{skill_path}` (pointer only; do not inline or modify). Apply its core implementation discipline:
- Test-Driven Development (TDD) at pre-agreed seams.
- Regular typechecks and test runs to maintain a green test suite.

## Architectural Context (Spec Excerpt)
Full specification reference: `{resolved_spec_path}`

{excerpt_text}

## Active Ticket Details
### {ticket.id} — {ticket.title}

### Requirements
{requirements_text}

### Acceptance Criteria
{ac_text}

### Ticket Gotchas
{gotchas_text}

{formatted_global_gotchas}

## Operational Guardrails & Completion Protocol
1. **No Git Staging or Commits**: Do NOT run `git add` or `git commit`. Worker git commits and staging are strictly forbidden. Git staging and atomic commits are managed exclusively by the Gatekeeper upon independent verification.
2. **Review Self-Checks**:
   - Mandatory `/code-review`: Conduct a `/code-review` self-check against standards and spec/ticket acceptance criteria before signaling completion.{security_review_line}
3. **Debugging Guidance**: For non-trivial test failures or hard bugs, consult `.agents/skills/diagnosing-bugs/SKILL.md`.
4. **Ready Signal Protocol**: When implementation and self-reviews are complete, emit the ready signal by writing `.agent/signals/{ticket.id}_ready.json`.
   The ready Signal JSON payload must follow this exact schema:
   - `ticket_id`: "{ticket.id}" (must match this active ticket)
   - `status`: "ready_for_verification"
   - `modified_files`: array of strings containing repository-relative paths modified during this ticket (e.g. `["runner/application/foo.py"]`)
   - `self_review_notes`: string summarizing findings, verification results, and standards compliance
   - `new_gotchas`: array of newly discovered runtime gotchas or lessons learned strings (empty array `[]` if none)
   - `timestamp`: current ISO-8601 UTC timestamp string
   - `scope`: optional lowercase architectural layer token (e.g. "application", "domain", "adapters"; omit or null to use the default queue scope; never use a ticket number)
5. **Question Protocol (Clarification / Blocked)**:
   If blocked, requirements are ambiguous, or an architectural decision is required:
   - Write a question Signal to `.agent/questions/{ticket.id}.json` and **stop working immediately**. Do not guess or continue working while blocked.
   The question Signal JSON payload must follow this exact schema:
   - `ticket_id`: "{ticket.id}"
   - `question`: string describing the clarifying question
   - `type`: "choice" or "text"
   - `options`: array of choice strings when type is "choice", or null when type is "text"
   - `status`: "pending"
   - `answer`: null
   - `created_at`: current ISO-8601 UTC timestamp string
"""
    return prompt


class _BuildDispatcher:
    """Descriptor supporting invocation on either PromptBuilder class or instance."""

    def __get__(self, instance: PromptBuilder | None, owner: type[PromptBuilder]) -> Any:
        if instance is None:
            def _class_build(
                ticket: Ticket,
                spec_excerpt: SpecExcerpt | str,
                global_gotchas: str,
                execution_skill: str | Path,
                *,
                spec_path: str | None = None,
            ) -> str:
                return build_prompt(
                    ticket=ticket,
                    spec_excerpt=spec_excerpt,
                    global_gotchas=global_gotchas,
                    execution_skill=execution_skill,
                    spec_path=spec_path,
                )
            return _class_build

        def _instance_build(
            ticket: Ticket,
            spec_excerpt: SpecExcerpt | str,
            global_gotchas: str,
            execution_skill: str | Path | None = None,
            *,
            spec_path: str | None = None,
        ) -> str:
            skill = execution_skill or instance.default_execution_skill
            if skill is None:
                raise ValueError("execution_skill must be provided either at init or build call")
            return build_prompt(
                ticket=ticket,
                spec_excerpt=spec_excerpt,
                global_gotchas=global_gotchas,
                execution_skill=skill,
                spec_path=spec_path,
            )

        return _instance_build


class PromptBuilder:
    """Pure prompt-composition builder for OpenCode Worker sessions."""

    def __init__(self, execution_skill: str | Path | None = None) -> None:
        self.default_execution_skill = (
            Path(execution_skill).as_posix() if execution_skill is not None else None
        )

    build = _BuildDispatcher()
    build_prompt = staticmethod(build_prompt)
