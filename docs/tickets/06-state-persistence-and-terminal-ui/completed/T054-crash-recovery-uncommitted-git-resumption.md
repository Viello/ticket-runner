# T054 — Crash recovery orchestrator with uncommitted git working tree resumption
Status: completed
Completed: 2026-09-19T09:07:00Z
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: T053
Reasoning: medium

### Requirements
- Implement `CrashRecoveryCoordinator` in `runner/application/crash_recovery.py` to restore in-flight ticket execution safely across machine reboots, terminal closures, or unexpected crashes.
- Startup inspection workflow:
  1. Inspect `.agent/state.json`. If `active_ticket_id` is set and `status` indicates active work (`WORKING`, `GATEKEEPER`, `WAITING_FOR_USER`, `PAUSE_REQUESTED`):
     a. Inspect working tree status using `git status --porcelain`. Identify uncommitted files, ignoring `.agent/` and untracked build artifacts. Do NOT discard or reset working tree changes.
     b. Inspect `tui_open`: If `tui_open: true`, log a prominent warning: `"Runner exited while TUI session was open (session: <tui_session_id>). TUI may still be running. Resuming managed execution."` and clear both `tui_open` and `tui_session_id` in state.
     c. If `opencode_session_id` is recorded, construct a reconnection prompt. If uncommitted files were detected, list them: `"Resuming session after restart. Uncommitted edits detected in: <files>. Continue implementation for ticket <active_ticket_id>."`; if tree is clean, use `"Resuming session after restart. Continue implementation for ticket <active_ticket_id>."`.
     d. Attempt session resumption. If OpenCode rejects the session id or resumption fails, inspect `.agent/checkpoints/{active_ticket_id}/` for the latest `handoff.md` and initiate Session B recovery carrying the checkpoint context.
  2. If `state.json` indicates `IDLE` or is absent, allow normal queue execution to proceed without intervention.
  3. If `state.json` exists but contains malformed JSON or invalid schema (`StateFormatError`), quarantine the corrupted file by renaming to `state.json.corrupt.<timestamp>`, log an error, and initialize a clean state document.
- Integrate `CrashRecoveryCoordinator` into `ticket_runner.py` startup sequence (`run_start`) and `RunnerContainer`.
- Jump-start:
  - Files to touch: `runner/application/crash_recovery.py`, `runner/application/__init__.py`, `runner/container.py`, `ticket_runner.py`, `tests/unit/application/test_crash_recovery.py`.
  - Seams: `runner/ports/state_store.py`, `runner/application/git_operations.py`, `runner/application/worker_supervisor.py`.
  - Anchor patterns: follow `runner/application/model_selection.py` for startup interactor structure.
  - Verification: `python -m pytest tests/unit/application/test_crash_recovery.py`.

### Acceptance Criteria
- Crash recovery preserves uncommitted working tree edits and passes the modified file list into the OpenCode reconnection prompt.
- When `tui_open: true` is persisted on disk, recovery logs the warning, resets `tui_open` to `false`, clears `tui_session_id`, and resumes managed execution.
- Successful session resumption re-attaches to the existing `opencode_session_id`.
- Failed session resumption triggers checkpoint fallback: discovers the latest `handoff.md` under `.agent/checkpoints/{ticket_id}/` and resumes via Session B.
- Malformed state files trigger quarantine to `state.json.corrupt.<timestamp>` and log a clear diagnostic without crashing the runner process.
- End-to-end tests verify recovery behavior with clean git tree, dirty git tree, crashed TUI flag, and checkpoint fallback.
- Full suite green: `python -m pytest`.

### Gotchas
- Never run `git reset --hard` during crash recovery: partial work must be preserved and communicated to the Worker.
- Filter out `.agent/` paths from `git status --porcelain` results so runtime state is not reported as uncommitted edits.
- The reconnection prompt must be passed via `--auto` to avoid interactive prompt freezes.
