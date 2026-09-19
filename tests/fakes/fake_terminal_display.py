"""FakeTerminalDisplay test double implementing TerminalDisplay and UiEventSink (T057)."""

from __future__ import annotations

from runner.domain.ring_buffer import RingBuffer, VALID_RING_BUFFER_SOURCES
from runner.domain.state import RunnerState
from runner.ports.terminal_display import TerminalDisplay, UiEventSink


class FakeTerminalDisplay(TerminalDisplay):
    """Test double recording state updates and ring buffer lines for headless testing."""

    def __init__(self) -> None:
        self.snapshots: list[tuple[RunnerState, int]] = []
        self.events: list[tuple[str, str]] = []
        self.ring_buffer = RingBuffer()
        self.is_running: bool = False
        self.started: bool = False
        self.stopped: bool = False
        self.refresh_count: int = 0

    @property
    def current_state(self) -> RunnerState | None:
        """The most recently updated RunnerState."""
        return self.snapshots[-1][0] if self.snapshots else None

    @property
    def queue_remaining(self) -> int | None:
        """The most recently updated queue_remaining count."""
        return self.snapshots[-1][1] if self.snapshots else None

    @property
    def lines(self) -> tuple[str, ...]:
        """Current ring buffer lines."""
        return self.ring_buffer.lines

    def update_state(self, state: RunnerState, queue_remaining: int) -> None:
        """Record state snapshot."""
        self.snapshots.append((state, queue_remaining))

    def emit(self, source: str, message: str) -> None:
        """Record telemetry event and append to internal ring buffer."""
        if source not in VALID_RING_BUFFER_SOURCES:
            valid_list = ", ".join(sorted(VALID_RING_BUFFER_SOURCES))
            raise ValueError(
                f"Invalid source '{source}'. Must be strictly one of: {valid_list}"
            )
        self.events.append((source, message))
        self.ring_buffer.append(source, message)

    def start(self) -> None:
        """Mark display as started."""
        self.is_running = True
        self.started = True

    def stop(self) -> None:
        """Mark display as stopped."""
        self.is_running = False
        self.stopped = True

    def refresh(self) -> None:
        """Record refresh invocation."""
        self.refresh_count += 1
