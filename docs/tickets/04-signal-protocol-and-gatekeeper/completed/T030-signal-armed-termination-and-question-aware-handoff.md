# T030 — Signal-armed termination and question-aware handoff
Status: completed
Completed: 2026-09-17T07:55:00Z
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T026, T027

### Requirements
- Supervise Signal-armed termination in the Worker supervisor: from the first appearance of either the ready Signal or a question Signal for the active Ticket, the Worker has a 10-second grace to exit; if it is still alive when the grace elapses, run the existing termination ladder and record a new `RunTerminationReason.KILLED_SIGNAL`. The grace clock starts once per Session Run, is evaluated on stream-loop iterations (no threads, no real sleeps), and never resets on repeated polls.
- A signal-killed run must not classify as a crash: `SessionRunResult.is_crash` is `False` for `KILLED_SIGNAL`, and the existing file-presence ready detection proceeds normally downstream.
- Make the handoff coordinator question-aware: when a Session Run ends and a pending question Signal exists, return control with a new `SingleCycleStatus.QUESTION_PENDING` plus the active session id instead of running the nudge or crash-retry paths; the question file stays untouched. An answered question must not trigger this.
- Jump-start:
  - Files to touch: `runner/application/worker_supervisor.py`, `runner/application/handoff_coordinator.py`, `tests/unit/application/test_worker_supervisor.py`, `tests/unit/application/test_handoff_coordinator.py`, `tests/specs/test_spec_04_gatekeeper.py` (new suite file with module docstring and local helpers).
  - Seams: the injected clocks already used in supervisor and handoff tests; `RuntimePaths` signal paths; `SignalRepository.read_pending_question` injected via the fake.
  - Anchor patterns: stall and ceiling watchdog tests for deterministic time; fake hooks that author files on process completion; helper style in `tests/specs/test_spec_03_worker.py`.
  - Verification: `pytest tests/unit/application/test_worker_supervisor.py tests/unit/application/test_handoff_coordinator.py tests/specs/test_spec_04_gatekeeper.py`.

### Acceptance Criteria
- Behavioral: with an injected clock, a Worker that writes the ready Signal and then keeps streaming is killed after exactly the 10-second grace with reason `KILLED_SIGNAL` and `is_crash` false.
- A Worker that exits within the grace keeps reason `EXITED` and is never killed; ceiling or stall conditions that fire first keep their own reasons.
- Bounded runs watch signals too, and a supervisor reused across chained runs resets grace state per run.
- Coordinator returns `QUESTION_PENDING` with the session id populated, the question file untouched, and no nudge prompt for a pending question; answered or absent questions keep the old behavior.
- Unit tests for the two changed components stay green.

### Gotchas
- Do not alter stall (`STALL_SILENCE_SECONDS`) or ceiling semantics; the poll only adds checks.
- Poll evaluation must not starve the stream reader, and the graceful path must still persist the final buffered stdout line per the drain-race invariants.
- `taskkill` exit codes are non-zero — classify via the termination reason, never via the raw code.
