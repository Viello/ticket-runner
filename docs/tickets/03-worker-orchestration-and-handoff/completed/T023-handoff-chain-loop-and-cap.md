# T023 — Handoff coordinator B: chain loop and cap
Status: completed
Completed: 2026-09-16T14:03:00Z
Security: required
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Loop the T021 single-cycle flow until the Worker Session finishes `READY` or routes to T022 escalation; each cycle re-validates Checkpoint freshness, so an old file can never satisfy a new handoff request (ADR 0014).
- Count consecutive handoffs within the ticket; on exceeding `MAX_CONSECUTIVE_HANDOFFS = 5` (module scope), escalate through T022 with "5 handoffs without completion" in the escalation payload instead of starting a sixth session.
- Complete the public result type for Spec 04's future `TicketProcessor` adapter: `WorkerRunResult(status: READY|ESCALATED, session_ids, handoffs, occupancy, ready_signal_present, jsonl/stderr paths per session, escalation details)`; `handoffs` counts instruction runs, and `session_ids` lists every Worker Session in order.
- Emit a notice per handoff cycle through the T019 seam (threshold crossed, checkpoint validated, session N+1 started).
- Security: required — drives repeated Worker invocations. Explicitly verify: loop termination is guaranteed (READY, escalation, or cap) and observable; no unbounded spawn loop is reachable from a scripted stream; per-cycle logs never collide (session ids differ across fresh sessions).
- Jump-start:
  - Files to touch: `runner/application/handoff_coordinator.py`, `tests/unit/application/test_handoff_coordinator.py`.
  - Seams: T021 cycle method, T022 escalation entry point, T019 `notify`.
  - Anchor patterns: run-loop structure and injected bounds in `QueueOrchestrator.run_lifecycle` (standby loop with `max_standby_iterations`).
  - Verification: `pytest tests/unit/application/test_handoff_coordinator.py`.

### Acceptance Criteria
- A scripted A→B→C chain validates a fresh checkpoint per cycle and finishes `READY`; the fake supervisor records exactly the expected spawn sequence and `session_ids` has three entries.
- A chain reaching the cap escalates without a sixth session spawn, and the escalation payload names the handoff count.
- `READY` ends the loop immediately (no trailing handoff); every loop termination path is covered by a test.

### Gotchas
- The single canonical checkpoint path is overwritten each cycle — freshness (not filename) is what makes a cycle provable; keep the 2s slack centralized.
- Session ids differ for each fresh session, so log files never collide; still assert distinct paths in tests.
- Keep the cap constant at module scope; the escalation payload must stay presentation-free (Spec 05 renders it).
