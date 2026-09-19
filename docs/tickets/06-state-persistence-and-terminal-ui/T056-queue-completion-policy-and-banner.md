# T056 — Queue completion policy, standby polling, and terminal celebration banner
Status: pending
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: T053
Reasoning: medium

### Requirements
- Implement queue completion policies (`standby` vs `terminate`) in `QueueOrchestrator` and `ticket_runner.py` according to Spec 06 User Stories 10–11 and UI Contract:
  - Under `lifecycle.queue_completion = "terminate"`:
    - When all tickets under `docs/tickets/` are completed, render the verbatim celebration banner:
      ```
      ╔══════════════════════════════════════════════════╗
      ║  🎉  Queue complete! All tickets committed.      ║
      ║  {n} tickets  ·  0 failed  ·  ~{k}k tokens      ║
      ╚══════════════════════════════════════════════════╝
      ```
    - Formatted in `bold green` border and text.
    - Variables: `{n}` is the count of tickets committed in this lifecycle run; `{k}` is total tokens accumulated across all sessions rounded to the nearest thousand (e.g. `120k`).
    - Display for 2 seconds (using an injectable sleep seam), then cleanly exit with code 0.
  - Under `lifecycle.queue_completion = "standby"`:
    - When all tickets are processed, release the sentinel `.queue.lock` and enter idle polling checking `docs/tickets/` every `poll_interval` (default 5.0 seconds) for new `Status: pending` tickets.
    - Do NOT render the celebration banner while standing by.
    - When a new ticket appears, re-acquire `.queue.lock` and resume execution immediately.
- Jump-start:
  - Files to touch: `runner/application/queue_orchestrator.py`, `ticket_runner.py`, `tests/unit/application/test_queue_orchestrator.py`, `tests/specs/test_spec_02_queue.py`.
  - Seams: `runner/ports/ticket_repository.py`, `QueueFileLock`, injectable clock/sleep function.
  - Verification: `python -m pytest tests/unit/application/test_queue_orchestrator.py tests/specs/test_spec_02_queue.py`.

### Acceptance Criteria
- Under `terminate` policy, queue completion renders the exact boxed banner with `{n}` and `~{k}k`, pauses 2 seconds, and exits with code 0.
- Under `standby` policy, sentinel `.queue.lock` is released when queue is empty, and orchestrator checks queue at the configured `poll_interval`.
- Newly added pending tickets during standby are picked up, locked, and executed without restarting the runner.
- Banner formatting and border characters match the spec contract verbatim.
- Unit and lifecycle tests assert banner output, token calculations, and exit codes using fake timers.
- Full suite green: `python -m pytest`.

### Gotchas
- The sentinel lock must be released during standby polling so the operator can write new ticket files to disk without lock conflicts.
- Make the 2-second display delay injectable in tests (`asyncio.sleep` seam) to keep test suites instant.
- Token count `{k}` must aggregate tokens consumed across all sessions in the lifecycle run.
