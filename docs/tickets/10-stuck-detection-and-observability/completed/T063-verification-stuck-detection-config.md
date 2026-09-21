# T063 — Verification stuck-detection config schema
Status: completed
Completed: 2026-09-21T04:16:00Z
Spec: docs/specs/10-stuck-detection-and-observability.md
Blocked by: None
Reasoning: low

### Requirements
- Add four new fields to the `verification:` section of the config schema, loader, and validator so downstream tickets have a settled API to work against:
  - `silence_window_seconds` (int, > 0, default 60) — kill the verification subprocess if no stdout/stderr arrives for this many seconds; raise on slow hardware.
  - `per_test_timeout_seconds` (int, >= 0, default 0; 0 = disabled) — when > 0, inject the runner-native per-test timeout flag.
  - `isolation_cmd` (str, default `""`) — optional template for single-test rerun (e.g. `pytest {test_id} -x`); empty means use heuristic.
  - `bug_escalation_at` (int, >= -1, default 1) — escalate diagnostic after this attempt number; -1 = only at circuit breaker; 0 = never.
- Update `config.example.yaml` with the new fields, inline comments explaining each, and a note distinguishing `silence_window_seconds` from the Worker's stall timeout.
- The config loader must apply the stated defaults when the fields are absent (backward-compatible with existing `config.yaml` files that lack them).
- Validation must reject `silence_window_seconds <= 0`, `per_test_timeout_seconds < 0`, and `bug_escalation_at < -1` with a clear error message.

Jump-start:
- Config loader: `runner/adapters/yaml_config_loader.py` — where other `verification:` fields (`max_attempts`, `timeout_seconds`) are parsed and validated.
- Config domain type: find the `VerificationConfig` (or equivalent) dataclass/typed-dict and add the four new fields with defaults.
- Test anchors: `tests/unit/adapters/test_yaml_config_loader.py` — copy the pattern used for `timeout_seconds` validation tests; add round-trip tests for each new field including default-when-absent.
- Verify with: `python -m pytest tests/unit/adapters/test_yaml_config_loader.py -x`

### Acceptance Criteria
- `config.example.yaml` contains all four new fields under `verification:` with accurate inline comments.
- Loading a `config.yaml` that omits all four new fields succeeds and populates the correct defaults.
- Loading a config with `silence_window_seconds: 0` raises a validation error naming the field.
- Loading a config with `per_test_timeout_seconds: -1` raises a validation error.
- Loading a config with `bug_escalation_at: -2` raises a validation error.
- All existing config loader tests still pass.
- `python -m pytest tests/unit/adapters/test_yaml_config_loader.py -x` exits 0.

### Smoke Scenarios
All scenarios are covered by automated tests. No manual steps required.

### Gotchas
- The silence window guards the *verification subprocess*, not the Worker. The Worker's stall timeout (`WorkerSupervisor`) is a separate concept; the config comment must make this distinction explicit to prevent future confusion.
- Default values must be applied at load time, not at use time, so the domain type is always fully populated and callers never need null-checks.
