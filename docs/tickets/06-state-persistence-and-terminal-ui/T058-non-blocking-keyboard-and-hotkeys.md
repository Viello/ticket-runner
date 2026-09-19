# T058 — Non-blocking Windows keyboard dispatcher and hotkey event loop
Status: pending
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: T057
Reasoning: medium

### Requirements
- Implement non-blocking Windows console keyboard poller in `runner/adapters/ui/keyboard.py`:
  - Schedule an async polling loop on the `asyncio` event loop running at 50ms intervals (`asyncio.sleep(0.05)`).
  - Use `msvcrt.kbhit()` and `msvcrt.getch()` on Windows to read keypresses without blocking concurrent async coroutines or subprocess streaming.
  - Provide an injectable key-reader seam (`Callable[[], str | None]`) for cross-platform headless testing and CI environments where `msvcrt` is absent.
- Implement hotkey action dispatching for core hotkeys:
  - `[p]`: Pause execution immediately. Calls `QueueOrchestrator.pause()`, setting `_is_paused = True` and releasing `.queue.lock` so external editors can modify `docs/tickets/`. Pressing `[p]` while paused unpauses and re-acquires the lock.
  - `[m]`: Toggle Presence Mode immediately between `"nearby"` and `"away"`. Updates `PresenceCoordinator`, persists `presence_mode` in `.agent/state.json`, and refreshes the terminal header row.
  - `[q]`: Trigger graceful shutdown. Signals `stop_event`, requests child subprocess termination via `WorkerSupervisor.request_kill(RunTerminationReason.KILLED_INTERRUPT)`, persists final state, and exits with code 130 or 0.
- Wire the keyboard listener into `run_start` in `ticket_runner.py` as a supervised background task.
- Jump-start:
  - Files to touch: `runner/adapters/ui/keyboard.py`, `runner/adapters/ui/__init__.py`, `ticket_runner.py`, `runner/application/queue_orchestrator.py`, `runner/application/presence_coordinator.py`, `tests/unit/adapters/test_keyboard.py`, `tests/unit/application/test_hotkey_dispatch.py`.
  - Seams: `msvcrt.kbhit`, `msvcrt.getch`, `QueueOrchestrator.pause()`, `PresenceCoordinator.toggle_mode()`.
  - Verification: `python -m pytest tests/unit/adapters/test_keyboard.py tests/unit/application/test_hotkey_dispatch.py`.

### Acceptance Criteria
- Keyboard poller runs asynchronously every 50ms without freezing the event loop or blocking subprocess streams.
- Pressing `[p]` immediately releases `.queue.lock` on disk and halts new ticket progression.
- Pressing `[m]` toggles presence mode between `nearby` and `away`, persists the new mode to `.agent/state.json`, and updates row 3 of the terminal display.
- Pressing `[q]` initiates clean shutdown, stops running subprocesses, writes state, and terminates.
- Non-Windows environments fall back cleanly without raising `ImportError` or `ModuleNotFoundError`.
- Tests verify each hotkey transition using synthetic key event streams.
- Full suite green: `python -m pytest`.

### Gotchas
- `msvcrt.getch()` yields raw bytes (e.g. `b'p'`); decode to string with `.decode("ascii", errors="ignore").lower()` to handle case insensitivity.
- On Windows, special keys (arrows, function keys) produce two bytes; discard the prefix byte (`0x00` or `0xE0`) and trailing byte cleanly.
- Ensure the async keyboard task is cancelled and awaited during runner cleanup to prevent "Task was destroyed but it is pending" warnings.
