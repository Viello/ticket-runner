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

## Implementation Decisions

- **State Schema (`.agent/state.json`)**:
  Stores `active_ticket_id` (string or null), `status` (`"IDLE"`, `"WORKING"`, `"GATEKEEPER"`, `"WAITING_FOR_USER"`, `"PAUSE_REQUESTED"`, `"CIRCUIT_BREAKER_TRIPPED"`), `opencode_session_id` (string or null), `presence_mode` (`"nearby"` | `"away"`), `verification_attempts` (integer), `tokens` object (`current` integer, `warning_sent` boolean), `branch` (string), `started_at` (ISO-8601), `last_checkpoint` (path or null), and `last_updated` (ISO-8601).
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

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that state transitions correctly update `state.json` contents on disk, that crash recovery properly detects uncommitted changes and resumes the recorded ticket, and that hotkeys invoke pause/mode-toggle/quit commands. Tests do not verify individual Rich widget rendering coordinates.
- **Modules Tested**: State persistence manager, crash recovery orchestrator, terminal UI coordinator, and keyboard input dispatcher.
- **Seams and Test Doubles**: Tests operate on temporary disk directories using fake input streams and headless Rich consoles to verify layout structure and state mutation without requiring physical terminal windows.

## Out of Scope

- Remote web dashboard or browser-based UI.
- Mouse click navigation or scrollbar dragging inside the terminal.
- Replaying entire multi-hour visual terminal sessions from recorded logs.

## Further Notes

- Atomic state writes paired with git status checks ensure that no power outage or killed terminal window can corrupt repository state or force manual reconstruction of ticket progress.
