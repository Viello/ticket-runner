# T032 — Ready-path ticket processor
Status: pending
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T031

### Requirements
- Implement the `TicketProcessor` seam for the ready path: purge stale Signals for the Ticket at start (Isolation Layer), build the initial Worker prompt through the prompt builder, drive the verification loop, and map a passing result into `TicketOutcome.approved` with `changes` as `["Update <path>", ...]` from `modified_files`, `new_gotchas` passed through, `scope` from the Signal when present, and `self_review_notes` surfaced to the terminal log only (never committed).
- A skipped result becomes `TicketOutcome.skipped(details=<last diagnostics>)`; the orchestrator already resets the tree and archives — the processor must not.
- Update the Worker prompt text to document the full ready Signal schema: field names, statuses, the optional `scope`, and the question protocol (write the question Signal and stop working when blocked).
- Jump-start:
  - Files to touch: `runner/application/ticket_processor.py` (new), `runner/application/prompt_builder.py`, `tests/unit/application/test_prompt_builder.py`, `tests/unit/application/test_ticket_processor.py` (new), `tests/specs/test_spec_04_gatekeeper.py` (append).
  - Seams: `TicketProcessor` protocol and `TicketOutcome.approved/skipped` in `runner/application/queue_orchestrator.py`; the loop result from T031.
  - Anchor patterns: real temp-git commit tests in `tests/specs/test_spec_02_queue.py`; suite helpers in `tests/specs/test_spec_03_worker.py`.
  - Verification: `pytest tests/unit/application/ tests/specs/test_spec_04_gatekeeper.py`.

### Acceptance Criteria
- Behavioral: the happy path through the orchestrator in a real temp git repo with fake command streams and scripted intervention produces exactly one commit `feat(<scope>): <title>` whose body carries `Update <path>` bullets and appended gotchas; the Ticket is relocated to `completed/`; the ready file is gone.
- A malformed ready Signal resumes with diagnostics and can only pass on a later valid cycle; attempts obey `max_attempts`.
- `scope` absent falls back to the orchestrator default; present is used verbatim in the commit header.
- Purge at start removes leftover ready and question files from earlier runs.
- Prompt tests cover the documented schema and question protocol text.

### Gotchas
- Fakes must author Signal files deterministically inside process-completion hooks — never `asyncio.sleep`.
- Keep the orchestrator's fixed finalize order (relocate, append gotchas, single commit); the processor only supplies outcome data.
- The new module is not in the architecture doc's target tree — record a gotcha proposing the doc update instead of editing root living docs.
