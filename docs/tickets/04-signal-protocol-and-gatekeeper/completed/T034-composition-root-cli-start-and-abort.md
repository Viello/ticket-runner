# T034 — Composition root, CLI start, and abort handling
Status: completed
Completed: 2026-09-17T08:55:00Z
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T033

### Requirements
- Add a Composition Root wiring the real adapters into the processor and orchestrator, with keyword-only optional overrides (command runner, intervention gateway, stores, git operations, runtime paths) so behavioral tests can build the full pipeline in one call.
- Wire `ticket_runner.py start` through the container, replacing the missing-processor path and the "arrives in Spec 04" error while keeping Doctor pre-flight, branch checks, and the lifecycle loop.
- Handle abort: the orchestrator catches `UserAbortError`, records `ABORTED`, performs no finalize and no working-tree reset, releases the queue lock, stops the lifecycle (including standby), and the CLI exits with code 2.
- Jump-start:
  - Files to touch: `runner/container.py` (new), `ticket_runner.py`, `runner/application/queue_orchestrator.py`, `tests/unit/test_cli.py`, `tests/unit/application/test_queue_orchestrator.py`, `tests/specs/test_spec_04_gatekeeper.py` (append).
  - Seams: `build_container(config, *, overrides...)`; `QueueOrchestrator(processor=...)`; lifecycle lock release in `finally`.
  - Anchor patterns: existing `run_start` wiring in `ticket_runner.py`; fake-orchestrator injection in `tests/unit/test_cli.py`.
  - Verification: `pytest tests/unit/test_cli.py tests/unit/application/test_queue_orchestrator.py tests/specs/test_spec_04_gatekeeper.py`.

### Acceptance Criteria
- `build_container` returns the wired pipeline used by `start`; with overrides injected, the behavioral suite processes a Ticket end to end in-process.
- Behavioral: `[A]bort` mid-loop leaves the working tree byte-identical (no reset, no commit, no archive), stops the lifecycle, releases the sentinel lock, and exits with code 2.
- The "arrives in Spec 04" placeholder and its CLI test assertions are gone; the full suite is green.

### Gotchas
- Keep overrides optional and keyword-only to avoid import cycles; adapters must not import the container.
- Release the sentinel lock before standby and exit (Windows sharing-violation gotcha) on every exit path.
- Do not add Discord or Presence Mode wiring — spec 05 extends this container.
