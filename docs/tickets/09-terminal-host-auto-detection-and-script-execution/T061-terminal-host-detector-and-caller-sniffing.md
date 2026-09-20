# T061 — Terminal host detector and caller environment sniffing
Status: pending
Blocked by: T060
Security: required
Reasoning: low

### Requirements
- Implement `TerminalHostDetector` in `runner/adapters/ui/terminal_detector.py` to auto-detect the active caller terminal environment without external third-party dependencies.
- Sniffing hierarchy:
  1. `WT_SESSION` environment variable $\rightarrow$ `wt.exe`.
  2. `TERM_PROGRAM=vscode` or `VSCODE_PID` (IDE integrated terminal) $\rightarrow$ inspect caller shell (`powershell.exe`, `pwsh.exe`, `cmd.exe`) via parent process inspection or environment cues (`PSModulePath`), falling back to `wt.exe` then `powershell.exe`.
  3. Standalone shell $\rightarrow$ inspect parent process via `os.getppid()` using standard library `ctypes` (`QueryFullProcessImageNameW`).
  4. General fallback priority: `wt.exe` $\rightarrow$ `pwsh.exe` $\rightarrow$ `powershell.exe` $\rightarrow$ `cmd.exe`.
- Jump-start:
  - Files to touch: `runner/adapters/ui/terminal_detector.py`, `tests/unit/adapters/test_terminal_detector.py`.
  - Seams: `TerminalHostDetector.detect(env, path_resolver, ppid_resolver)`.
  - Anchor patterns: `Doctor._path_resolver` and `validate_terminal_host()` in `runner/adapters/ui/tui_launcher.py`.
  - Verification command: `python -m pytest tests/unit/adapters/test_terminal_detector.py`.

### Acceptance Criteria
- `TerminalHostDetector.detect()` returns `"wt.exe"` when `WT_SESSION` is set and `wt.exe` is found on PATH.
- `detect()` returns `"powershell.exe"` or `"cmd.exe"` when running inside an IDE integrated terminal matching the caller shell.
- `detect()` inspects parent process ID via `os.getppid()` and matches known candidate shell binaries.
- `detect()` falls back in priority order (`wt.exe` $\rightarrow$ `pwsh.exe` $\rightarrow$ `powershell.exe` $\rightarrow$ `cmd.exe`) when caller shell is indeterminate.
- `detect()` returns `None` if no candidate terminal hosts exist on PATH.
- Unit tests cover all detection branches, edge cases, and missing PATH candidates using synthetic environments and dependency injection without spawning real processes.

### Gotchas
- Do not import third-party packages (like `psutil`); rely strictly on Python standard library `os`, `sys`, `ctypes`, and `shutil`.
- Always verify detected candidates against `path_resolver` before returning them so non-existent binaries are never selected.
