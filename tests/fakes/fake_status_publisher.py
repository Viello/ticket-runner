"""In-memory FakeStatusPublisher test double for StatusPublisher port (T067)."""

from __future__ import annotations

from runner.domain.status_event import StatusEvent
from runner.ports.status_publisher import StatusPublisher


class FakeStatusPublisher(StatusPublisher):
    """In-memory test double conforming to StatusPublisher."""

    def __init__(self) -> None:
        self.events: list[StatusEvent] = []

    def publish(self, event: StatusEvent) -> None:
        """Record the event in memory."""
        self.events.append(event)

    @property
    def last_event(self) -> StatusEvent | None:
        """Return the most recently published event, or None."""
        return self.events[-1] if self.events else None
