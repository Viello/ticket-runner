# T999 — Smoke ping helper and unit test verification
Status: completed
Completed: 2026-09-20T07:57:58Z
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: None
Reasoning: low

### Requirements
- Add a lightweight smoke helper function `smoke_ping() -> str` in `runner/smoke.py` that returns `"pong"`.
- Add a corresponding unit test `test_smoke_ping()` in `tests/unit/test_smoke.py` verifying that `smoke_ping()` returns `"pong"`.
- Jump-start:
  - Files to touch: `runner/smoke.py`, `tests/unit/test_smoke.py`.
  - Seams: None (pure standalone helper).
  - Anchor pattern: Existing `get_smoke_status()` in `runner/smoke.py` and `test_smoke_status()` in `tests/unit/test_smoke.py`.
  - Verification command: `python -m pytest tests/unit/test_smoke.py`.

### Acceptance Criteria
- `smoke_ping()` is defined in `runner/smoke.py` and returns `"pong"`.
- `tests/unit/test_smoke.py` contains `test_smoke_ping()` asserting `smoke_ping() == "pong"`.
- Verification command passes: `python -m pytest tests/unit/test_smoke.py`.
- Full project test suite remains green: `python -m pytest`.

### Gotchas
- Preserve the existing `get_smoke_status()` helper in `runner/smoke.py` and `test_smoke_status()` in `tests/unit/test_smoke.py`.
