# T042 — Defer interactive clean-slate prompt until exit
Status: pending
Spec: docs/specs/07-runner-exit-lifecycle.md
Blocked by: T040

### Requirements
- In `QueueOrchestrator.run_lifecycle` (runner/application/queue_orchestrator.py), under `queue_completion="standby"`, do not invoke the interactive clean-slate archive prompt (`clean_slate: interactive` → `[Y/n]`) at queue drain — the runner must settle into the standby watch loop (T038 banner) without blocking on a human answer.
- Defer the interactive archival until the Runner actually exits: on graceful SIGINT (T040) and under the `terminate` policy. `always` and `never` policies keep their current drain-time behavior (archive automatically / skip). The `terminate` policy's prompt-at-drain behavior is preserved per ADR 0012.
- When deferred and fired at exit, run the archival before the T041 completion summary prints, with the sentinel lock already released (existing Windows sharing-violation gotcha).

### Acceptance Criteria
- With `queue_completion="standby"` and `clean_slate="interactive"`, a drained queue prints the standby banner and never blocks on a `[Y/n]` prompt; the watch loop keeps polling.
- On graceful exit (SIGINT or terminate), the interactive prompt fires (or archival runs for `always`), then the completion summary prints.
- `clean_slate="always"` archives at drain in both policies; `"never"` skips entirely.
- The `terminate` policy behavior is unchanged from current (ADR 0012).
- Full pytest suite is green.

### Gotchas
- The standby watch loop must stay non-blocking, so no prompt may fire between drain and exit.
- The deferred prompt/archival must run with the sentinel lock released so an interactive answer cannot hold the Windows file lock.
- Standby resume cycles that drain again must not re-trigger the prompt mid-watch; only the final exit fires it.