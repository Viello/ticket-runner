"""RingBuffer domain entity providing a fixed-capacity telemetry log sink (T057)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from datetime import datetime
import time
from typing import Any, Callable

MAX_RING_BUFFER_ENTRIES: int = 15

VALID_RING_BUFFER_SOURCES: frozenset[str] = frozenset({"runner", "worker", "gate"})


class RingBuffer:
    """Fixed-capacity rolling telemetry ring buffer for terminal dashboard."""

    def __init__(
        self,
        max_entries: int = MAX_RING_BUFFER_ENTRIES,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._max_entries = max_entries
        self._clock = clock or datetime.now
        self._buffer: deque[str] = deque(maxlen=max_entries)

    @property
    def max_entries(self) -> int:
        """Maximum number of entries retained before FIFO eviction."""
        return self._max_entries

    @property
    def entries(self) -> tuple[str, ...]:
        """Chronological tuple of all formatted log entries in the buffer."""
        return tuple(self._buffer)

    @property
    def lines(self) -> tuple[str, ...]:
        """Alias to entries providing lines of text."""
        return tuple(self._buffer)

    def append(
        self,
        source: str,
        message: str,
        timestamp: datetime | str | None = None,
    ) -> str:
        """Format and append a new telemetry line to the buffer, evicting the oldest if full.

        Args:
            source: Event producer, strictly one of: 'runner', 'worker', 'gate'.
            message: Telemetry content.
            timestamp: Optional datetime or 'HH:MM:SS' string. Defaults to clock().

        Returns:
            The formatted line string.

        Raises:
            ValueError: If source is not one of ('runner', 'worker', 'gate').
        """
        if source not in VALID_RING_BUFFER_SOURCES:
            valid_list = ", ".join(sorted(VALID_RING_BUFFER_SOURCES))
            raise ValueError(
                f"Invalid source '{source}'. Must be strictly one of: {valid_list}"
            )

        if isinstance(timestamp, datetime):
            time_str = timestamp.strftime("%H:%M:%S")
        elif isinstance(timestamp, str) and timestamp.strip():
            time_str = timestamp.strip()
        else:
            time_str = self._clock().strftime("%H:%M:%S")

        formatted_line = f"{time_str} [{source:<6}] {message}"
        self._buffer.append(formatted_line)
        return formatted_line

    def clear(self) -> None:
        """Remove all entries from the buffer."""
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)

    def __iter__(self) -> Iterator[str]:
        return iter(self._buffer)

    def __getitem__(self, index: int) -> str:
        return self._buffer[index]
