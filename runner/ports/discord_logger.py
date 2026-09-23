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

    async def post_status_card(
        self,
        ticket: Any,
        thread_id: str,
    ) -> str:
        """Post the initial pinned Status Card embed in a ticket thread.

        Args:
            ticket: Ticket entity or ticket-like mapping.
            thread_id: Target thread snowflake ID.

        Returns:
            Created status card message ID.
        """
        ...

    async def update_status_card(
        self,
        thread_id: str,
        message_id: str,
        *,
        status: str,
        attempt: int | str = 1,
        tokens_current: int = 0,
        started_at: str = "",
    ) -> None:
        """Update an existing Status Card message in-place with current execution state.

        Args:
            thread_id: Target thread snowflake ID.
            message_id: Status card message snowflake ID.
            status: Current execution phase label.
            attempt: Current attempt count (or formatted attempt string).
            tokens_current: Current consumed token count.
            started_at: Ticket start timestamp string (HH:MM UTC).
        """
        ...

    async def start_live_digest(
        self,
        thread_id: str,
        initial_content: str = "",
    ) -> str:
        """Post the initial plain-text message for a rolling Live Digest.

        Args:
            thread_id: Target thread snowflake ID.
            initial_content: Optional starter text.

        Returns:
            Created live digest message ID.
        """
        ...

    async def update_live_digest(
        self,
        content_chunk: str = "",
        thread_id: str | None = None,
    ) -> None:
        """Append to rolling 500-char window and edit message subject to 5s rate-limit floor.

        Args:
            content_chunk: New chunk of LLM output text.
            thread_id: Optional thread ID (defaults to active live digest thread).
        """
        ...

    async def finish_live_digest(
        self,
        thread_id: str | None = None,
    ) -> None:
        """Fire a final edit appending '\\n[done]' and stop further digest edits.

        Args:
            thread_id: Optional thread ID (defaults to active live digest thread).
        """
        ...
