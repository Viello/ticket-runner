# Spec 09 — Terminal Host Auto-Detection and Windows Script Execution

## Problem Statement

When an operator presses the interactive TUI hotkey (`[o]`) during runner execution to inspect an active Worker session, the runner spawns an external terminal host attached to `opencode --session <id>` (Spec 06 §4.1 / ADR 0021). 

However, two major friction points degrade this experience on Windows:
1. **Windows Script Invocation Failure (`0x80070002`)**: On Windows, OpenCode is distributed via npm as shell wrappers (`opencode.cmd` and `opencode.ps1`) rather than a standalone compiled PE executable (`opencode.exe`). Windows Terminal (`wt.exe`) directly invokes the Win32 `CreateProcessW` API, which only recognizes executable binaries (`.exe`). When `wt.exe` attempts to launch `opencode` directly, it crashes with `0x80070002` (`ERROR_FILE_NOT_FOUND`: "The system cannot find the file specified"), leaving the operator with a failed terminal tab and an unattached session.
2. **Rigid Static Configuration**: Terminal host selection currently requires manual hardcoding in `config.yaml` (`ui.session_terminal: "wt.exe"`). If an operator runs Ticket Runner from an IDE integrated terminal (VS Code / Antigravity IDE) or a native PowerShell console, the runner cannot detect the caller's terminal context and always spawns whatever host was statically written to the config file, which may be inappropriate or fail depending on the caller environment.

## Solution

1. **Intelligent Terminal Host Auto-Detection (`ui.session_terminal: "auto"`)**: Support dynamic terminal sniffing when `ui.session_terminal` is set to `"auto"` (or left unset). The runner sniffs the caller's process environment:
   - If running inside Windows Terminal (`WT_SESSION` set), selects `wt.exe`.
   - If running inside an IDE integrated terminal (`TERM_PROGRAM=vscode` / `VSCODE_PID`), inspects the caller shell (PowerShell $\rightarrow$ `powershell.exe` / `pwsh.exe`, CMD $\rightarrow$ `cmd.exe`), falling back to `wt.exe` then `powershell.exe` if indeterminate.
   - If running in a standalone shell, inspects the parent process name to match the caller's shell.
   - Falls back gracefully to priority `wt.exe` $\rightarrow$ `pwsh.exe` $\rightarrow$ `powershell.exe` $\rightarrow$ `cmd.exe`.
   - Explicit terminal names in `config.yaml` remain supported and override auto-detection.
2. **Transparent Command Interpreter Wrapping for Windows Scripts**: Update the command builder so that when launching commands via `wt.exe` on Windows, or when the target binary resolves to a batch script (`.cmd` / `.bat`), the invocation is transparently wrapped in the command interpreter (`cmd.exe /c opencode --session <id>`). This satisfies `CreateProcessW` by executing a valid `.exe` (`cmd.exe`) while preserving full argument forwarding and terminal lifetime.
3. **Doctor Pre-Flight Auto Resolution**: Doctor evaluates `"auto"` during pre-flight checks, verifies that the auto-detected candidate exists on PATH, and reports the resolved terminal host name clearly (e.g. `✓ Session terminal host 'auto' resolved to 'wt.exe' on PATH.`).
4. **Universal Resume Hotkey**: Support `[r]` Resume hotkey across all terminal hosts as a universal fail-safe, alongside automatic process-exit detection for non-detaching shells.

## User Stories

1. As an operator running Ticket Runner in Windows Terminal, I want `ui.session_terminal: "auto"` to automatically detect Windows Terminal, so that I don't have to manually configure my terminal host in `config.yaml`.
2. As an operator running Ticket Runner in an IDE integrated terminal (Antigravity IDE or VS Code), I want the runner to detect my IDE shell (e.g. PowerShell) and spawn a standalone matching terminal window, so that my interactive session feels natural and responsive.
3. As an operator on Windows with OpenCode installed via npm (`opencode.cmd`), I want `wt.exe` to successfully launch OpenCode without throwing error `0x80070002`, so that I can inspect sessions in Windows Terminal tabs without file-not-found crashes.
4. As an operator configuring Ticket Runner, I want to explicitly set `ui.session_terminal: "powershell.exe"` or `"cmd.exe"` if desired, so that I can override auto-detection whenever I prefer a specific terminal host.
5. As an operator running pre-flight verification (`python ticket_runner.py doctor`), I want Doctor to report which terminal host `"auto"` resolved to, so that I have immediate visibility into what host will be launched.
6. As an operator with a machine lacking `wt.exe`, I want auto-detection to fall back smoothly to `pwsh.exe`, `powershell.exe`, or `cmd.exe`, so that Ticket Runner never fails startup due to missing optional terminal emulators.
7. As an operator interacting with an external TUI session, I want `[r]` Resume to work regardless of which terminal host was launched, so that I can always unfreeze Ticket Runner even if a shell window detaches or stays open.
8. As a developer inspecting telemetry, I want the ring buffer and runner logs to record the exact resolved command line tokens when launching an external terminal, so that troubleshooting terminal dispatch issues is straightforward.

## Implementation Decisions

1. **Terminal Host Detector Component**:
   - Introduce a dedicated domain/application component `TerminalHostDetector` with dependency injection for environment variables (`Mapping[str, str]`), path resolver (`Callable[[str], str | None]`), and process inspector (`Callable[[], str | None]`).
   - The detector inspects:
     1. `WT_SESSION` environment variable $\rightarrow$ `wt.exe`
     2. `TERM_PROGRAM` / `VSCODE_PID` environment variables $\rightarrow$ matches caller shell (`powershell.exe`, `pwsh.exe`, `cmd.exe`) via process inspection or environment hints (`PSModulePath`), falling back to `wt.exe` then `powershell.exe`.
     3. Parent process ID via `os.getppid()` using standard library `ctypes` on Windows (`QueryFullProcessImageNameW` or Toolhelp snapshot) with zero third-party dependencies.
     4. Default candidate priority fallback: `wt.exe` $\rightarrow$ `pwsh.exe` $\rightarrow$ `powershell.exe` $\rightarrow$ `cmd.exe`.
2. **Command Builder Script Wrapping (`build_tui_command`)**:
   - Update `build_tui_command(host, session_id, command_resolver=None)`.
   - When target host is `wt.exe` (or when the resolved command binary ends with `.cmd` or `.bat` on Windows), wrap the command in `["wt.exe", "cmd.exe", "/c", "opencode", "--session", session_id]`.
   - When target host is `pwsh.exe` or `powershell.exe`, retain `["<host>", "-NoExit", "-Command", "opencode", "--session", session_id]`.
   - When target host is `cmd.exe`, retain `["cmd.exe", "/k", "opencode", "--session", session_id]`.
   - Maintain strict alphanumeric validation on `session_id` and candidate validation on `host` to guarantee shell-injection defense.
3. **Doctor Terminal Host Check Alignment**:
   - Update `Doctor.check_terminal_host()` to recognize `"auto"` (and empty/default value).
   - Resolve the active host using `TerminalHostDetector`, confirm the resolved executable exists on PATH, and return a descriptive `CheckResult` message: `f"Session terminal host '{configured_host}' resolved to '{resolved_host}' on PATH."`.
4. **Universal Resume Hotkey in TuiCoordinator & Warning Panel**:
   - Ensure the hotkey poller accepts `[r]` to resume execution from `tui_open` state across all terminal hosts, not strictly `wt.exe`.
   - For non-detaching hosts (`powershell.exe`, `cmd.exe`), maintain process wait tasks while honoring an immediate manual `[r]` resume override.

## Testing Decisions

1. **Domain Detector Unit Tests**:
   - Test `TerminalHostDetector` using synthetic environment dictionaries and mock process resolvers across all four branches:
     - `WT_SESSION` present $\rightarrow$ returns `wt.exe`.
     - `TERM_PROGRAM=vscode` with PowerShell caller $\rightarrow$ returns `powershell.exe`.
     - `TERM_PROGRAM=vscode` with CMD caller $\rightarrow$ returns `cmd.exe`.
     - Indeterminate caller $\rightarrow$ returns highest-priority host on PATH.
     - No candidate hosts on PATH $\rightarrow$ returns `None`.
2. **Command Builder Tests**:
   - Test `build_tui_command` with `wt.exe` asserting token list: `["wt.exe", "cmd.exe", "/c", "opencode", "--session", session_id]`.
   - Test case insensitivity (`WT.EXE`), full paths (`C:\WindowsApps\wt.exe`), and injection resistance.
3. **Doctor Verification Tests**:
   - Test `check_terminal_host` when configuration is `session_terminal: "auto"`. Assert passed result and message reporting the resolved executable.
4. **Behavioral Protocol Tests**:
   - Test that pressing `[r]` resumes execution when `tui_open` is active for all terminal hosts.

## Out of Scope

- Integrating non-Windows terminal emulators (e.g. Alacritty, iTerm2, Kitty, GNOME Terminal) — Ticket Runner is explicitly targeted to Windows/PowerShell environments.
- Supporting arbitrary user-specified shell command flags in `config.yaml` beyond the supported candidate hosts.
- In-place console takeover (Option B discussed in alignment) — external window/tab is preserved per ADR 0021.

## Further Notes

- `opencode.cmd` resolution relies on `cmd.exe /c`, which is universally present on all Windows installations (`%SystemRoot%\System32\cmd.exe`).
- Zero new external Python dependencies are introduced; process inspection uses Python standard library `ctypes` and `os.getppid()`.
