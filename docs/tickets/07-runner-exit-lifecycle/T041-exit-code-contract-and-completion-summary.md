# T041 — Exit code contract and completion summary
Status: pending
Spec: docs/specs/07-runner-exit-lifecycle.md
Blocked by: T040

### Requirements
- Codify the exit-code contract: `0` clean terminate (queue drained under `terminate`, or standby exited via stop), `1` runtime error, `2` operator abort (`UserAbortError`), `130` graceful SIGINT (single or forced second press from T040). Document it in `ticket_runner.py` `--help` text and the README.
- Collect ticket outcomes across the whole lifecycle in `QueueOrchestrator.run_lifecycle` (runner/application/queue_orchestrator.py) — today `run_next` outcomes are discarded — tracking approved/skipped/aborted counts and the short commit SHAs authored, including across standby resume cycles.
- Track wall-clock duration (start at lifecycle entry, consistent with the injectable clock used by tests).
- On every graceful exit (terminate policy completion and graceful SIGINT), print a compact summary block: tickets processed (approved/skipped/aborted), commits authored, working branch, and elapsed time. Printed after the clean-slate handling (T042) and before returning.

### Acceptance Criteria
- `run_lifecycle` returns `0`/`1`/`2`/`130` on the documented paths; a CLI-level test asserts the actual process exit code (including `KeyboardInterrupt` → 130).
- The summary block on a graceful exit shows correct approved/skipped/aborted counts, the commit SHAs authored this run, the branch, and elapsed time.
- Outcome counts are correct when standby drains, resumes on a new ticket, and drains again.
- `--help` documents the exit-code contract.
- Full pytest suite is green.

### Gotchas
- `run_lifecycle` currently discards outcomes from `run_next`; collection must span the initial drain loop and every standby resume cycle.
- Use the injectable clock (already threaded through `run_lifecycle`/container) for duration so tests stay deterministic.
- The summary must print before the process returns so scripts that capture stdout see it; keep it on stdout, not stderr.