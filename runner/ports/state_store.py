"""StateStore port protocol for durable runner state documents."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


@runtime_checkable
class StateStore(Protocol):
    """Abstract protocol for reading and writing durable runner state documents."""

    def read(self) -> dict[str, Any] | None:
        """Read the persisted state document.

        Returns:
            The state document as a dictionary, or None if the state file does not exist.

        Raises:
            StateFormatError: If the state file exists but is malformed, not a JSON
                object, exceeds the maximum size, or cannot be safely decoded.
        """
        ...

    def write(self, document: Mapping[str, Any]) -> None:
        """Atomically persist the exact supplied document.

        Callers own any read-modify-write merge semantics.

        Args:
            document: Key-value mapping representing the state document to persist.

        Raises:
            OSError: If writing or atomic replacement fails.
        """
        ...
