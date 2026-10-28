# T018 — Rewrite Antigravity Adapter to Match Empirical CLI Surface
**Type:** wayfinder:task (HITL)
Status: completed
Completed: 2026-10-04T09:30:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T002
Reasoning: high

### Question

The Antigravity adapter at `runner/adapters/antigravity/antigravity_worker.py`
ships against an imagined `agy` CLI surface that does not exist on the real
binary. T002's empirical research (branch `research/agy-flag-surface`, commit
`0c30f9a`) revealed comprehensive drift. This ticket rewrites the adapter to
match reality.

### Why this matters

Per T002 findings, every call to the existing adapter fails with
`Error: unexpected argument "run"` and exit code `2`. The `worker.provider:
"antigravity"` setting in `config.yaml:11-13` (the repo's active default) is
broken. Users who flip the provider today get a non-functional pipeline.

This is not "hardening" — this is a fix.

### Requirements

Rewrite `runner/adapters/antigravity/antigravity_worker.py`:

1. **`build_antigravity_run_command` (lines 29-79)** — produce the correct argv:
   - Base: `["agy", "-p", prompt, "--output-format", "stream-json"]`
   - Reasoning depth: `--effort low|medium|high|xhigh|max` (NOT `--variant`)
   - Model: `--model <slug>` (NOT `-m`)
   - Session resume: `--continue` (most recent) or `--conversation <uuid>`
     (specific). Drop the `--session` flag entirely.
   - Always set `--print-timeout <duration>` (e.g. `5s`) on every command to
     prevent runaway runs (per T002's note on `0s` default).
2. **`_extract_token_usage` (lines 82-110)** — handle the empirical wire keys:
   - `input_tokens` → input
   - `output_tokens` → output
   - `thinking_tokens` → reasoning
   - `cache_read_tokens` → cache.read
   - `cache_write_tokens` → cache.write (if emitted)
   - `total_tokens` → total
   - Walk the envelope: look under `step_update.usage` and `result.usage`, never
     at the top level.
3. **`decode_event` (lines 113-172)** — handle the empirical envelope:
   - Closed set of `event` types: `{init, step_update, result}`.
   - Set `is_known` based on whether `event` is in the closed set (per the
     asymmetry noted in T002 vs OpenCode's allowlist at
     `runner/adapters/opencode/opencode_worker.py:16-24`).
   - Pull `conversation_id` as session id (already in the allowlist at line 154).
4. **`extract_resource_access` (lines 175-283)** — handle the empirical
   `step_update.tool_info.parameters.<arg>` shape:
   - Walk `step_update.tool_info.parameters` for skill/AGENTS.md paths.
   - Keep the raw-line fallback for non-structured output.
   - The current `part.tool_name` / `part.state.input` paths are dead code; remove
     them.
5. **Session id allowlist** — `agy` emits UUIDs as `conversation_id`, not the
   `ses_<alphanumeric>` shape the rest of the runner assumes
   (`runner/domain/runtime_paths.py:10` `SESSION_ID_PATTERN`). Decide and
   implement:
   - **Option A**: relax the `SESSION_ID_PATTERN` to accept either `ses_*` or a
     UUID. Keep backward compatibility.
   - **Option B**: translate `conversation_id` to a synthetic `ses_<hash>` id
     inside the adapter, leaving the allowlist untouched.
   - Document the choice in the gotcha entry.
6. **Update existing tests** at
   `tests/unit/adapters/test_antigravity_worker_adapter.py` (290 lines):
   - Replace all `agy run --auto` argv expectations with `agy -p <prompt>
     --output-format stream-json`.
   - Replace all `tokens`/`part.tokens`/`usage` mock structures with
     `step_update.usage` / `result.usage`.
   - Add coverage for the new `--effort`, `--model`, `--continue`/`--conversation`
     flag combinations.
   - Add coverage for the new event-type allowlist.
7. **Add a comment block at the top of the file** explaining the empirical surface
   and pointing at the T002 research note for the single source of truth.

### Acceptance Criteria

- `runner/adapters/antigravity/antigravity_worker.py` builds argv that agy accepts
  (no `run`, no `--auto`).
- Token extraction reads from `step_update.usage` / `result.usage` correctly.
- Event decoder handles the closed `{init, step_update, result}` set.
- Resource extraction walks `step_update.tool_info.parameters`.
- The full test suite passes:
  `pytest tests/unit tests/unit/adapters/test_antigravity_worker_adapter.py`.
- A live integration test against a real `agy` (T003) passes end-to-end.
- A gotcha entry is added to `docs/tickets/gotchas.md` summarizing the
  pre-T018 writeup (the broken state) and the post-T018 fix.

### Smoke Scenarios

**Scenario: Rewritten adapter spawns a real `agy` and parses its output**

- Setup: Real `agy` 1.2.16 installed on this host (confirmed at
  `C:\Users\Acer\AppData\Local\agy\bin\agy.exe`). No env-var override needed —
  `agy` is on PATH.
- Why: Verify the rewrite does not regress under real-world conditions.
- Steps:
  1. From `D:\Projects`, set `$env:worker__provider = "antigravity"` (or use the
     existing `config.yaml` provider).
  2. Run a minimal `WorkerSupervisor.run(prompt="Respond with: OK")` via the
     scaffold (`python -c "from runner.application.worker_supervisor import
     WorkerSupervisor; ..."`).
  3. Confirm the run completes with exit code 0 and at least one `step_update`
     event is decoded.
- Expected: Step 3 reports success; stdout shows JSONL envelope.

**Scenario: Session resume works via `--continue`**

- Setup: Two consecutive `WorkerSupervisor.run()` calls (the second resumes the
  first).
- Why: Verify `--continue` flag is plumbed correctly.
- Steps:
  1. First run with a fresh session; capture `conversation_id` from the JSONL.
  2. Second run with `session_id=<id>`; verify the adapter sends
     `--conversation <id>` (not `--session <id>`).
- Expected: Second run resumes; new events share the same `conversation_id`.

### Gotchas

- This is the largest ticket in Spec 15. Estimate: 4-8 hours of careful work.
- The session-id allowlist decision (Option A vs B) is a domain-modeling call —
  consider grilling on it before committing.
- The fix unblocks the entire `provider: "antigravity"` configuration, which is
  the repo's current default. This is a critical-path ticket; it must land
  before any Antigravity smoke tests (T003) or live-test executions.
