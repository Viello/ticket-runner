# T007 — Queue directory scanner and TicketRepository store
Status: pending
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Define the `TicketRepository` abstract protocol in `runner/ports/ticket_repository.py` exposing pending-ticket discovery and ordered selection for consumers (queue orchestrator, Doctor).
- Implement `DirectoryTicketStore` in `runner/adapters/markdown/ticket_store.py` that scans `docs/tickets/<spec-slug>/` directories, excludes the `completed/` archive subfolder and `gotchas.md`, orders files by ticket identifier (`T001`, `T002`, ...), and returns the first file with `Status: pending` (user story 5); expose all pending tickets of the active spec queue in execution order.
- Handle an absent `docs/tickets/` root or empty queues by returning empty results rather than raising; surface malformed ticket files with their path so the Runner can report them.
- Refactor `Doctor.check_queue` in `runner/application/doctor.py` to delegate pending-ticket detection to the store instead of its ad-hoc `rglob`/regex scan, keeping all Spec 01 Doctor behavior and tests green.
- Jump-start:
  - Files to touch: `runner/ports/ticket_repository.py`, `runner/adapters/markdown/ticket_store.py`, `runner/application/doctor.py`, `tests/unit/adapters/test_ticket_store.py`, `tests/unit/application/test_doctor.py`.
  - Seams: `runner/ports/ticket_repository.py:TicketRepository` and `runner/adapters/markdown/ticket_store.py:DirectoryTicketStore`.
  - Anchor patterns: protocol style in `runner/ports/config_loader.py`; Doctor construction/DI in `runner/application/doctor.py`; existing behavioral tests in `tests/specs/test_spec_01_doctor.py`.
  - Verification: `pytest tests/unit/adapters/test_ticket_store.py tests/specs/test_spec_01_doctor.py`.

### Acceptance Criteria
- Scanning a temporary `docs/tickets/<spec-slug>/` tree returns only pending tickets ordered by numeric identifier, skipping `completed/`, `gotchas.md`, `.queue.lock`, and `.tmp` artifacts.
- With mixed statuses (`pending`/`running`/`completed`/`skipped`), selection returns the lowest-id pending ticket.
- Tickets inside nested `completed/` folders never appear as pending.
- Doctor's queue check behavior is unchanged: missing directory fails with the same remediation, zero pending tickets fails, pending tickets pass.
- `tests/specs/test_spec_01_doctor.py` remains fully green without modification.
- Unit tests operate against real temporary directory trees.

### Gotchas
- The scanner must not descend into `completed/` or report its archived files; `.queue.lock` and `*.tmp` are runtime artifacts, never tickets.
- Doctor treats zero pending tickets as a hard failure (Spec 01 acceptance); keep that contract even though the orchestrator's standby lifecycle treats an empty queue differently.
- Sort by parsed numeric identifier, not raw filename string comparison, so `T010` orders after `T009`.
- Keep Doctor strictly read-only (Spec 01 gotcha) — the refactor must not create lock files or write anything.
