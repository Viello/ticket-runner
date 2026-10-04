# T004 — Plumb `AGENT_ANTIGRAVITY_BIN` and `AGENT_OPENCODE_BIN` Through Doctor
**Type:** wayfinder:task (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T001
Reasoning: medium

### Question

Wire the canonical env-var overrides (`AGENT_ANTIGRAVITY_BIN` and
`AGENT_OPENCODE_BIN`, per T001) through `Doctor._check_worker_binary` so users
with non-PATH `agy` or `opencode` installations can override the binary path. The
Doctor pre-flight at `runner/application/doctor.py:221-263` resolves the binary
by literal name only.

### Why this matters

Per T001's resolution, the env-var convention lets them override the binary path.
Without this ticket, the env-var name exists on paper but does nothing at
runtime.

### Requirements

- Extend `Doctor._check_worker_binary` to consult the env-var override first,
  then fall back to `shutil.which(binary)` (the current behavior).
- Resolution priority (T001-locked):
  1. Environment variable (`AGENT_ANTIGRAVITY_BIN` or `AGENT_OPENCODE_BIN`).
  2. `shutil.which(binary_name)` (default).
- If the env-var is set but the file does not exist or is not executable, the check
  must fail with a remediation message that explicitly names the env-var (e.g.
  `"AGENT_ANTIGRAVITY_BIN is set to '<path>' but that path does not exist or is not
  executable."`).
- Both env-vars plumbed symmetrically per T001's symmetry decision.
- Add unit tests in `tests/unit/application/test_doctor.py` covering (×2 providers,
  ×4 cases = 8 tests):
  - Env-var set, valid file → check passes.
  - Env-var set, invalid path → check fails with named-var remediation.
  - Env-var unset, binary on PATH → check passes (current behavior preserved).
  - Env-var unset, binary NOT on PATH → check fails with current remediation
    (regression guard).
- The `path_resolver` injection already in `Doctor` (per
  `docs/tickets/gotchas.md:189-190`) keeps tests deterministic.

### Acceptance Criteria

- `Doctor._check_worker_binary` consults the env-var override before
  `shutil.which` for both `opencode` and `antigravity` providers.
- All 8 unit tests pass in `tests/unit/application/test_doctor.py`.
- The existing tests still pass (no regression in default behavior).
- A gotcha entry is added to `docs/tickets/gotchas.md` summarizing the new resolution
  priority.

### Smoke Scenarios

**Scenario: Doctor pre-flight uses Antigravity env-var override**

- Setup: `$env:AGENT_ANTIGRAVITY_BIN='C:\Users\Acer\AppData\Local\agy\bin\agy.exe'`
  (the actual `where agy` location on this host). `$env:PATH` should NOT contain
  `agy` to prove the override is being used.
- Why: Verify the override actually bypasses `shutil.which` and resolves the binary
  directly.
- Steps:
  1. Run `python ticket_runner.py doctor` from the repo root.
  2. Confirm the doctor output shows Antigravity worker binary check passing.
  3. Unset the env-var and confirm the doctor fails with the missing-binary
     remediation.
- Expected: Step 2 passes; Step 3 fails with the existing
  `"Antigravity CLI binary 'agy' was not found in PATH"` message.

**Scenario: Doctor pre-flight uses OpenCode env-var override** — symmetric to
the Antigravity scenario, replacing `agy` with `opencode` and
`AGENT_ANTIGRAVITY_BIN` with `AGENT_OPENCODE_BIN`.

### Gotchas

- Do NOT remove the `shutil.which` fallback; the env-var is an override, not a
  replacement.
- The resolution priority must be documented in the docstring of
  `_check_worker_binary` (and reflected in the new gotcha entry).
- T004 should land BEFORE T018 (or alongside it) — once T018 rewrites the
  adapter, the Doctor check is more important than ever (the broken adapter
  would otherwise not be caught until smoke test fails).