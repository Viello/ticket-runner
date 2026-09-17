# T039 — Windows Job Object subprocess reaping
Status: pending
Security: required
Spec: docs/specs/07-runner-exit-lifecycle.md
Blocked by: none

### Requirements
- Assign every subprocess spawned by `SubprocessRunner.spawn` (runner/adapters/cli/subprocess_runner.py) — the Worker opencode CLI above all — to a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, so the entire process tree, including opencode's detached server child spawned inside the run, terminates when the job is closed. This fixes the confirmed orphan class where a hard kill of the run CLI leaves a detached `opencode.exe` spinning (observed: PID 17064, ~30% CPU for an hour after its ticket completed).
- Assign the process to the job immediately after spawn, before it can spawn children. Keep the Job Object handle alive for the lifetime of the `SubprocessProcessHandle` so it is never garbage-collected early.
- The job must close on every handle lifecycle end: normal completion, the existing termination ladder, and task cancellation — so no exit path leaks the tree.
- On non-Windows platforms this is a no-op; existing behavior is preserved.
- Keep the existing `taskkill /PID <pid> /T /F` path in `SubprocessProcessHandle.terminate` as a secondary fallback; the Job Object is the primary reaping guarantee.
- Wire the mechanism so `WorkerSupervisor` (runner/application/worker_supervisor.py) reaps via the job on `KILLED_SIGNAL`, `STALLED`, and cancellation paths without changing its public API.

### Acceptance Criteria
- A spawned Worker whose child detaches from the parent process tree is reaped when the owning job closes (demonstrated with a test double that spawns a detached grandchild, plus a manual integration check that no `opencode.exe` server outlives a `KILLED_SIGNAL` termination).
- A simulated cancellation of the supervisor run closes the job and reaps the tree.
- Non-Windows code path is unchanged and the full pytest suite is green.
- The existing `taskkill /T` fallback still fires when the job path is unavailable.

### Gotchas
- Python's `asyncio.create_subprocess_exec` on Windows inherits the parent's job by default; avoid `CREATE_BREAKAWAY_FROM_JOB` so children stay inside the job.
- Race: assign the process to the job immediately after spawn — a child spawned before assignment escapes the job.
- The Job Object handle must be held by the process-handle object (not a local variable) or the OS may reap the tree mid-run.
- This ticket touches a subprocess boundary: security review required before emitting the ready signal.