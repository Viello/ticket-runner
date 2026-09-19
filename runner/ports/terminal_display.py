"""TerminalDisplay port protocol and UiEventSink telemetry sink (T057)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runner.domain.state import RunnerState


@runtime_checkable
class UiEventSink(Protocol):
    """Abstract telemetry event sink for runner, worker, and gatekeeper logs."""

    def emit(self, source: str, message: str) -> None:
        """Emit a telemetry line to the sink.

        Args:
            source: Event producer, strictly one of: 'runner', 'worker', 'gate'.
            message: Telemetry content.

        Raises:
            ValueError: If source is not one of ('runner', 'worker', 'gate').
        """
        ...


@runtime_checkable
class TerminalDisplay(UiEventSink, Protocol):
    """Abstract protocol for terminal dashboard display."""

    def update_state(self, state: RunnerState, queue_remaining: int) -> None:
        """Update active runner state and remaining tickets count.

        Args:
            state: Current authoritative RunnerState entity.
            queue_remaining: Number of pending tickets remaining in the queue.
        """
        ...

    def emit(self, source: str, message: str) -> None:
        """Emit a telemetry event into the rolling ring buffer.

        Args:
            source: Event producer, strictly one of: 'runner', 'worker', 'gate'.
            message: Telemetry content.
        """
        ...

    def start(self) -> None:
        """Start the interactive terminal display."""
        ...

    def stop(self) -> None:
        """Stop and tear down the interactive terminal display."""
        ...

    def refresh(self) -> None:
        """Force a visual refresh of the terminal dashboard."""
        ...
