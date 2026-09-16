# T035 — Spec 04 coverage audit
Status: pending
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T034

### Requirements
- Audit `tests/specs/test_spec_04_gatekeeper.py` against Spec 04 US1–US11: every user story has at least one behavioral assertion, and the story-to-test matrix is recorded in the module docstring.
- Fill coverage gaps with suite scenarios only; refresh any stale placeholder references if they survived earlier tickets.
- Confirm no behavioral test spawns live OpenCode or sleeps real 10-second or 300-second windows (injected clocks and fakes only) and keep the full suite runtime bounded.
- Jump-start:
  - Files to touch: `tests/specs/test_spec_04_gatekeeper.py`, `runner/application/queue_orchestrator.py` (message text only if still stale).
  - Seams: none new — suite level only.
  - Anchor patterns: T024's suite docstring and coverage-sweep acceptance criteria in `.agent/archive/03-worker-orchestration-and-handoff/completed/`.
  - Verification: full `pytest`.

### Acceptance Criteria
- Module docstring lists US1–US11 with the covering test names.
- Any genuinely missing story gets a focused scenario; no production edits are required.
- Full pytest suite is green and the spec suite runs without real-time sleeps.

### Gotchas
- This ticket is an audit and gap-fill. If a gap requires production behavior changes, stop and raise it as a gotcha instead of editing the Runner here.
