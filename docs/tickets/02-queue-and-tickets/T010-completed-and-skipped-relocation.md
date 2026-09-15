# T010 — Completed and skipped ticket relocation
Status: pending
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Add `finalize_completed(ticket, completed_at)` to `DirectoryTicketStore`: stamp the header with `Status: completed` and `Completed: <iso-8601 UTC timestamp>`, then relocate the file from `docs/tickets/<spec-slug>/` to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md` (user stories 7, 8).
- Add `finalize_skipped(ticket, details)`: stamp `Status: skipped` plus the Circuit Breaker failure details (reason text, attempt count/timestamps as available), then relocate the file to the same `completed/` archive (user story 10).
- Preserve the ticket's custom markdown formatting through the update (reuse the T006 serializer) and never record a commit SHA in frontmatter (ADR 0012).
- Make relocation collision-safe: fail with a descriptive error if the destination already exists rather than overwriting history.
- Ensure the `completed/` subfolder exists, creating it along with a `.gitkeep` when absent.
- Jump-start:
  - Files to touch: `runner/adapters/markdown/ticket_store.py`, `runner/adapters/markdown/serializer.py`, `tests/unit/adapters/test_ticket_store.py`, `tests/unit/adapters/test_ticket_serializer.py`.
  - Seams: `runner/adapters/markdown/ticket_store.py:DirectoryTicketStore.finalize_completed` / `finalize_skipped`.
  - Anchor patterns: archived files under `docs/tickets/01-doctor-and-git-ops/completed/` show the completed header shape; ADR 0012 for the single-commit lifecycle; Spec 04 owns the `[S]kip` reset contract, this ticket owns only the relocation mechanics.
  - Verification: `pytest tests/unit/adapters/test_ticket_store.py tests/unit/adapters/test_ticket_serializer.py`.

### Acceptance Criteria
- A completed ticket ends up in `completed/` with `Status: completed` and an ISO-8601 `Completed:` timestamp, and no copy remains in the active directory.
- A skipped ticket ends up in `completed/` with `Status: skipped` and its failure details recorded in the header area.
- Formatting outside the header is untouched by stamping and relocation.
- Relocating onto an existing destination fails loudly without data loss.
- `completed/` is created with `.gitkeep` when missing.
- Tests cover both statuses, collision handling, and directory creation on real temp trees.

### Gotchas
- `Completed:` timestamps must be timezone-aware UTC ISO-8601 (`...Z`), matching timestamps written elsewhere by the Runner.
- Relocation happens before the Gatekeeper's single commit so the moved file, code, tests, and gotchas are staged together (ADR 0012); the orchestrator calls this, not the store.
- Once relocated, the scanner (T007) must no longer find the ticket — verify no `.tmp` or partial copies linger in the active directory.
- Moving within the same volume uses `os.replace`; avoid copy+delete fallback unless a cross-volume case requires it.
