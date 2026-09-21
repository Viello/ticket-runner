# T064 — Silence window in verification command runner
Status: pending

### Requirements
- Extend the verification command runner's subprocess streaming loop with a silence timer: if no stdout/stderr line arrives within `verification.silence_window_seconds` seconds, terminate the process tree and surface `termination_reason = HANG` in the result.
- Termination must use the existing process-tree kill pattern (`taskkill /T /F` on Windows, `proc.terminate()` on POSIX) — the same pattern as `SubprocessProcessHandle` in the Worker supervisor.
- When `per_test_timeout_seconds > 0`, detect the test framework from `test_cmd` keywords and prepend the appropriate native timeout flag to the command before spawning:
  - `pytest` → `--timeout=N`
  - `jest` / `vitest` → `--testTimeout=N000` (milliseconds)
  - `go test` → `-timeout Ns`
  - `cargo test`, `dotnet test`, unknown → no flag injected; silence window is the sole guard.
- Normal completion (process exits before the silence window fires) must not be affected.
- The silence window timer resets on each received line, not just on process start.

Jump-start:
- Verification command runner: find the module under `runner/adapters/` or `runner/application/` that calls the test subprocess (look for `test_cmd`, `build_cmd`, `timeout_seconds` usage — likely near `VerificationLoop`).
- Silence detection pattern: read `runner/application/worker_supervisor.py` (or equivalent) — the Worker's stall detection uses `asyncio.wait(..., timeout=stall_timeout)` in a loop; replicate that structure here.
- Process kill: `runner/adapters/subprocess_process_handle.py` — reuse `_terminate_process_tree()` or equivalent.
- Tests: extend `FakeProcessHandle` (or equivalent fake in `tests/`) to support yielding lines with injected clock gaps; assert kill + HANG reason.
- Verify with: `python -m pytest tests/ -x -k "silence or hang or verification"`

### Acceptance Criteria
- A fake subprocess that emits one line then goes silent for > `silence_window_seconds` is killed; the returned result carries `termination_reason == HANG` (or equivalent label).
- A fake subprocess that completes normally in < `silence_window_seconds` returns exit code 0 with no kill.
- When `per_test_timeout_seconds > 0` and `test_cmd` contains `pytest`, the spawned command includes `--timeout=N`.
- When `test_cmd` contains `cargo test` (no native flag supported), no extra flag is injected regardless of `per_test_timeout_seconds`.
- `python -m pytest tests/ -x` exits 0.

### Smoke Scenarios
All scenarios are covered by automated tests. No manual steps required.

### Gotchas
- The silence timer must reset on each received line — not just on process start — otherwise a slow-but-alive suite that emits one line every 45 seconds would be killed by a 60-second window. Only a genuine *gap* between lines triggers the kill.
- The per-test timeout flag must be injected before the command is passed to `shutil.which` resolution; verify the flag does not appear as the first positional argument where it would shadow the executable name.
