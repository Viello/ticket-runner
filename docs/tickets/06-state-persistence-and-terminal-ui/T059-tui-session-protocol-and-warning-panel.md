# T059 — TUI Session pause-and-open protocol, warning panel, and process lifecycle
Status: pending
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: T054, T055, T058
Security: required
Reasoning: medium

### Requirements
- Implement the TUI Session Pause-and-Open protocol according to Spec 06 User Stories 12–16, 18–19 and ADR 0021:
  1. Two-key confirmation modal state machine:
     - Normal state: `[p] pause  [m] toggle mode  [q] quit  [o] open TUI`.
     - Pressing `[o]` enters `CONFIRM_TUI_OPEN` state, updating row 6 to `Open TUI? [y] confirm / [n] cancel`.
     - Pressing `[n]` cancels and restores the normal hotkey legend.
     - Pressing `[y]`:
       - If a Session Run is currently executing, transition row 6 to `[p] pause  [m] toggle mode  [q] quit  [o] pending…` and queue intent until the next signal boundary.
       - If at a signal boundary (or once reached), launch the TUI session.
  2. TUI session launch sequence:
     a. Persist `tui_open: true` and `tui_session_id: <active_session_id>` to `.agent/state.json` via `StateCoordinator`.
     b. Freeze the Rich `Live` dashboard and render the full-screen warning panel:
        ```
        ⚠  OpenCode TUI open — Runner is paused & blind
           Execution is paused: no Gatekeeper, no Circuit Breaker, no token tracking.
           Tokens consumed in TUI are NOT tracked against the 135k handoff budget.
           Work done in TUI bypasses the Gatekeeper and Signal protocol.
           Close the terminal window to resume managed execution.
           [r] Resume  (required if using Windows Terminal)
        ```
        - Styling: `⚠` and line 1 in `bold yellow`; lines 2–5 in `dim white`; line 6 (`[r] Resume`) in `bold green`.
        - Row 6 hotkey legend displays: `[r] Resume  (all other keys suspended)`.
     c. Spawn the configured terminal host (`config.ui.session_terminal`) as an external subprocess:
        - `wt.exe`: `wt.exe opencode --session <id>` (immediately detaches).
        - `pwsh.exe`: `pwsh.exe -NoExit -Command opencode --session <id>`.
        - `powershell.exe`: `powershell.exe -NoExit -Command opencode --session <id>`.
        - `cmd.exe`: `cmd.exe /k opencode --session <id>`.
     d. Wait for exit or `[r]` resume:
        - For blocking terminal hosts (`cmd.exe`, `powershell.exe`, `pwsh.exe`), await process exit or accept `[r]` to resume immediately.
        - For `wt.exe`, await `[r]` keypress on the keyboard dispatcher.
  3. Resume managed execution:
     a. Clear `tui_open` and `tui_session_id` in `.agent/state.json`.
     b. Restore the normal Rich Live dashboard layout.
     c. Start a fresh Session Run on the same session id with the resume banner:
        `--auto "Resuming after user inspection via TUI. Continue from where you left off."`.
- Add comprehensive spec-level behavioral tests in `tests/specs/test_spec_06_state_ui.py` exercising the full state machine, signal boundary queuing, process invocation, warning panel rendering, universal `[r]` resume, and crash recovery warning when `tui_open: true`.
- Jump-start:
  - Files to touch: `runner/adapters/ui/tui_launcher.py`, `runner/application/tui_coordinator.py`, `runner/adapters/ui/terminal.py`, `runner/adapters/ui/keyboard.py`, `runner/application/worker_supervisor.py`, `tests/unit/application/test_tui_session.py`, `tests/specs/test_spec_06_state_ui.py`.
  - Seams: `runner/ports/command_runner.py`, `StateStore`, `TerminalDisplay`.
  - Verification: `python -m pytest tests/unit/application/test_tui_session.py tests/specs/test_spec_06_state_ui.py`.

### Acceptance Criteria
- Pressing `[o]` initiates the confirm-pending modal without blocking the `asyncio` event loop.
- Pressing `[n]` cancels the modal and restores the normal legend cleanly.
- Mid-run `[o] -> [y]` queues intent until the signal boundary without interrupting the active Session Run.
- At signal boundary, `state.json` records `tui_open: true` and `tui_session_id` before terminal spawn.
- The frozen warning panel renders verbatim matching the text and color specifications.
- The configured terminal host command is executed with the expected `--session <id>` argument.
- Process termination or pressing `[r]` clears `tui_open`, restores the dashboard, and injects the `--auto` resume banner.
- Security verification passes: terminal commands strictly validate terminal host paths and prevent command injection.
- Full suite green: `python -m pytest`.

### Gotchas
- Never launch the TUI session while a Session Run is active: OpenCode on-disk session state will corrupt if accessed by two concurrent processes.
- Windows Terminal (`wt.exe`) detaches immediately upon tab creation, so the runner must rely on `[r]` keypress to detect when the operator is ready to resume.
- Ensure all subprocess spawns use list arguments (`exec` mode) rather than raw shell strings to prevent shell escaping bugs.
