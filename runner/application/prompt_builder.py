"""Pure prompt-composition module for OpenCode Worker sessions."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from runner.adapters.markdown.spec_parser import SpecExcerpt
from runner.domain.ticket import Ticket

DEFAULT_INVARIANTS = """## Invariants
- OpenCode is invoked as a subprocess, never a daemon: `opencode run --format json --session <id> --auto "<prompt>"`; resume with the same session id (ADR 0001).
- Worker executes tickets via configured `worker.execution_skill` (`.agents/skills/implement/SKILL.md`), performing pre-signal reviews, but never commits directly
- Worker↔Runner messages are durable JSON files (`.agent/signals/{ticket_id}_ready.json`, `.agent/questions/{ticket_id}.json`) — never parse model stdout for state (ADR 0004).
- Only the Runner's Gatekeeper passes a ticket, by running configured test/build commands; Worker self-reports don't count; 3 failed attempts trip the circuit breaker (ADR 0002).
- All automated work happens on `agent/ticket-runner`; the Runner stages and commits, and `.git/hooks/pre-push` blocks pushes (ADR 0005). Never `git push`.
- Commit format: Title must be `<type>(<scope>): <Title>` where `<scope>` names the architectural layer or subsystem (`packaging`, `domain`, `ports`, `adapters`, `git`, `doctor`, `queue`, `discord`, `ui`), never a ticket number. Follow with a blank line and hyphen-bulleted (`- <action>`) imperative changes without trailing periods. No ticket numbers in title or body.
- Token budget: warn 120k, handoff 135k, hard ceiling 150k; handoff writes `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- Single commit per ticket: Gatekeeper approval authors exactly one commit combining code, tests, newly logged gotchas, and the relocated ticket file (`Status: completed`); never record commit SHA in ticket frontmatter (ADR 0012).
- Source of truth: Working code, unit tests, and CLI interfaces are authoritative over markdown documentation. Specifications and tickets are ephemeral scaffolding; never modify root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`) without explicit user approval.
- `.agent/` is untracked runtime state; git-ignore it when implementing."""

INVARIANTS_HEADING_PATTERN = re.compile(r"^##\s+Invariants\s*$", re.IGNORECASE)
ANY_H2_HEADING_PATTERN = re.compile(r"^##\s+", re.IGNORECASE)


def extract_invariants(agents_path: str | Path = "AGENTS.md") -> str:
    """Extract and sanitize the '## Invariants' section from AGENTS.md.

    Falls back gracefully to standard core invariants if AGENTS.md is missing,
    unreadable, or lacks the '## Invariants' heading.
    """
    path = Path(agents_path)
    try:
        if not path.is_file():
            return DEFAULT_INVARIANTS
        content = path.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_INVARIANTS

    lines = content.splitlines()
    invariants_lines: list[str] = []
    found_heading = False

    for line in lines:
        if not found_heading:
            if INVARIANTS_HEADING_PATTERN.match(line.strip()):
                found_heading = True
            continue

        if ANY_H2_HEADING_PATTERN.match(line.strip()):
            break

        invariants_lines.append(line)

    extracted = "\n".join(invariants_lines).strip()
    if not extracted:
        return DEFAULT_INVARIANTS

    # Sanitize any residual interactive slash commands from the extracted block
    cleaned = (
        extracted.replace("`/code-review`", "code-review")
        .replace("`/security-review`", "security-review")
        .replace("/code-review", "code-review")
        .replace("/security-review", "security-review")
    )
    return f"## Invariants\n{cleaned}"


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


def _format_global_gotchas(gotchas_path: str | Path = "docs/tickets/gotchas.md") -> str:
    path_str = str(gotchas_path).strip()
    if "\n" in path_str or path_str.startswith("#"):
        posix_path = "docs/tickets/gotchas.md"
    elif not path_str:
        posix_path = "docs/tickets/gotchas.md"
    else:
        posix_path = Path(path_str).as_posix()
    return (
        f"## Global Gotchas & Lessons Learned\n"
        f"Review and adhere to all project-wide pitfalls recorded at `{posix_path}` before implementing."
    )


def build_prompt(
    ticket: Ticket,
    spec_excerpt: SpecExcerpt | str,
    gotchas_path: str | Path = "docs/tickets/gotchas.md",
    execution_skill: str | Path = ".agents/skills/implement/SKILL.md",
    *,
    spec_path: str | None = None,
    global_gotchas: str | None = None,
    agents_path: str | Path = "AGENTS.md",
) -> str:
    """Render a pure scoped prompt for an OpenCode Worker session.

    Args:
        ticket: Active Ticket domain entity.
        spec_excerpt: SpecExcerpt object or excerpt markdown string.
        gotchas_path: Path to docs/tickets/gotchas.md (emitted as a scoped pointer).
        execution_skill: Path to the configured execution skill file.
        spec_path: Optional explicit path to the spec file; inferred if omitted.
        global_gotchas: Optional legacy alias for gotchas_path.
        agents_path: Path to AGENTS.md for inlining repository invariants.

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
    effective_gotchas = global_gotchas if global_gotchas is not None else gotchas_path
    formatted_global_gotchas = _format_global_gotchas(effective_gotchas)

    invariants_text = extract_invariants(agents_path)

    security_review_line = ""
    if ticket.security_required:
        security_review_line = (
            "\n   - Mandatory Security Review: Read `.agents/skills/security-review/SKILL.md` "
            "using your file-reading tool as required by ticket frontmatter (`Security: required`) "
            "and summarize findings in `self_review_notes`."
        )

    prompt = f"""# Ticket Task: {ticket.id} — {ticket.title}

## Execution Skill & Discipline
Before writing or modifying any code, use your file-reading tool (e.g. `read`) to first read and adhere to `{skill_path}`, and then read `AGENTS.md` to ground your work in project-wide architectural constraints. Apply the core implementation discipline:
- Test-Driven Development (TDD) at pre-agreed seams.
- Fast Feedback Loop: Run targeted single test files matching modified modules (e.g. `python -m pytest tests/unit/application/test_foo.py -x`). Do NOT run the full test suite repeatedly during development loops.
- Windows Shell Environment: Subcommands run under Windows PowerShell. Never pipe test output to Unix-only utilities (`tail`, `grep`, `head`) as they do not exist on Windows.
- Broad Suite Check: Run broader test suites only once implementation passes targeted tests, immediately before emitting the ready signal.

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
{invariants_text}

1. **No Git Staging or Commits**: Do NOT run `git add` or `git commit`. Worker git commits and staging are strictly forbidden. Git staging and atomic commits are managed exclusively by the Gatekeeper upon independent verification.
2. **Review Self-Checks**:
   - Mandatory Code Review: Read `.agents/skills/code-review/SKILL.md` using your file-reading tool and summarize standards and spec verification findings in `self_review_notes`.{security_review_line}
3. **Debugging Guidance**: For non-trivial test failures or hard bugs, read `.agents/skills/diagnosing-bugs/SKILL.md` using your file-reading tool.
4. **Ready Signal Protocol**: When implementation and self-reviews are complete, emit the ready signal by writing `.agent/signals/{ticket.id}_ready.json`.
   The ready Signal JSON payload must follow this exact schema:
   - `ticket_id`: "{ticket.id}" (must match this active ticket)
   - `status`: "ready_for_verification"
   - `modified_files`: array of strings containing repository-relative paths modified during this ticket (e.g. `["runner/application/foo.py"]`)
   - `self_review_notes`: string summarizing findings, verification results, and standards compliance
   - `new_gotchas`: array of newly discovered runtime gotchas or lessons learned strings (empty array `[]` if none)
   - `manual_verification`: array of objects `[{{"name": "...", "setup": "...", "steps": "...", "expected": "..."}}]` for Smoke Scenarios requiring human verification (empty array `[]` if all are automated)
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
                gotchas_path: str | Path = "docs/tickets/gotchas.md",
                execution_skill: str | Path = ".agents/skills/implement/SKILL.md",
                *,
                spec_path: str | None = None,
                global_gotchas: str | None = None,
                agents_path: str | Path = "AGENTS.md",
            ) -> str:
                return build_prompt(
                    ticket=ticket,
                    spec_excerpt=spec_excerpt,
                    gotchas_path=gotchas_path,
                    execution_skill=execution_skill,
                    spec_path=spec_path,
                    global_gotchas=global_gotchas,
                    agents_path=agents_path,
                )
            return _class_build

        def _instance_build(
            ticket: Ticket,
            spec_excerpt: SpecExcerpt | str,
            gotchas_path: str | Path | None = None,
            execution_skill: str | Path | None = None,
            *,
            spec_path: str | None = None,
            global_gotchas: str | None = None,
            agents_path: str | Path | None = None,
        ) -> str:
            skill = execution_skill or instance.default_execution_skill or ".agents/skills/implement/SKILL.md"
            path = gotchas_path or instance.default_gotchas_path
            agents = agents_path or instance.default_agents_path
            return build_prompt(
                ticket=ticket,
                spec_excerpt=spec_excerpt,
                gotchas_path=path,
                execution_skill=skill,
                spec_path=spec_path,
                global_gotchas=global_gotchas,
                agents_path=agents,
            )

        return _instance_build


class PromptBuilder:
    """Pure prompt-composition builder for OpenCode Worker sessions."""

    def __init__(
        self,
        execution_skill: str | Path | None = None,
        gotchas_path: str | Path | None = None,
        agents_path: str | Path | None = None,
    ) -> None:
        self.default_execution_skill = (
            Path(execution_skill).as_posix() if execution_skill is not None else None
        )
        self.default_gotchas_path = (
            Path(gotchas_path).as_posix() if gotchas_path is not None else "docs/tickets/gotchas.md"
        )
        self.default_agents_path = (
            Path(agents_path).as_posix() if agents_path is not None else "AGENTS.md"
        )

    build = _BuildDispatcher()
    build_prompt = staticmethod(build_prompt)
    extract_invariants = staticmethod(extract_invariants)
