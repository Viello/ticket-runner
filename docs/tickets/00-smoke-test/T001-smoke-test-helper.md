# T001 — Smoke test helper and passing unit test
Status: pending
Spec: docs/specs/00-smoke-test.md
Blocked by: None
Security: None
Reasoning: 

### Requirements
- Create `runner/smoke.py` with a simple status helper:
  ```python
  def get_smoke_status() -> dict[str, str]:
      return {"status": "ok", "model": "smoke"}
  ```
- Create `tests/unit/test_smoke.py` with a test exercising `get_smoke_status`:
  ```python
  from runner.smoke import get_smoke_status

  def test_get_smoke_status() -> None:
      assert get_smoke_status() == {"status": "ok", "model": "smoke"}
  ```
- Run tests via `python -m pytest tests/unit/test_smoke.py` to verify green status.
- Once passing, write the ready signal `.agent/signals/T001_ready.json` with payload:
  ```json
  {
    "ticket_id": "T001",
    "status": "ready",
    "modified_files": ["runner/smoke.py", "tests/unit/test_smoke.py"],
    "self_review_notes": "Implemented smoke helper and verified with unit test",
    "new_gotchas": [],
    "timestamp": "2026-09-19T06:00:00Z"
  }
  ```
- Do NOT author any git commits directly (the Gatekeeper alone authors commits upon passing verification).

### Acceptance Criteria
- `runner/smoke.py` exists and exports `get_smoke_status() -> dict[str, str]`.
- `tests/unit/test_smoke.py` exists and passes.
- Full test suite passes: `python -m pytest`.
- Durable signal file `.agent/signals/T001_ready.json` is created.
- Working tree contains no uncommitted files other than the new code and signal; no git commit authored by worker.

### Gotchas
- The worker must never commit to git directly (ADR 0002, ADR 0008, ADR 0012).
- Signal file must be written atomically to `.agent/signals/T001_ready.json` in UTF-8 encoding.
