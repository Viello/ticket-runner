# Spec 06: State Persistence, Crash Recovery, and Terminal UI

## Problem Statement

Autonomous orchestrators running across long hours are vulnerable to operating system reboots, terminal closures, and unexpected crashes. If state is held purely in memory, uncommitted progress and session tracking are lost. Furthermore, static terminal logging provides poor visibility into token limits and active progress, while blocking console inputs cause frozen interfaces.

## Solution

Persist orchestrator execution state continuously to `.agent/state.json` using atomic disk writes, providing full crash recovery across restarts. Render a split interactive dashboard in the terminal using `rich.live.Live` with a pinned status/token panel and scrolling telemetry ring buffer, driven by non-blocking Windows console hotkeys (`[p]`, `[m]`, `[q]`) within the `asyncio` event loop.

## User Stories

1. As a developer, I want the Runner to persist its operational state to `.agent/state.json` on every state transition, so that progress is durable across sudden machine reboots or power outages.
2. As a developer, I want state updates written atomically using temporary file replacements, ensuring that `.agent/state.json` is never corrupted by partial writes.
3. As a developer, I want the Runner to detect an interrupted run on startup, inspect `git status`, and automatically resume the active session or checkpoint without losing progress.
4. As a developer, I want a split live terminal dashboard in `nearby` mode showing a pinned top header with Ticket ID, status, token gauge, presence mode, and hotkey hints.
5. As a developer, I want the terminal dashboard to display a scrolling ring buffer showing the last 15 lines of Worker tool invocations and Gatekeeper diagnostics, keeping active work visible.
6. As a developer, I want to press `[p]` in the terminal to immediately pause execution, releasing the `tickets.md` file lock so I can edit the queue.
7. As a developer, I want to press `[m]` in the terminal to immediately toggle between `nearby` and `away` mode, adjusting notification targets without restarting the process.
8. As a developer, I want to press `[q]` in the terminal to trigger a graceful shutdown that terminates active child subprocesses cleanly and saves state before exiting.
9. As a developer, I want console hotkey polling to execute non-blockingly on Windows (`msvcrt.kbhit()`), ensuring the terminal UI never freezes the `asyncio` event loop.
10. As a developer, I want the Runner to support configurable queue completion behavior (`standby` vs `terminate`), allowing it to either monitor `tickets.md` for new items or cleanly exit when all tickets are completed.
11. As a developer, I want a clear terminal banner announcing queue completion when all tickets pass verification, celebrating completed milestones.
12. As a developer, I want to press `[o]` in the terminal to open an interactive OpenCode TUI window for the active Worker Session, so I can inspect session history or send messages directly when needed.
13. As a developer, I want pressing `[o]` to require a two-key confirmation (`[y]` to confirm / `[n]` to cancel`) before anything happens, so accidental keypresses don't disrupt execution.
14. As a developer, I want the Runner to wait for the next signal boundary before handing control to the TUI window, so no in-flight Session Run work is lost by a mid-run termination.
15. As a developer, I want the Rich dashboard to freeze and display a prominent warning panel while the TUI window is open, making it clear that the Runner is paused and all managed safety mechanisms are suspended.
16. As a developer, I want the warning panel to state that execution is paused, tokens consumed in TUI are untracked, and work done in TUI bypasses the Gatekeeper and Signal protocol, so I understand the full consequence before interacting.
17. As a developer, I want the Doctor to detect available terminal hosts (wt.exe, pwsh.exe, powershell.exe, cmd.exe) once on first run and prompt me to choose, persisting my selection to `config.yaml` under `ui.session_terminal`, so I never have to configure it manually.
18. As a developer, I want the Runner to inject a short resume banner via `--auto` when starting a fresh Session Run after I close the TUI window, so the model is re-oriented without needing to re-read its entire session history.
19. As a developer, I want `state.json` to record `tui_open` and `tui_session_id` so that if the Runner crashes while the TUI is open, crash recovery logs a warning and clears the flag rather than resuming into an ambiguous state.

## Implementation Decisions

- **State Schema (`.agent/state.json`)**:
  Stores `active_ticket_id` (string or null), `status` (`"IDLE"`, `"WORKING"`, `"GATEKEEPER"`, `"WAITING_FOR_USER"`, `"PAUSE_REQUESTED"`, `"CIRCUIT_BREAKER_TRIPPED"`), `opencode_session_id` (string or null), `presence_mode` (`"nearby"` | `"away"`), `verification_attempts` (integer), `tokens` object (`current` integer, `warning_sent` boolean), `branch` (string), `started_at` (ISO-8601), `last_checkpoint` (path or null), `tui_open` (boolean, default `false`), `tui_session_id` (string or null), and `last_updated` (ISO-8601).
- **Atomic State Writes**: All writes to `state.json` write to `state.json.tmp` and execute an atomic replace (`os.replace`).
- **Crash Recovery Logic**:
  On startup, if `status` in `state.json` indicates an in-flight ticket:
  1. Inspect `git status --porcelain` to identify uncommitted edits.
  2. If an `opencode_session_id` is recorded, attempt to resume the session with a reconnection prompt.
  3. If session resumption fails, inspect `.agent/checkpoints/{active_ticket_id}/` for the latest `handoff.md` and resume via Session B.
- **Rich Terminal Dashboard Architecture**: Built with `rich.live.Live` rendering a `rich.layout.Layout` divided into two panels:
  - Top panel (fixed 6 rows): Displays status header, stylized token progress bar (`[████░░░░░░] 48,200 / 135,000`), current Presence Mode, and hotkey legend.
  - Bottom panel: Displays a rolling fixed-size ring buffer (15 entries) of timestamped Worker tool calls and Gatekeeper logs.
- **Non-Blocking Keyboard Polling**: On Windows, keyboard input is polled using `msvcrt.kbhit()` and `msvcrt.getch()` scheduled as an async polling loop with a 50ms interval, ensuring responsive hotkey handling without blocking async tasks.
- **Queue Completion Policy**:
  - `standby`: runner enters idle polling loop checking `tickets.md` every 5 seconds for new `Status: pending` tickets.
  - `terminate`: runner prints completion summary and exits with code 0.
- **TUI Session Hotkey (`[o]`) — Pause-and-Open Protocol** (ADR 0021):
  - Pressing `[o]` initiates a two-key confirmation sequence: the dashboard status bar changes to `"Open TUI? [y] confirm / [n] cancel"` and keyboard polling waits for `[y]` or `[n]` only. The `asyncio` event loop is not blocked; a `CONFIRM_TUI_OPEN` state flag gates the poller.
  - Confirmation fires immediately on `[o]` press. If a Session Run is active, the confirmed intent is queued and the hotkey legend dims to `[o] pending…` with a status note `"TUI open queued — waiting for signal boundary."`
  - At the next signal boundary (between Session Runs), the Runner:
    1. Sets `tui_open: true` and `tui_session_id: <active session id>` in `state.json`.
    2. Freezes the Rich `Live` dashboard and renders the warning panel (see below).
    3. Spawns the configured terminal host as a subprocess: `<terminal_host> /k opencode --session <id>` (cmd/PowerShell form) or the configured equivalent.
    4. For cmd.exe and powershell.exe: awaits process exit (`await proc.wait()`) before offering resume.
    5. For wt.exe: process detaches immediately; the warning panel displays `[r] Resume` as the only active hotkey.
  - On TUI window close (or `[r]` press for wt.exe), the Runner:
    1. Clears `tui_open` and `tui_session_id` in `state.json`.
    2. Restores the Rich dashboard.
    3. Starts a fresh Session Run on the same session id with resume banner: `--auto "Resuming after user inspection via TUI. Continue from where you left off."`
- **Dashboard Warning Panel (TUI open state)**:
  Rendered as a frozen Rich panel replacing normal dashboard content:
  ```
  ⚠  OpenCode TUI open — Runner is paused & blind
     Execution is paused: no Gatekeeper, no Circuit Breaker, no token tracking.
     Tokens consumed in TUI are NOT tracked against the 135k handoff budget.
     Work done in TUI bypasses the Gatekeeper and Signal protocol.
     Close the terminal window to resume managed execution.
     [r] Resume  (required if using Windows Terminal)
  ```
- **Doctor Terminal Host Detection**:
  On first startup when `ui.session_terminal` is absent from `config.yaml`, Doctor probes for available terminal hosts in priority order: `wt.exe` → `pwsh.exe` → `powershell.exe` → `cmd.exe`. It presents the detected list, prompts the user to select one, and writes the choice to `config.yaml`. This check is skipped on all subsequent startups when `ui.session_terminal` is already set. Doctor fails with a clear error if no terminal host can be detected (unexpected on Windows).
- **Crash Recovery with TUI Open**:
  On startup, if `state.json` contains `tui_open: true`, the Runner logs a warning: `"Runner exited while TUI session was open (session: <tui_session_id>). TUI may still be running. Resuming managed execution."` and clears both `tui_open` and `tui_session_id` before proceeding with normal crash recovery.

## UI Contract

This section defines the exact rendered formats that implementing code must produce. These are port-boundary contracts, not style suggestions — tests assert against them. For all `state.json` field names referenced below, the authoritative schema is in **Implementation Decisions → State Schema** above.

### Top Panel (6 fixed rows)

Verbatim example:

```
ticket  T042 · status  WORKING  · attempt  2 / 3
tokens  [████████░░] 118,200 / 150,000 (79%)
presence  nearby  · session  9f4a2c1e
branch  agent/ticket-runner  · queue  T042 (2 remaining)
────────────────────────────────────────────────────────────
[p] pause  [m] toggle mode  [q] quit  [o] open TUI
```

Rules:
- Row 1: `ticket  {active_ticket_id} · status  {status} · attempt  {verification_attempts} / 3`
- Row 2: `tokens  [{bar}] {tokens.current:,} / 150,000 ({pct}%)`
- Row 3: `presence  {presence_mode} · session  {opencode_session_id | "none"}`
- Row 4: `branch  {branch} · queue  {active_ticket_id} ({n} remaining)` — or `queue  empty` when queue is exhausted
- Row 5: Rich horizontal rule (`─` characters, full panel width)
- Row 6: hotkey legend (see **Hotkey Legend States** below)

The top panel is implemented as a `rich.layout.Layout` split: top panel is a fixed-height `Panel` (6 rows + borders); bottom panel fills the remaining height with the ring buffer.

### Token Bar Format

Rule: 10 characters wide. Fill character `█`, empty character `░`.

| Block index | Threshold | Rich colour |
|---|---|---|
| 1–8 | always filled when `current` ≥ that tenth | `green` |
| 9 | filled when `current` ≥ 120,000 | `yellow` |
| 10 | filled when `current` ≥ 135,000 | `red` |

Percentage: `round(tokens.current / 150_000 * 100)`. Bar is recalculated and the `Live` display refreshed on every state write.

Verbatim examples:
```
[██████████]  150,000 / 150,000 (100%)   ← fully red at ceiling
[████████░░]  118,200 / 150,000  (79%)   ← normal running
[████░░░░░░]   60,000 / 150,000  (40%)   ← early session
```

### Ring-Buffer Line Format

Verbatim example:
```
13:04:03 [worker] Tool: Read CONTEXT.md
13:04:15 [worker] Tool: Edit src/runner/presence_coordinator.py
13:07:44 [gate  ] Gatekeeper: running pytest tests/ ...
13:07:50 [runner] Authoring commit: feat(queue): defer clean-slate prompt
```

Rules:
- Template: `{HH:MM:SS} [{source:<6}] {message}` — source label left-padded to 6 characters
- `source` is exactly one of: `runner`, `worker`, `gate`
- Maximum 15 entries at any time; when a 16th arrives, the oldest is evicted (FIFO ring)
- Newest entry always at the bottom; display order is chronological top-to-bottom
- No entry is ever edited after insertion; only evicted

### Hotkey Legend States

The hotkey legend (row 6 of the top panel) has exactly four states, each rendered as plain text:

| State | Exact rendered text |
|---|---|
| Normal | `[p] pause  [m] toggle mode  [q] quit  [o] open TUI` |
| Confirm-pending (after `[o]`) | `Open TUI? [y] confirm / [n] cancel` |
| TUI queued (session run active, confirmed) | `[p] pause  [m] toggle mode  [q] quit  [o] pending…` |
| TUI open | `[r] Resume  (all other keys suspended)` |

Transitions: Normal → Confirm-pending on `[o]`; Confirm-pending → Normal on `[n]`; Confirm-pending → TUI queued (if session active) or TUI open (if at signal boundary) on `[y]`; TUI open → Normal on `[r]` or process exit.

### TUI Warning Panel (exact copy)

When `tui_open: true`, the normal dashboard is replaced entirely by this panel. No other panel is visible.

```
⚠  OpenCode TUI open — Runner is paused & blind
   Execution is paused: no Gatekeeper, no Circuit Breaker, no token tracking.
   Tokens consumed in TUI are NOT tracked against the 135k handoff budget.
   Work done in TUI bypasses the Gatekeeper and Signal protocol.
   Close the terminal window to resume managed execution.
   [r] Resume  (required if using Windows Terminal)
```

Rule: the `⚠` and the first line are rendered in `bold yellow`; the four body lines in `dim white`; the `[r] Resume` line in `bold green`.

### Completion Banner (terminate policy only)

Rendered only when `queue_completion_policy = "terminate"` and the queue is exhausted. Not rendered in `standby` mode.

```
╔══════════════════════════════════════════════════╗
║  🎉  Queue complete! All tickets committed.      ║
║  {n} tickets  ·  0 failed  ·  ~{k}k tokens      ║
╚══════════════════════════════════════════════════╝
```

Rules:
- `{n}` = count of tickets committed in this run
- `{k}` = total tokens across all sessions, rounded to nearest thousand
- Rendered in `bold green` border and text
- Displayed for 2 seconds, then runner exits with code 0

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that state transitions correctly update `state.json` contents on disk, that crash recovery properly detects uncommitted changes and resumes the recorded ticket, and that hotkeys invoke pause/mode-toggle/quit commands. Tests do not verify individual Rich widget rendering coordinates.
- **Modules Tested**: State persistence manager, crash recovery orchestrator, terminal UI coordinator, keyboard input dispatcher, and TUI session lifecycle coordinator.
- **Seams and Test Doubles**: Tests operate on temporary disk directories using fake input streams and headless Rich consoles to verify layout structure and state mutation without requiring physical terminal windows.
- **TUI Session State Machine Tests**: The `CONFIRM_TUI_OPEN` modal state transitions are tested in isolation as a pure state machine unit test: verify that `[o]` sets the confirm-pending flag, `[y]` advances to queued/open, `[n]` cancels and restores the normal hotkey legend, and a mid-run `[o]+[y]` queues the intent rather than opening immediately.
- **TUI Session Integration Tests**: `FakeTerminalDisplay` is extended with a pre-loaded key sequence (e.g. `[o]`, `[y]`) and a `FakeCommandRunner` records the subprocess spawn call. Tests assert that the correct terminal host command is spawned with the expected `--session <id>` argument, that `state.json` is updated to `tui_open: true` before spawn and cleared after, and that the resume `--auto` prompt is injected into the next Session Run.
- **Doctor Terminal Detection Tests**: Tests stub filesystem probes for each terminal host binary and verify that the Doctor writes the user-selected choice to `config.yaml` exactly once, and skips detection on subsequent runs where `ui.session_terminal` is already present.

## Out of Scope

- Remote web dashboard or browser-based UI.
- Mouse click navigation or scrollbar dragging inside the terminal.
- Replaying entire multi-hour visual terminal sessions from recorded logs.

## Further Notes

- Atomic state writes paired with git status checks ensure that no power outage or killed terminal window can corrupt repository state or force manual reconstruction of ticket progress.
