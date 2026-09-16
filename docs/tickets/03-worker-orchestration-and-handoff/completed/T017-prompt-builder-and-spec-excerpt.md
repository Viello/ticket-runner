# T017 — Prompt builder and Spec Excerpt extraction
Status: completed
Completed: 2026-09-16T12:55:50Z
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add a pure prompt-composition module (e.g. `runner/application/prompt_builder.py`): given a `Ticket` (with `security_required`), Spec Excerpt text, global gotchas, and the configured `execution_skill` path, render the scoped Worker prompt containing (Spec 03 Implementation Decisions, ADRs 0008/0011/0013): ticket id/title/requirements/acceptance criteria/ticket gotchas; the Spec Excerpt plus a link to the full spec file; global gotchas from `docs/tickets/gotchas.md`; a directive to follow the execution skill at its path (pointer only, never the inlined body); mandatory `/code-review` before signaling and conditional `/security-review` when `security_required`; an explicit prohibition on `git add`/`git commit` in favor of the ready signal; the instruction to write `.agent/signals/{ticket_id}_ready.json` with `self_review_notes` on completion; and a pointer to `.agents/skills/diagnosing-bugs/SKILL.md` for non-trivial test failures.
- Add a Spec Excerpt extractor in `runner/adapters/markdown/spec_parser.py`: extract the `## Problem Statement` and `## Solution` sections (in that order) from a spec markdown file, returning the excerpt text together with the spec path for linking; a missing section or unreadable file raises a `TicketFormatError`-family error carrying actionable guidance.
- Keep the builder pure (inputs in, string out — no disk reads); callers gather excerpt and gotchas.
- Jump-start:
  - Files to touch: `runner/application/prompt_builder.py`, `runner/adapters/markdown/spec_parser.py`, `tests/unit/application/test_prompt_builder.py`, `tests/unit/adapters/test_spec_parser.py`.
  - Seams: `runner/adapters/markdown/__init__.py` re-exports parser/store modules; `GotchasStore.load()` and `Ticket.spec_path` are the runtime inputs T021 will pass in.
  - Anchor patterns: section parsing in `runner/adapters/markdown/parser.py`; CRLF/line-ending handling rules from gotchas.md.
  - Verification: `pytest tests/unit/application/test_prompt_builder.py tests/unit/adapters/test_spec_parser.py`.

### Acceptance Criteria
- With `security_required=True` the prompt contains the `/security-review` instruction; with `False` it is absent; every other required element above is present in both cases and includes the real ticket id in the ready-signal path.
- The prompt explicitly forbids staging/committing and names the execution skill path from the argument, not a hard-coded default.
- Excerpt extraction returns exactly the two sections' content from `docs/specs/03-worker-orchestration-and-handoff.md`-style files (tolerating CRLF) and raises the documented error when a section is missing.

### Gotchas
- Do not inline the execution skill body (ADR 0008) and do not embed spec content beyond the excerpt (ADR 0011).
- Keep formatting stable and assert it in tests — T024 treats the prompt contract as acceptance criteria, and Spec 04's retry loop reuses the builder for diagnostic prompts.
- Ticket content is pre-authored markdown; pass it through verbatim rather than escaping it.
- No `pytest-asyncio`; this module is synchronous.
