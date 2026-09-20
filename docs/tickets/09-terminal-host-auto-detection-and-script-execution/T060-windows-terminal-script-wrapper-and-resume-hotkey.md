# T060 — Windows Terminal script wrapper defense and universal resume hotkey
Status: pending
Security: required
Reasoning: low

### Requirements
- Fix `0x80070002` (`ERROR_FILE_NOT_FOUND`) when Windows Terminal (`wt.exe`) launches OpenCode on Windows: update `build_tui_command` in `runner/adapters/ui/tui_launcher.py` so that `wt.exe` commands are wrapped in `["wt.exe", "cmd.exe", "/c", "opencode", "--session", session_id]`.
- Update `TuiCoordinator` and `RichTerminalDisplay` to enable universal `[r]` Resume hotkey support across all terminal hosts (`wt.exe`, `powershell.exe`, `pwsh.exe`, `cmd.exe`), allowing operators to unfreeze Ticket Runner at any time during an interactive TUI session.
- Jump-start:
  - Files to touch: `runner/adapters/ui/tui_launcher.py`, `runner/application/tui_coordinator.py`, `runner/adapters/ui/terminal.py`, `tests/unit/application/test_tui_session.py`, `tests/specs/test_spec_06_state_ui.py`.
  - Seams: `build_tui_command` and `TuiCoordinator.handle_hotkey`.
  - Anchor patterns: Existing `build_tui_command` in `runner/adapters/ui/tui_launcher.py` and `HOTKEY_LEGENDS` in `runner/adapters/ui/terminal.py`.
  - Verification command: `python -m pytest tests/unit/application/test_tui_session.py tests/specs/test_spec_06_state_ui.py`.

### Acceptance Criteria
- `build_tui_command("wt.exe", session_id)` returns `["wt.exe", "cmd.exe", "/c", "opencode", "--session", session_id]`.
- `build_tui_command("WT.EXE", session_id)` and full paths (e.g. `C:\WindowsApps\wt.exe`) also return the `cmd.exe /c` wrapped command.
- Shell injection characters in `session_id` and `host` remain strictly rejected via `validate_session_id()` and `validate_terminal_host()`.
- `[r]` keypress in `tui_open` state immediately resumes runner execution across all terminal hosts (`powershell.exe`, `cmd.exe`, `pwsh.exe`, `wt.exe`).
- All existing and updated unit tests in `tests/unit/application/test_tui_session.py` and `tests/specs/test_spec_06_state_ui.py` pass cleanly.

### Gotchas
- On Windows, `wt.exe` executes commands directly with Win32 `CreateProcessW` without a shell interpreter, failing on npm-installed `.cmd`/`.ps1` wrappers unless invoked via `cmd.exe /c`.
- In `tui_coordinator.py`, ensure non-detaching hosts (`powershell.exe`, `cmd.exe`) still clean up their background process wait tasks if the operator resumes early using the universal `[r]` hotkey.
