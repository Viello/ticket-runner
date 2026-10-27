# T122 — Enforce Gatekeeper Ownership of docs/tickets/ and Idempotent Ticket Finalization
Status: pending
Spec: docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md
Blocked by: None
Reasoning: medium

### Requirements
- Scope Step 4 (`Ticket Transition & Gotchas`) and Step 6 (`Readiness & Live QA`) in `.agents/skills/implement/SKILL.md` so that in Ticket Runner autonomous execution, the Worker never edits `docs/tickets/gotchas.md`, never stamps `Status: completed`, and never relocates the Ticket file into `completed/`, instead passing `new_gotchas` and all required fields (`ticket_id`, `status: "ready_for_verification"`, `modified_files`, `self_review_notes`, `new_gotchas`, `timestamp`) in `.agent/signals/<ticket_id>_ready.json`.
- Expand Guardrail 1 in `PromptBuilder` (`runner/application/prompt_builder.py`) to `No Git Staging, Commits, or Queue File Mutations`, explicitly forbidding `git add` / `git commit`, editing `docs/tickets/gotchas.md` directly, or modifying, moving, or deleting any Ticket markdown file under `docs/tickets/`.
- Harden `DirectoryTicketStore._resolve_ticket_path` and `DirectoryTicketStore.finalize_completed` (`runner/adapters/markdown/ticket_store.py`) so that if a Worker prematurely moved the active Ticket file to `<spec_dir>/completed/<ticket_filename>.md` before Gatekeeper finalization, `finalize_completed` locates the file inside `completed/`, updates `Status: completed` and `Completed: <ISO-8601-UTC-timestamp>` in place (ensuring `.gitkeep` exists), and returns the destination `Path` cleanly without raising `TicketFormatError`.
- Jump-start orientation: inspect `.agents/skills/implement/SKILL.md`, `runner/application/prompt_builder.py` (`build_prompt`), `runner/adapters/markdown/ticket_store.py` (`DirectoryTicketStore._resolve_ticket_path`, `_relocate_ticket`, `finalize_completed`), `tests/unit/application/test_prompt_builder.py`, and `tests/unit/adapters/test_ticket_store.py`. Verify with `python -m pytest tests/unit/application/test_prompt_builder.py tests/unit/adapters/test_ticket_store.py -x`.

### Acceptance Criteria
- `.agents/skills/implement/SKILL.md` marks Step 4 (`Ticket Transition & Gotchas`) as `*(interactive mode only — skip in Ticket Runner autonomous execution; pass new gotchas via the ready signal JSON and let Gatekeeper relocate the ticket)*` and Step 6 specifies the full autonomous ready Signal schema (`status: "ready_for_verification"`, `modified_files`, `self_review_notes`, `new_gotchas`, `timestamp`) while stating that ticket relocation and `docs/tickets/gotchas.md` updates belong to the Gatekeeper.
- `PromptBuilder.build` output contains the explicit guardrail prohibiting modifications, moves, or deletions under `docs/tickets/` (including the active Ticket file and `docs/tickets/gotchas.md`).
- Calling `DirectoryTicketStore.finalize_completed(ticket, completed_at=...)` when `ticket.path` has already been moved to `<spec_dir>/completed/<ticket.path.name>` succeeds idempotently, stamps `Status: completed` and `Completed: <timestamp>` in place, and returns the `completed/` path without raising `TicketFormatError`.

### Gotchas
- Do not relax `DirectoryTicketStore`'s error handling when a ticket file is genuinely missing from both `<spec_dir>/` and `<spec_dir>/completed/`; `TicketFormatError("Ticket file not found: ...")` must still raise when neither path exists.
- Keep `finalize_skipped` and existing `test_ticket_store.py` contracts green; double- check whether any existing test asserts `finalize_completed` on a path already passed as `.../completed/T001.md` vs. a `Ticket` entity whose `ticket.path` pointed to the pending directory before being moved.
