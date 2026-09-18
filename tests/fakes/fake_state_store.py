"""In-memory fake implementation of StateStore for testing."""

from __future__ import annotations

from typing import Any, Mapping

from runner.ports.state_store import StateStore


class FakeStateStore:
    """In-memory test double conforming to StateStore."""

    def __init__(
        self,
        initial_state: Mapping[str, Any] | None = None,
        *,
        read_error: Exception | None = None,
        write_error: Exception | None = None,
    ) -> None:
        self._state: dict[str, Any] | None = dict(initial_state) if initial_state is not None else None
        self._read_error = read_error
        self._write_error = write_error
        self.write_calls: list[dict[str, Any]] = []

    def seed_state(self, state: Mapping[str, Any] | None) -> None:
        """Seed or clear the state document in memory."""
        self._state = dict(state) if state is not None else None

    def read(self) -> dict[str, Any] | None:
        """Return the current in-memory state document or raise the injected read error."""
        if self._read_error is not None:
            raise self._read_error
        if self._state is None:
            return None
        return dict(self._state)

    def write(self, document: Mapping[str, Any]) -> None:
        """Store the exact supplied document or raise the injected write error."""
        if self._write_error is not None:
            raise self._write_error
        doc_copy = dict(document)
        self.write_calls.append(doc_copy)
        self._state = doc_copy
