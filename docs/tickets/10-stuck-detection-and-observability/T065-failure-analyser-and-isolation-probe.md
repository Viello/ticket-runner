# T065 — Failure analyser and isolation probe
Status: pending

### Requirements
- Implement a pure domain function `analyse(output_lines, exit_code, termination_reason, config) → FailureDiagnostic` with no subprocess dependencies. It must:
  - Classify the failure as `HANG`, `CASCADE`, `ENV`, or `FLAKY` using the heuristics described in Spec 10 § Implementation Decisions.
  - Extract up to 3 unique error-class fingerprints (exception class names, "FAILED", "ERROR", "ImportError", etc.) from the full output.
  - Identify the first failing test identifier (file path + test name) from the output.
  - Build an isolation rerun command using the heuristic or the `isolation_cmd` config template, then run the isolation probe as a subprocess and capture its output.
  - Return a `FailureDiagnostic` value object: `label`, `root_tests`, `top_errors`, `log_tail` (last 100 lines), `isolation_output`, `suggested_action`.
- Classification heuristics (evaluated in order):
  1. `HANG` — `termination_reason` is `HANG` / `STALLED`.
  2. `ENV` — output contains "ModuleNotFoundError", "ImportError", "command not found", "No module named", or similar setup errors appearing before the first test identifier line.
  3. `CASCADE` — five or more `FAILED` / `ERROR` entries with a single repeating error class.
  4. `FLAKY` — fallback (exit != 0, no clear pattern).
- Isolation command heuristic (when `isolation_cmd` is empty):
  - `pytest` → `pytest {test_id} -x`
  - `jest` / `vitest` → `npx {runner} --testNamePattern "{test_name}"`
  - `go test` → `go test -run {test_name} ./...`
  - `cargo test` → `cargo test {test_name}`
  - Unknown → skip isolation, `isolation_output = None`.
- The isolation probe subprocess must respect `timeout_seconds` from config; do not let it run indefinitely.

Jump-start:
- Create as a new domain module — `runner/domain/failure_analyser.py` (or similar). Pure functions, no I/O imports beyond subprocess for the isolation rerun.
- `FailureDiagnostic` is a dataclass or `NamedTuple` defined in the same file or in `runner/domain/`.
- Tests: `tests/unit/domain/test_failure_analyser.py`. Use string literals as fixture output — no real processes needed for the classification tests. For isolation probe tests, use the existing `FakeProcessHandle` or a simple subprocess mock.
- Verify with: `python -m pytest tests/unit/domain/test_failure_analyser.py -x`

### Acceptance Criteria
- `analyse()` given a HANG termination reason returns `label == "HANG"` regardless of output content.
- `analyse()` given pytest output with `ModuleNotFoundError` on the first line returns `label == "ENV"`.
- `analyse()` given pytest output with 10 `FAILED` entries sharing `AssertionError` returns `label == "CASCADE"` and `top_errors[0] == "AssertionError"`.
- `analyse()` given a non-zero exit with no recognisable pattern returns `label == "FLAKY"`.
- The isolation command builder returns the correct template string for each known runner without executing anything.
- `log_tail` contains at most 100 lines.
- `python -m pytest tests/unit/domain/test_failure_analyser.py -x` exits 0.

### Smoke Scenarios
All scenarios are covered by automated tests. No manual steps required.

### Gotchas
- Classification must be evaluated in strict priority order (HANG → ENV → CASCADE → FLAKY). An ENV error appearing in a suite that also has many FAILED lines must still classify as ENV, because fixing the environment will likely resolve the cascade too.
- Test identifier extraction patterns differ by runner: pytest uses `test_file.py::test_fn`, jest uses `describe > test name`, go test uses `--- FAIL: TestFoo`. The heuristic must parse the first occurrence, not the last. If none is found, `root_tests` is an empty list — not an error.
- The isolation probe must not inherit the full original command (e.g. `python -m pytest`) verbatim; it needs the single-test form. Validate that `{test_id}` substitution resolves before spawning.
