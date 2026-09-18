# T040 — Graceful SIGINT shutdown
Status: completed
Completed: 2026-09-18T04:18:30Z
Security: required
Spec: docs/specs/07-runner-exit-lifecycle.md
Blocked by: T039

### Requirements
- Make the first Ctrl+C a cooperative graceful shutdown: trap `KeyboardInterrupt` at the `asyncio.run` boundary in `ticket_runner.main` / `run_start` (ticket_runner.py), set the lifecycle stop event, request a kill on the active Worker supervisor, wait for the shutdown to drain, release the queue lock, and return exit code 130. A second Ctrl+C during shutdown force-kills (hard exit) and also returns 130.
- Fix the cancellation leak in `WorkerSupervisor.run` (runner/application/worker_supervisor.py): `asyncio.CancelledError` is a `BaseException`, so the existing `except Exception: await self._terminate_ladder(handle)` is bypassed on cancellation and the Worker subprocess leaks. Ensure the termination ladder (and thus the T039 job close) runs on cancellation — either by converting the interrupt into `supervisor.request_kill(...)` before cancellation, or by explicitly handling `CancelledError` in the supervisor so the ladder always executes. Never rely on the generic exception clause alone.
- Thread the stop signal so it works in both standby (stop event exits the watch loop in `QueueOrchestrator.run_lifecycle`) and mid-Worker (active supervisor run is killed). Use `loop.call_soon_threadsafe` where the interrupt handler runs on the main thread, since Windows does not support `asyncio` signal handlers for SIGINT.
- Ensure `run_lifecycle`'s `finally: self.release_lock()` still runs on the SIGINT path so the sentinel lock is never left held.

### Acceptance Criteria
- Ctrl+C during standby exits cleanly: watch loop stops, lock released, exit code 130, no traceback.
- Ctrl+C mid-Worker terminates the active Worker (fake `ProcessHandle` records termination; the T039 job reaps the tree) and exits 130.
- A second Ctrl+C during the graceful shutdown force-exits immediately, also with 130.
- The supervisor termination ladder provably runs on task cancellation (regression test for the `CancelledError` bypass).
- Full pytest suite is green.

### Gotchas
- `CancelledError` is a `BaseException` — verify the supervisor's ladder fires on cancellation with a regression test, not by inspection.
- The interrupt handler runs on the main thread outside the event loop; marshal state changes through `loop.call_soon_threadsafe`.
- The first interrupt must be idempotent: pressing Ctrl+C again during an already-draining shutdown force-exits instead of re-entering the graceful path.
- Subprocess termination on shutdown is a security-sensitive path: security review required before emitting the ready signal.
