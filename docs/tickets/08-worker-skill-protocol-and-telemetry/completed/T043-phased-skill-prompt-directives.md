# T043 — Phased skill and AGENTS.md prompt directives
Status: completed
Completed: 2026-09-17T15:14:00Z
Spec: docs/specs/08-worker-skill-protocol-and-telemetry.md
Blocked by: None

### Requirements
- Update `runner/application/prompt_builder.py` to direct Worker execution through explicit file-reading tool directives instead of passive pointer notes or interactive slash commands.
- Extract and inline the `## Invariants` section from `AGENTS.md` directly into the prompt's operational guardrails section, providing immediate grounding in project constraints.
- Instruct the Worker to first read and adhere to `worker.execution_skill` (`{skill_path}`) using its file-reading tool (e.g. `read`), and then read `AGENTS.md` before writing or modifying any code.
- Replace interactive `/code-review` and `/security-review` slash-command references with positive instructions to read `.agents/skills/code-review/SKILL.md` (and `.agents/skills/security-review/SKILL.md` when `ticket.security_required` is true) and record findings in the `self_review_notes` field of the ready Signal.
- Update debugging guidance to direct reading `.agents/skills/diagnosing-bugs/SKILL.md` with the file-reading tool.
- Jump-start:
  - Files to touch: `runner/application/prompt_builder.py`, `tests/unit/application/test_prompt_builder.py`.
  - Seams: `PromptBuilder.build()` pure string rendering.
  - Anchor patterns: Spec excerpt extraction and inlining in `PromptBuilder`.
  - Verification: `python -m pytest tests/unit/application/test_prompt_builder.py`.

### Acceptance Criteria
- Rendered prompt inlines the `## Invariants` block extracted from `AGENTS.md`.
- Startup section explicitly instructs reading `{skill_path}`, followed by reading `AGENTS.md`, using the file-reading tool.
- Review section explicitly instructs reading `.agents/skills/code-review/SKILL.md` and summarizing findings in `self_review_notes`.
- When `ticket.security_required` is true, review section explicitly instructs reading `.agents/skills/security-review/SKILL.md` and summarizing findings in `self_review_notes`.
- Prompt contains no interactive slash commands (`/code-review`, `/security-review`) and no confusing `(pointer only; do not inline or modify)` text.
- Full `test_prompt_builder.py` test suite is green.

### Gotchas
- `AGENTS.md` extraction must be resilient: if `AGENTS.md` is unreadable or lacks an `## Invariants` header, fall back gracefully to standard core invariants rather than raising an unhandled exception.
- Keep inlined invariants concise (~250 tokens) to ensure the total command string remains safely below the Windows 32,767 character ceiling.
