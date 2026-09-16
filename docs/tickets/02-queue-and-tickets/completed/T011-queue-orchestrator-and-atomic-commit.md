# T011 — Queue orchestrator: lock lifecycle, processor seam, and atomic commit
Status: completed
Completed: 2026-09-16T06:56:25Z
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Implement `QueueOrchestrator` in `runner/application/queue_orchestrator.py` executing tickets strictly one at a time through an injected processor seam (`Callable[[Ticket], Awaitable[TicketOutcome]]` or equivalent protocol) so Spec 03 can plug in the Worker supervisor without changing queue mechanics.
- Per-ticket cycle: acquire the sentinel lock (T008), select the first pending ticket (T007), invoke the processor, then on approval append new gotchas (T009) + relocate the ticket as completed (T010) + author exactly one `GitOperations.commit_ticket` commit staging code, tests, gotchas, and the relocated ticket together (user stories 5, 8).
- On a skipped outcome, reset the working tree via `GitOperations.reset_working_tree()` and relocate the ticket as skipped with failure details (user story 10 mechanics; the `[S]kip` policy itself is Spec 04).
- Manage the lock lifecycle: held while a ticket is processing, released on pause/question wait/Circuit Breaker (user story 3), re-acquired with a fresh `docs/tickets/` rescan on resume so newly added or edited tickets are picked up (user story 4).
- Expose `pause()` / `resume()` primitives for the Spec 06 hotkey layer; never parse model stdout for queue state (ADR 0004; signals are Spec 04's responsibility).
- Respect the commit conventions: scope names a subsystem such as `queue`, never a ticket number, no ticket numbers in title or body, bullets imperative without trailing periods (AGENTS.md).
- Jump-start:
  - Files to touch: `runner/application/queue_orchestrator.py`, `tests/unit/application/test_queue_orchestrator.py`, `tests/specs/test_spec_02_queue.py`.
  - Seams: `runner/application/queue_orchestrator.py:QueueOrchestrator` composing `DirectoryTicketStore`, `QueueFileLock`, `GotchasStore`, `GitOperations`.
  - Anchor patterns: `GitOperations.commit_ticket` / `reset_working_tree` in `runner/application/git_operations.py`; interaction-style tests in `tests/unit/application/test_git_operations.py` using `FakeCommandRunner`; sequential state machine in `ticket-runner-plan.md` §4.
  - Verification: `pytest tests/unit/application/test_queue_orchestrator.py tests/specs/test_spec_02_queue.py`.

### Acceptance Criteria
- Given a temp queue with multiple pending tickets and a fake processor, tickets execute one at a time in identifier order; no ticket starts before the previous one is finalized.
- On approval, exactly one commit is authored containing the relocation and gotchas changes (verified through recorded git invocations or a real temp repo), and the ticket file sits under `completed/`.
- On skip, the working tree is reset and the ticket is archived as skipped without a feature commit.
- The sentinel lock is held during processing and released while paused; resuming re-acquires the lock and picks up a ticket inserted during the pause.
- Spec-level tests in `tests/specs/test_spec_02_queue.py` exercise the orchestration end-to-end against temporary directory trees without a live Worker.

### Gotchas
- `GitOperations.commit_ticket` stages everything via `git add .`; the orchestrator must never leave stray temp/lock artifacts (T008 `.gitignore` entries) and must write gotchas + relocate before committing.
- One commit per ticket means ordering matters: serialize ticket → relocate → append gotchas → commit; any failure before commit must not leave a half-updated active queue.
- Pause release must close the lock handle, not merely set a flag, so external editors can write on Windows.
- Tests must call async coroutines via `asyncio.run` in synchronous test functions (no `pytest-asyncio` in this repo).
- Do not implement Worker invocation, prompt composition, or signal parsing here — Specs 03/04 own those; the processor seam is the contract boundary.
