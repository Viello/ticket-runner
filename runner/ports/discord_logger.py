"""DiscordLogger port protocol for structured logging and remote notification seams (T082)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["DiscordLogger"]


@runtime_checkable
class DiscordLogger(Protocol):
    """Abstract protocol for severity routing, chunking, and Discord dispatch."""

    async def log(
        self,
        event_type: str,
        payload: str,
        thread_id: str,
        presence_mode: str = "nearby",
        *,
        severity: str | None = None,
    ) -> list[str]:
        """Log a structured event to a thread subject to severity routing and chunking.

        Args:
            event_type: Classification of the event (e.g. 'circuit_breaker_trip', 'phase_transition').
            payload: Event message text or diagnostic body.
            thread_id: Target thread snowflake ID.
            presence_mode: Current presence mode ('nearby' or 'away').
            severity: Optional explicit severity override ('critical' or 'routine').

        Returns:
            List of posted Discord message IDs (empty if suppressed).
        """
        ...

    async def post_embed(
        self,
        thread_id: str,
        embed_dict: dict[str, Any],
    ) -> list[str]:
        """Post a Discord embed dictionary subject to chunking and field limits.

        Args:
            thread_id: Target thread snowflake ID.
            embed_dict: Discord embed dictionary payload.

        Returns:
            List of posted Discord message IDs.
        """
        ...
