# T031 — Verification loop and Circuit Breaker
Status: pending
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T025, T027, T028, T029, T030

### Requirements
- Add the verification loop as an application use case with an in-memory, per-Ticket budget of `verification.max_attempts` Verification Attempts. One attempt is one Worker session run, Signal validation, and Gatekeeper verification; any failure ends the cycle early, consumes one attempt, and feeds diagnostics back into the active Worker session as the next resume prompt.
- Diagnostics by failure kind: malformed ready Signal gives the `SignalFormatError` message; worker-phase non-READY statuses (stalled, ceiling, escalated, crash) give the escalation details already produced by spec 03; failed verification gives `VerificationReport.diagnostics`.
- Budget exhaustion opens the intervention menu through `InterventionGateway.request_intervention`: `retry` resets to a full fresh budget and injects the optional hint; `skip` returns a skip result carrying the last diagnostics; `abort` raises a new `UserAbortError`.
- A pending question interrupts, it does not fail: return control for the question with the session id and zero budget consumed; re-entry later resumes with the same budget.
- Add `TicketOutcomeStatus.ABORTED` to the orchestrator outcome enum and `UserAbortError` to the domain exception hierarchy.
- Keep the ready Signal single-use: consume it before any diagnostics resume.
- Jump-start:
  - Files to touch: `runner/application/gatekeeper.py`, `runner/domain/exceptions.py`, `runner/application/queue_orchestrator.py`, `tests/unit/application/test_gatekeeper_loop.py` (new), `tests/specs/test_spec_04_gatekeeper.py` (append).
  - Seams: injected cycle runner, `SignalRepository`, the T028 executor, `InterventionGateway`; one loop instance per Ticket so the budget survives question interleaves and retries.
  - Anchor patterns: status enums in `runner/application/handoff_coordinator.py`; the `TicketOutcome` contract in `runner/application/queue_orchestrator.py`; fake-driven application tests.
  - Verification: `pytest tests/unit/application/test_gatekeeper_loop.py tests/specs/test_spec_04_gatekeeper.py`.

### Acceptance Criteria
- Behavioral: a failing verification resumes with diagnostics containing the tail and passes on the next cycle; a malformed Signal consumes an attempt with the format error as diagnostics; a worker-phase non-READY consumes an attempt with escalation details; budget exhaustion opens the menu.
- `retry` with a hint restores the full budget (the menu reopens only after another full budget) and the hint appears in the resume prompt; `skip` returns a skip result with diagnostics; `abort` raises `UserAbortError`.
- `QUESTION_PENDING` returns with the session id and zero budget consumed; re-entry continues with the same budget.
- `max_attempts=1` trips after the first failure; the counter is never persisted (in-memory only) and never goes negative.
- No working-tree reset, Ticket relocation, or commit logic lives in this component.

### Gotchas
- The orchestrator owns skip resets and commit ordering — do not duplicate them here.
- Bound the diagnostics embedded in resume prompts so a huge tail cannot blow the context budget.
- Never reuse a consumed Signal; every cycle must validate a fresh file.
- Question interleaves must not reset the budget — keep loop state per Ticket, not per call.
