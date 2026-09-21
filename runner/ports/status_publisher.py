"""StatusPublisher port protocol for publishing StatusEvent notifications (T067)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from runner.domain.status_event import StatusEvent


@runtime_checkable
class StatusPublisher(Protocol):
    """Abstract port protocol for status event publishing."""

    def publish(self, event: StatusEvent) -> None:
        """Publish a status event to external observers.

        Args:
            event: StatusEvent containing snapshot of runner execution state.
        """
        ...
