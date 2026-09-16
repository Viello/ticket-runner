# T029 — Intervention port and terminal menu
Status: completed
Completed: 2026-09-16T16:43:21Z
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: none

### Requirements
- Define an `InterventionGateway` port for human contact: `ask_question(question)` returns the answer text; `request_intervention(ticket, diagnostics, attempt)` returns an `InterventionDecision(action, hint)` with actions `retry`, `skip`, or `abort`.
- Terminal adapter implementing the agreed menu contract: `[R]etry [hint]` with an optional single-line hint, `[S]kip` behind one explicit `[y/N]` confirmation because it discards uncommitted edits, `[A]bort` immediate; inputs case-insensitive; unrecognized input re-prompts; an empty confirmation answer defaults to no.
- Non-interactive stdin falls back safely: question prompts raise a domain error; the menu returns `abort` — the Runner must never silently continue.
- Scriptable fake that queues answers and decisions, records every prompt and diagnostics payload, and fails loudly when exhausted.
- Jump-start:
  - Files to touch: `runner/ports/intervention.py` (new), `runner/adapters/ui/__init__.py` and `runner/adapters/ui/terminal_prompts.py` (new), `tests/fakes/fake_intervention.py` (new), `tests/unit/adapters/test_terminal_prompts.py` (new).
  - Seams: injectable input and output functions with builtins as defaults.
  - Anchor patterns: confirmation fallback in `runner/application/clean_slate.py`; protocol style in `runner/ports/command_runner.py`.
  - Verification: `pytest tests/unit/adapters/test_terminal_prompts.py`.

### Acceptance Criteria
- Parametrized input sequences cover `r`, `R`, `retry`, `r use sqlite`, `a`, `s` followed by `y`, `s` followed by `n` (re-prompt), and garbage-then-valid; the hint is captured verbatim (trimmed) or `None`.
- Menu prompt text uses the `[R]etry`, `[S]kip`, `[A]bort` vocabulary and echoes the diagnostics payload and attempt number.
- Question prompts render type and options and return the raw answer without interpreting it.
- Non-interactive fallback is covered by tests where stdin raises `OSError` or `EOFError`: menu returns `abort`, question raises.

### Gotchas
- Do not call `input()` outside the adapter; the processor depends only on the port.
- Follow the non-interactive terminal fallback gotcha instead of propagating raw stdin errors.
- Keep output ASCII-safe (Windows console encoding gotcha); no Rich dependency in this ticket.
