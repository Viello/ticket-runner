# T002 — Circuit breaker verification drill
Status: pending
Spec: docs/specs/00-smoke-test.md
Blocked by: T001
Security: None
Reasoning: 

### Requirements
- Append an intentional failing test to `tests/unit/test_smoke.py`:
  ```python
  def test_intentional_failure_for_circuit_breaker() -> None:
      assert False, "Circuit breaker test intentional failure"
  ```
- Write the ready signal `.agent/signals/T002_ready.json` with payload:
  ```json
  {
    "ticket_id": "T002",
    "status": "ready"
  }
  ```
- Keep the intentional failure in place across any retry feedback attempts to allow the Gatekeeper to exhaust all 3 verification attempts and trip the circuit breaker.
- Do NOT author any git commits directly.

### Acceptance Criteria
- `tests/unit/test_smoke.py` contains `test_intentional_failure_for_circuit_breaker`.
- `.agent/signals/T002_ready.json` is emitted.
- Gatekeeper runs `python -m pytest`, catches the failing test, exhausts the 3-attempt budget, and successfully invokes the operator intervention menu (`[R]etry [hint] | [S]kip | [A]bort`).

### Gotchas
- The worker must not resolve the intentional failure: this ticket specifically exercises the Gatekeeper circuit breaker path.
- The worker must never commit to git directly.
