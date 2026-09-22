"""DiscordGateway port protocol for Discord API operations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from runner.domain.exceptions import DiscordGatewayError

__all__ = ["DiscordGateway", "DiscordGatewayError"]


@runtime_checkable
class DiscordGateway(Protocol):
    """Abstract protocol for Discord messaging and thread management seams."""

    async def post_message(
        self,
        channel_or_thread_id: str,
        content: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> str:
        """Post a message to a channel or thread.

        Args:
            channel_or_thread_id: Target snowflake ID for the channel or thread.
            content: Text body of the message.
            embed: Optional Discord embed structure as a plain dict.

        Returns:
            The created message snowflake ID.

        Raises:
            DiscordGatewayError: If the remote operation fails.
        """
        ...

    async def edit_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
        content: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> None:
        """Edit an existing message in-place.

        Args:
            channel_or_thread_id: Snowflake ID of the containing channel or thread.
            message_id: Snowflake ID of the message to update.
            content: New text body for the message.
            embed: Optional Discord embed structure as a plain dict.

        Raises:
            DiscordGatewayError: If the remote operation fails.
        """
        ...

    async def pin_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
    ) -> None:
        """Pin a message to a channel or thread.

        Args:
            channel_or_thread_id: Snowflake ID of the containing channel or thread.
            message_id: Snowflake ID of the message to pin.

        Raises:
            DiscordGatewayError: If the remote operation fails.
        """
        ...

    async def create_thread(
        self,
        channel_id: str,
        name: str,
        starter_message: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Post a starter message in a channel and create a public thread from it.

        Args:
            channel_id: Parent channel snowflake ID.
            name: Title/name of the thread.
            starter_message: Initial message text announcing the thread.
            embed: Optional Discord embed structure as a plain dict.

        Returns:
            A tuple of (thread_id, starter_message_id) both as snowflake strings.

        Raises:
            DiscordGatewayError: If the remote operation fails.
        """
        ...

    async def edit_thread(
        self,
        thread_id: str,
        *,
        archived: bool = False,
        locked: bool = False,
    ) -> None:
        """Update a thread's archived or locked state.

        Args:
            thread_id: Snowflake ID of the thread.
            archived: Whether to archive the thread.
            locked: Whether to lock the thread against further replies.

        Raises:
            DiscordGatewayError: If the remote operation fails.
        """
        ...

    async def archive_thread(
        self,
        thread_id: str,
    ) -> None:
        """Convenience helper to archive and lock a thread in a single operation.

        Args:
            thread_id: Snowflake ID of the thread.

        Raises:
            DiscordGatewayError: If the remote operation fails.
        """
        ...
