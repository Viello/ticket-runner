# T057 — TerminalDisplay port, RingBuffer telemetry sink, and Rich Live dashboard layout
Status: completed
Completed: 2026-09-19T14:46:00Z
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: T053
Reasoning: medium

### Requirements
- Define `TerminalDisplay` port protocol and `UiEventSink` in `runner/ports/terminal_display.py`:
  - `update_state(state: RunnerState, queue_remaining: int) -> None`
  - `emit(source: str, message: str) -> None`: where `source` is strictly one of `"runner"`, `"worker"`, `"gate"`.
  - `start() -> None`, `stop() -> None`, `refresh() -> None`
- Implement `RingBuffer` domain entity in `runner/domain/ring_buffer.py`:
  - Maximum 15 entries; FIFO eviction when 16th entry is appended.
  - Entry format: `{HH:MM:SS} [{source:<6}] {message}` (source left-padded to 6 chars, e.g. `[worker]`, `[gate  ]`, `[runner]`).
  - Strict chronological order (oldest top, newest bottom); no in-place edits.
- Implement token progress bar calculation:
  - 10 characters: fill `█`, empty `░`.
  - Percentage: `round(tokens.current / 150_000 * 100)`.
  - Blocks 1–8: `green` (when current >= that tenth).
  - Block 9: `yellow` (when current >= 120,000).
  - Block 10: `red` (when current >= 135,000).
- Implement `RichTerminalDisplay` adapter in `runner/adapters/ui/terminal.py` using `rich.live.Live` and `rich.layout.Layout`:
  - Fixed top panel (6 rows):
    - Row 1: `ticket  {active_ticket_id} · status  {status} · attempt  {verification_attempts} / 3`
    - Row 2: `tokens  [{bar}] {tokens.current:,} / 150,000 ({pct}%)`
    - Row 3: `presence  {presence_mode} · session  {opencode_session_id | "none"}`
    - Row 4: `branch  {branch} · queue  {active_ticket_id} ({n} remaining)` or `queue  empty`
    - Row 5: Rich horizontal rule (`─` characters, full width)
    - Row 6: Hotkey legend (Normal state: `[p] pause  [m] toggle mode  [q] quit  [o] open TUI`)
  - Bottom panel: rolling ring buffer lines.
- Implement `tests/fakes/fake_terminal_display.py` for testing.
- Connect `UiEventSink` to `WorkerSupervisor` (worker tool calls), `Gatekeeper` (verification test/build outputs), and `QueueOrchestrator` (commit and lifecycle events).
- Jump-start:
  - Files to touch: `runner/ports/terminal_display.py`, `runner/ports/__init__.py`, `runner/domain/ring_buffer.py`, `runner/domain/__init__.py`, `runner/adapters/ui/terminal.py`, `tests/fakes/fake_terminal_display.py`, `tests/unit/adapters/test_terminal_display.py`, `tests/unit/domain/test_ring_buffer.py`.
  - Seams: `runner/application/worker_supervisor.py`, `runner/application/gatekeeper.py`, `runner/application/queue_orchestrator.py`.
  - Anchor patterns: compare with `runner/ports/state_store.py`.
  - Verification: `python -m pytest tests/unit/domain/test_ring_buffer.py tests/unit/adapters/test_terminal_display.py`.

### Acceptance Criteria
- `RingBuffer` enforces the 15-line capacity, correct 6-character left padding for sources, and FIFO eviction.
- Token bar formats 10 characters with color thresholds strictly matching the contract (yellow at 120k, red at 135k).
- Top panel renders all 6 rows matching the verbatim text format when tested with a headless `rich.console.Console`.
- `UiEventSink` receives tool events from worker, gatekeeper command runs, and runner lifecycle commits without crashing.
- `FakeTerminalDisplay` records state snapshots and ring buffer lines for headless testing.
- Full suite green: `python -m pytest`.

### Gotchas
- The top panel must be fixed height (Panel height=8 with borders, or Layout size=8) to prevent visual jumping during live updates.
- In headless test environments, pass `console=Console(record=True, width=80)` to assert exact output strings without a physical TTY.
- Ensure token percentages do not exceed 100% or produce divide-by-zero errors when `tokens.current` is 0.
