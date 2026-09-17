# Spec 07: Runner Exit Lifecycle

## Problem Statement

After the Runner processes the final ticket in the queue, it either stays alive silently or exits ungracefully. With the default `standby` policy the process remains running and watching for new tickets, but an operator cannot tell whether it finished successfully, is watching for new work, or is wedged: the runner prints a single line and then nothing for hours. Pressing Ctrl+C kills the process ungracefully — `KeyboardInterrupt` propagates as a traceback, the active Worker subprocess leaks because cancellation bypasses the termination ladder, and opencode's detached server child is orphaned and keeps spinning at full CPU indefinitely. There is no stable contract distinguishing "clean finish" from "aborted" from "killed by operator", no record of what the run accomplished, and the interactive clean-slate archive prompt blocks the standby watch loop waiting for a human answer.

## Solution

Give the Runner a deliberate, legible exit lifecycle. When the queue drains it prints an unambiguous one-time banner — all tickets processed, standing by, press Ctrl+C to exit — and polls for new tickets at a configurable interval. Ctrl+C becomes a first-class graceful shutdown: the first press cooperatively stops the standby loop and the active Worker, reaps the Worker's full process tree (including opencode's detached server child) via a Windows Job Object, releases the queue lock, prints a compact completion summary, and exits with code 130; a second press force-kills. Exit codes 0 (clean), 1 (runtime error), 2 (abort), and 130 (graceful SIGINT) are codified and documented. Interactive clean-slate archival is deferred from queue-drain to actual exit so standby never blocks on a prompt.

## User Stories

1. As a developer, I want the Runner to print a clear one-time banner when all tickets are processed, so that I know it is done and watching for new tickets rather than stuck.
2. As a developer, I want the banner to tell me how to exit the watch loop (Ctrl+C), so that I am never left guessing how to stop the Runner.
3. As a developer, I want the standby watch poll interval to be configurable, so that I can trade responsiveness against CPU/disk chatter.
4. As a developer, I want to press Ctrl+C once to gracefully shut down the Runner, so that the active Worker is stopped, the queue lock is released, and I see a clean summary instead of a traceback.
5. As a developer, I want to press Ctrl+C a second time to force-kill the Runner immediately, so that a wedged shutdown is never a dead end.
6. As a developer, I want every spawned Worker process tree to be reaped when the Runner exits, so that no orphaned opencode server keeps spinning after a run.
7. As a developer, I want a documented exit-code contract (0 clean, 1 runtime error, 2 abort, 130 SIGINT), so that scripts and supervisors can distinguish outcomes reliably.
8. As a developer, I want a compact completion summary on graceful exit — tickets approved/skipped/aborted, commits authored, wall-clock duration, and branch — so that I can see what the run accomplished at a glance.
9. As a developer, I want the interactive clean-slate archive prompt to be deferred until the Runner actually exits, so that the standby watch loop never blocks on a question while I am away.
10. As a developer, I want the watch loop to announce when it detects a new pending ticket and resumes queue execution, so that standby resumption is visible.

## Implementation Decisions

- **Queue completion policies remain unchanged**: `standby` (default) keeps the process alive watching for new tickets; `terminate` prints a summary and exits with code 0.
- **New `lifecycle.poll_interval` configuration** (default 5 seconds): a validated positive float loaded from `config.yaml` and threaded through the CLI into the standby watch loop. The CLI's existing `poll_interval` override parameter remains but defaults from the config.
- **Standby banner**: a single, one-time line emitted on entering the watch loop — all tickets processed, watching for new tickets, press Ctrl+C to exit. No periodic heartbeat or status spam.
- **Graceful SIGINT shutdown**: Windows does not support `asyncio` signal handlers for SIGINT, so Ctrl+C is trapped at the `asyncio.run` boundary as `KeyboardInterrupt` and converted into a cooperative stop: set the lifecycle stop event (exits the standby loop), request a kill on the active Worker supervisor (stops stream reading and runs the termination ladder), release the queue lock, print the completion summary, and return exit code 130. A second Ctrl+C force-kills and also returns 130.
- **Cancellation-safe Worker termination**: the supervisor's termination ladder must run when its task is cancelled. `asyncio.CancelledError` is a `BaseException`, so the existing `except Exception` termination path is bypassed on cancellation — the ladder must run explicitly on cancellation (via `request_kill` before cancellation or an explicit `CancelledError` handler), never relying on the exception clause alone.
- **Windows Job Object reaping**: every spawned Worker subprocess is assigned to a Windows Job Object with `KILL_ON_JOB_CLOSE` so the entire process tree — including opencode's detached server child spawned inside the run — terminates when the Runner exits or the job is closed. The existing `taskkill /T /F` path remains as a secondary fallback. On non-Windows platforms this is a no-op preserving current behavior. No orphaned-server detection or warning is added.
- **Exit code contract**: `0` clean terminate, `1` runtime error, `2` operator abort, `130` graceful SIGINT (single or forced second press). Documented in the CLI `--help` and README.
- **Completion summary**: the lifecycle collects ticket outcomes (approved/skipped/aborted counts) and wall-clock duration; on graceful exit it prints a compact block including counts, the short commit SHAs authored, the working branch, and elapsed time.
- **Clean-slate deferral**: under `standby`, the interactive `[Y/n]` archive prompt is not invoked at queue drain; archival runs at actual exit (graceful SIGINT or `terminate`). The `always` and `never` policies behave unchanged. The `terminate` policy's prompt-at-drain behavior is preserved per ADR 0012.

## Testing Decisions

- **Test external behavior only**: assertions target return codes, printed banner/summary text, collected outcome counts, lock release, and fake-process termination flags — not internal wiring or call ordering.
- **Modules tested**: queue orchestrator lifecycle, CLI entry point and exit codes, worker supervisor termination (including cancellation), subprocess process-handle reaping, and lifecycle configuration loading/validation.
- **Primary seam**: `QueueOrchestrator.run_lifecycle` driven with an injected processor, `stop_event`, clock, and iteration cap — the same seam the existing orchestrator suite already uses. CLI-level tests cover the exit-code contract including `KeyboardInterrupt`. Supervisor tests use fake `ProcessHandle`s that record termination, mirroring the existing worker-supervisor suite. Config tests cover `poll_interval` validation.
- **Prior art**: the existing unit suites for the queue orchestrator, CLI, worker supervisor, and config loader/YAML loader.

## Out of Scope

- Spec 06 state persistence (`.agent/state.json`), crash recovery, the terminal dashboard, and the `[q]` hotkey.
- Orphaned opencode server detection or warning (declined during design).
- POSIX process-group reaping equivalent (the Job Object is Windows-specific).
- Changing the `standby`/`terminate` defaults or the existing abort exit code.

## Further Notes

- `opencode run` boots a local server inside the run process; a hard kill of the run CLI can leave that server detached and spinning (observed: an orphaned `opencode.exe` holding a bound port at ~30% CPU for an hour after the ticket completed). The Job Object is the structural fix for this class of leak.
- The design was stress-tested through a grilling session; every decision above reflects a settled answer.