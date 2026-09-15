# T012 — Queue completion lifecycle and CLI start wiring
Status: pending
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Detect queue exhaustion in `QueueOrchestrator` (no pending tickets in the active spec directory) and emit a completion notice, then apply `lifecycle.queue_completion` from `RunnerConfig` (user story 11):
  - `standby`: remain running in an idle watch loop, polling `docs/tickets/` for newly added pending tickets on an injectable interval (default 5 seconds) and resuming automatically when found.
  - `terminate`: print a completion summary and return exit code 0.
- Wire the `start` subcommand in `ticket_runner.py`: load and validate `config.yaml` via `YamlConfigLoader`, run Doctor pre-flight checks first (honoring `--local-only` and `--config`), then drive the queue lifecycle through `asyncio.run`.
- Until Spec 03 supplies the Worker processor, `start` with pending tickets must fail fast with a clear message that Worker execution arrives in Spec 03, exiting non-zero without modifying the workspace; `start` with an empty queue exercises standby/terminate cleanly.
- Keep `pause` and `status` as explicit not-yet-implemented placeholders (Spec 06 owns them).
- Jump-start:
  - Files to touch: `ticket_runner.py`, `runner/application/queue_orchestrator.py`, `tests/unit/application/test_queue_orchestrator.py`, `tests/specs/test_spec_02_queue.py`, `tests/unit/test_cli.py` (new, if absent).
  - Seams: `ticket_runner.py:main` dispatch; `QueueOrchestrator.run_lifecycle(...)` with injected polling interval and processor.
  - Anchor patterns: `run_doctor` CLI pattern in `ticket_runner.py`; lifecycle policy fields in `runner/domain/config.py:LifecycleConfig`; ASCII-safe console fallback in `ticket_runner.py:_configure_console_encoding`.
  - Verification: `pytest tests/unit/application/test_queue_orchestrator.py tests/unit/test_cli.py tests/specs/test_spec_02_queue.py` plus a manual `python ticket_runner.py start` smoke run against an empty queue.

### Acceptance Criteria
- `standby` polls at the injected interval and resumes the queue when a new pending ticket appears; the loop is cancellable for tests.
- `terminate` prints a summary and exits 0 when the queue drains.
- `ticket_runner.py start` runs Doctor first, threads `--config`/`--local-only`, and returns non-zero when Doctor fails.
- With pending tickets and no processor configured, `start` reports the Spec 03 dependency clearly and leaves the repository untouched.
- CLI and lifecycle behavior are covered by tests using fakes and temporary trees; the manual smoke run against an empty queue confirms the flow.

### Gotchas
- Doctor treats zero pending tickets as a failure (Spec 01); standby applies to a Runner whose queue drains during a run, so do not weaken or bypass Doctor for the empty-start case — document the boundary.
- The 5-second poll interval must be injectable so tests do not sleep for real; ensure the standby loop yields to the event loop between polls.
- Use the existing ASCII-safe console path and avoid Unicode that `cp1252` cannot encode (Spec 01 gotcha).
- `start` must not create state files, lock files, or commits while no processor is wired.
