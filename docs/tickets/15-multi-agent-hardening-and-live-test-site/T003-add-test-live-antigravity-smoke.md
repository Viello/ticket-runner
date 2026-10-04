# T003 — Add `test_live_antigravity_smoke.py`
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T002, T018
Reasoning: medium

### Question

Mirror `tests/unit/adapters/test_live_opencode_smoke.py` for Antigravity: a
gated-on-`TICKET_RUNNER_LIVE=1` smoke test that invokes a real `agy` binary and
asserts the JSONL envelope shape. This closes the gap noted at
`docs/tickets/gotchas.md:180-183` — Antigravity currently has no live integration
test.

### Why this matters

`tests/unit/adapters/test_live_opencode_smoke.py` validates that OpenCode's stdout
is parseable JSON containing `sessionID`. Antigravity has no equivalent. If the
`agy` CLI changes its output format, the unit tests at
`tests/unit/adapters/test_antigravity_worker_adapter.py` will keep passing (they
mock the stream) but the real integration breaks silently.

**Updated per T002 research**: the empirical envelope is keyed by `event`
(`init`, `step_update`, `result`), and the session id is `conversation_id`. The
test should assert these specifically.

### Requirements

- Create `tests/unit/adapters/test_live_antigravity_smoke.py` mirroring the
  structure of `tests/unit/adapters/test_live_opencode_smoke.py`.
- Gate the test on `TICKET_RUNNER_LIVE=1` (skip otherwise — do not require `agy` to
  be installed for the default CI run).
- The test must:
  1. Resolve `agy` via the same `path_resolver` / `which_fn` injection used by
     `Doctor._check_worker_binary` (so T004's env-var override naturally flows
     through).
  2. Spawn **`agy -p "Respond with: OK" --output-format stream-json
     --print-timeout 5s`** via `SubprocessRunner`. (NOT `agy run --auto` — T002
     revealed that argv fails with exit code 2.)
  3. Read stdout line-by-line and assert each line parses as JSON.
  4. Verify a `conversation_id` field appears at least once across the stream.
  5. Verify that at least one event has the top-level `event` field set to one of
     the closed set `{init, step_update, result}`.
- Add a brief comment block at the top of the test explaining how to run it:
  `$env:TICKET_RUNNER_LIVE=1; pytest tests/unit/adapters/test_live_antigravity_smoke.py`.
- **Dependence on T018**: this ticket should be implemented AFTER T018 lands the
  rewritten adapter, so the test can exercise the corrected argv structure.

### Acceptance Criteria

- `tests/unit/adapters/test_live_antigravity_smoke.py` exists, mirrors the OpenCode
  smoke test's structure, and is skipped (not failed) when
  `TICKET_RUNNER_LIVE != 1`.
- With `TICKET_RUNNER_LIVE=1`, a real `agy` installed, and the T018-rewritten
  adapter in place, the test passes.
- Without `agy` installed, the test skips gracefully with a clear message.
- A new test case in `tests/specs/test_spec_15_multi_agent_and_live_test.py` (created
  alongside this work) verifies the test file exists, has the gating decorator, and
  matches the OpenCode smoke test's structural conventions.

### Smoke Scenarios

**Scenario: Live Antigravity smoke test executes against real `agy` (post-T018)**

- Setup: Requires `agy` installed, T018's rewritten adapter in place, and the
  `$env:TICKET_RUNNER_LIVE=1` environment variable set.
- Why: Verify the integration does not silently regress when `agy` updates.
- Steps:
  1. Run
     `pytest tests/unit/adapters/test_live_antigravity_smoke.py -v` with
     `$env:TICKET_RUNNER_LIVE=1`.
  2. Confirm test passes (return code 0).
  3. Run with `$env:TICKET_RUNNER_LIVE=0` (or unset) and confirm the test is skipped
     (not failed).
- Expected: Step 2 returns 0 with one test passing; Step 3 reports one test skipped.

### Gotchas

- The test must NOT mutate any state on disk outside its `tmp_path` (per the runner's
  isolation discipline).
- The smoke test should NOT call `--continue` or `--conversation` (unlike the unit
  adapter tests, which test session resume); fresh-session smoke only.
- The `agy` JSONL envelope is **fundamentally different** from OpenCode's
  (`event: {init, step_update, result}` vs OpenCode's flat type allowlist). The
  test must assert the agy-specific envelope.