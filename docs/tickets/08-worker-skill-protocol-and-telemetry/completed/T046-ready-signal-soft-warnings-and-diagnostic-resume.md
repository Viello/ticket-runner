# T046 — Ready signal soft warnings and diagnostic retry resume
Status: completed
Completed: 2026-09-18T03:12:00Z
Spec: docs/specs/08-worker-skill-protocol-and-telemetry.md
Blocked by: T043, T045

### Requirements
- Update `runner/application/ticket_processor.py` to evaluate the accumulated `resources_accessed` set when handling a ready Signal (`.agent/signals/{ticket_id}_ready.json`).
- If `"code-review"` was not accessed, emit a warning notice via `_notify` and log at `WARNING` level:
  `"[{ticket.id}] Warning: Ready signal emitted without reading '.agents/skills/code-review/SKILL.md'. Proceeding to verification."`
- If `"AGENTS.md"` was not accessed, emit a warning notice via `_notify` and log at `WARNING` level:
  `"[{ticket.id}] Warning: Ready signal emitted without reading 'AGENTS.md'. Proceeding to verification."`
- If `ticket.security_required` is true and `"security-review"` was not accessed, emit a warning notice via `_notify` and log at `WARNING` level:
  `"[{ticket.id}] Warning: Ready signal emitted without reading required '.agents/skills/security-review/SKILL.md'. Proceeding to verification."`
- Maintain independent Gatekeeper verification as the sole acceptance barrier: soft warnings alert the operator in terminal and Discord without blocking, rejecting, or incrementing verification attempts.
- Format the Gatekeeper failure resume prompt on repeated verification failures (attempt $\ge 2$) to prepend an explicit instruction:
  `"Gatekeeper verification failed (attempt {attempt}). Before making further edits, read and follow '.agents/skills/diagnosing-bugs/SKILL.md' using your file reading tool to diagnose and isolate the root cause.\n\n"`
  On attempt 1 failure, emit error diagnostics directly without prepending the diagnostic skill instruction.
- Jump-start:
  - Files to touch: `runner/application/ticket_processor.py`, `tests/unit/application/test_ticket_processor.py`.
  - Seams: `TicketProcessor._process_ticket()`, failure resume prompt formatting.
  - Anchor patterns: Notification dispatch on circuit breaker trip; failure resume prompt in `ticket_processor.py`.
  - Verification: `python -m pytest tests/unit/application/test_ticket_processor.py`.

### Acceptance Criteria
- Missing `"code-review"`, `"AGENTS.md"`, or `"security-review"` (when required) triggers a clear warning message sent through `_notify` and the logger.
- When all required resources are present in `resources_accessed`, no soft warnings are emitted.
- Gatekeeper verification proceeds unconditionally regardless of soft warning triggers.
- Attempt 1 failure resume prompt contains trailing error output without the diagnostic skill directive.
- Attempt 2+ failure resume prompt prepends the `diagnosing-bugs` file-reading directive before error diagnostics.
- Full `test_ticket_processor.py` suite passes.

### Gotchas
- Soft warnings are non-blocking: never fail a verification attempt or trip the circuit breaker due to missing skill reads alone.
