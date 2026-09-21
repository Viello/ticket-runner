# T066 — Structured diagnostic report and escalation prompt
Status: pending
Spec: docs/specs/10-stuck-detection-and-observability.md
Blocked by: T065
Reasoning: medium

### Requirements
- After each failed verification attempt, call the failure analyser (T065) to build a `FailureDiagnostic`, then check escalation policy (`bug_escalation_at` from config) to decide whether to surface it.
- Escalation rules:
  - `bug_escalation_at == 0` → never escalate; proceed silently to next attempt.
  - `bug_escalation_at == -1` → escalate only when the circuit breaker is about to trip (last attempt exhausted).
  - `bug_escalation_at >= 1` → escalate when `current_attempt >= bug_escalation_at` (and always when circuit breaker trips regardless of this value).
- When escalating, render a structured diagnostic report:
  ```
  ⚠ <LABEL> detected — <root_test or "unknown">
  Top errors: <top_errors joined by ", ">
  <isolation_output if present, else omitted>
  --- last 100 lines ---
  <log_tail>
  Token budget: <token_count> / <token_budget>
  Suggested: <suggested_action>
  Run /diagnosing-bugs? [Y/n]
  ```
- Send the report simultaneously to:
  - Terminal via `InterventionGateway` (existing prompt mechanism).
  - Discord channel (call the Discord adapter's send method; if not yet implemented, call a no-op stub and log a warning — never raise).
- If the operator answers Y (or presses Enter), yield `INTERVENTION_REQUESTED` with the `FailureDiagnostic` attached so the caller can hand off to the `/diagnosing-bugs` workflow.
- If the operator answers N, or the environment is non-interactive (`NonInteractiveError` / `EOFError`), log the diagnostic to `.agent/logs/<ticket_id>_diagnostic.md` and resume the next attempt.
- The escalation logic lives in or is called from `VerificationLoop`; do not embed it in the command runner.

Jump-start:
- `VerificationLoop` (or equivalent orchestration class in `runner/application/`) is where `max_attempts` and circuit breaker logic live — this is where to hook escalation.
- `InterventionGateway` (port): find the interface and its terminal adapter; look for how clarification questions are currently surfaced to the operator (the Question Signal flow uses it).
- Discord: find the Discord adapter stub (likely in `runner/adapters/discord/`); if absent, create a no-op `DiscordAdapter.send(message: str)` stub.
- Diagnostic log: write to `.agent/logs/{ticket_id}_diagnostic.md` using `atomic_write_text`.
- Tests: `tests/unit/application/test_verification_loop.py` — inject a fake `FailureDiagnostic` producer and mock `InterventionGateway`; assert escalation fires at the right attempt and is suppressed correctly.
- Verify with: `python -m pytest tests/unit/application/ -x`

### Acceptance Criteria
- With `bug_escalation_at: 1`, a first-attempt failure produces a rendered diagnostic report and the Y/N prompt.
- With `bug_escalation_at: -1`, failures on attempts 1 and 2 (of 3) produce no prompt; attempt 3 (circuit breaker) produces the prompt.
- With `bug_escalation_at: 0`, no prompt is ever shown regardless of attempt count.
- Answering Y yields `INTERVENTION_REQUESTED` with `FailureDiagnostic` attached.
- Answering N (or non-interactive EOF) writes the diagnostic to `.agent/logs/{ticket_id}_diagnostic.md` and the loop continues.
- Discord send is called when escalating; a missing/stub Discord adapter does not raise.
- `python -m pytest tests/unit/application/ -x` exits 0.

### Smoke Scenarios
**Scenario: operator sees and answers the escalation prompt**
- Setup: Set `bug_escalation_at: 1` in `config.yaml`. Point `test_cmd` at a test file that always fails (e.g. `assert False`). Run the Runner against a pending ticket that targets this failing suite.
- Steps:
  1. Observe that on the first failed verification attempt the terminal displays the diagnostic report block (label, top errors, last 100 log lines, suggested action, `Run /diagnosing-bugs? [Y/n]`).
  2. Type `Y` and press Enter.
- Expected: The Runner yields `INTERVENTION_REQUESTED` and pauses the verification loop — the attempt counter does not increment; the terminal indicates it is waiting for human intervention.

**Scenario: operator dismisses the escalation prompt**
- Setup: Same as above (`bug_escalation_at: 1`, always-failing test).
- Steps:
  1. Wait for the `Run /diagnosing-bugs? [Y/n]` prompt to appear.
  2. Type `N` and press Enter.
- Expected: The diagnostic is written to `.agent/logs/<ticket_id>_diagnostic.md` (open and confirm the file contains the label, errors, and log tail). The verification loop resumes and attempts the next retry.

**Scenario: circuit-breaker always escalates regardless of `bug_escalation_at`**
- Setup: Set `bug_escalation_at: 0` (never escalate) and `max_attempts: 2`. Point `test_cmd` at an always-failing test.
- Steps:
  1. Let both verification attempts fail without interacting.
  2. On the second failure (circuit breaker trips), observe whether the prompt appears.
- Expected: The escalation prompt appears despite `bug_escalation_at: 0`, because the circuit breaker always escalates.

### Gotchas
- The diagnostic render must bound the log tail to 100 lines before inserting into the report; never embed unbounded output in a Discord message or terminal prompt (it will exceed Discord's 2000-character limit and the Windows command-line ceiling).
- `INTERVENTION_REQUESTED` interrupts the verification loop without consuming a retry attempt — the circuit breaker counter must not increment when the operator steps in.
- Discord send is fire-and-forget for now; do not await a reply from Discord in this ticket (that is Discord-adapter work in Spec 05).
