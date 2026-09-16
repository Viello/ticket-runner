# T020 — Worker supervisor B: stall watchdog, termination ladder, bounded runs
Status: completed
Completed: 2026-09-16T13:29:00Z
Security: required
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add to `WorkerSupervisor` a no-event stall watchdog: if no stdout line arrives for `STALL_SILENCE_SECONDS = 900`, terminate the run and return reason `STALLED`. Implement it as a bounded wait around stream consumption (e.g. `asyncio.wait_for` on the next line), not a detached sleeper thread.
- Add a total wall-clock cap `BOUNDED_RUN_TIMEOUT_SECONDS = 300` that applies only to runs explicitly marked bounded (handoff instruction, nudge, resume-retry); normal work runs are uncapped except by the token ceiling and watchdog. Both constants live at module scope.
- Implement the termination ladder used by the watchdog and by `request_kill(reason)`: first a graceful `terminate()`, then tree-kill via the T016 port's `taskkill /PID <pid> /T /F` path, then a bounded wait for the process to actually disappear.
- Add `request_kill(reason)` as the external interrupt API: T021 calls it with `KILLED_HANDOFF` at 135k or `KILLED_CEILING` at 150k while a stream is being consumed; the supervisor stops reading, runs the termination ladder, and returns promptly with that reason.
- Finalize the result type: `SessionRunResult(reason, session_id, exit_code, occupancy, ready_signal_present, stderr_tail, jsonl_path, stderr_path)` with `reason in {EXITED, KILLED_HANDOFF, KILLED_CEILING, STALLED, DROPPED}` (`DROPPED` = exited/crashed without a usable session id).
- Security: required — forced process termination and caps. Explicitly verify: kill targets only the spawned PID tree; no process survives `run()` return; `request_kill` cannot be spoofed by stream content (it is an in-process API); watchdog cannot fire on a live stream.
- Jump-start:
  - Files to touch: `runner/application/worker_supervisor.py`, `tests/unit/application/test_worker_supervisor.py`.
  - Seams: T019 stream consumption loop; T016 handle `terminate()`/`wait()`.
  - Anchor patterns: deterministic async tests in `tests/unit/application/test_queue_orchestrator.py`; inject clocks/timeouts as constructor parameters so tests never sleep real minutes.
  - Verification: `pytest tests/unit/application/test_worker_supervisor.py`.

### Acceptance Criteria
- A fake stream that goes silent beyond 900s (injected clock) returns `STALLED` and the fake process records termination.
- Calling `request_kill(KILLED_HANDOFF)` mid-stream returns promptly with that reason and with all lines consumed so far written to the session log.
- A bounded run exceeding 300s wall-clock (injected) is killed; an unbounded run under the same script is not.
- A child that floods stderr while stdout is slow returns `EXITED` without deadlock; exit codes propagate unchanged.

### Gotchas
- Windows `TerminateProcess` does not reap grandchildren (Opencode may spawn bash/LSP children) — prefer the taskkill tree path and verify no orphan remains in tests via recorded fake invocations.
- Keep the watchdog and cap injectable/adjustable in tests; T024 must not wait real 900s/300s.
- Do not conflate `WARN` notices with kill logic: WARN never terminates a run.
