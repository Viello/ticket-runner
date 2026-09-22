"""DiscordPyGateway adapter implementing DiscordGateway using discord.py (T072)."""

from __future__ import annotations

from typing import Any
import discord

from runner.domain.exceptions import DiscordGatewayError


class DiscordPyGateway:
    """Production gateway adapter wrapping a running discord.py Client."""

    def __init__(self, client: discord.Client) -> None:
        self._client = client

    async def _resolve_channel(self, channel_or_thread_id: str) -> Any:
        try:
            channel_id_int = int(channel_or_thread_id)
        except (ValueError, TypeError) as exc:
            raise DiscordGatewayError(
                f"Invalid channel or thread ID: {channel_or_thread_id!r}"
            ) from exc

        try:
            channel = self._client.get_channel(channel_id_int)
            if channel is None:
                channel = await self._client.fetch_channel(channel_id_int)
        except discord.DiscordException as exc:
            raise DiscordGatewayError(
                f"Failed to resolve channel or thread {channel_or_thread_id}: {exc}"
            ) from exc
        except Exception as exc:
            raise DiscordGatewayError(
                f"Failed to resolve channel or thread {channel_or_thread_id}: {exc}"
            ) from exc

        if channel is None:
            raise DiscordGatewayError(
                f"Channel or thread not found: {channel_or_thread_id}"
            )
        return channel

    async def _resolve_message(self, channel: Any, message_id: str) -> Any:
        try:
            msg_id_int = int(message_id)
        except (ValueError, TypeError) as exc:
            raise DiscordGatewayError(f"Invalid message ID: {message_id!r}") from exc

        try:
            if hasattr(channel, "fetch_message"):
                return await channel.fetch_message(msg_id_int)
            if hasattr(channel, "get_partial_message"):
                return channel.get_partial_message(msg_id_int)
            raise DiscordGatewayError(f"Channel cannot retrieve messages: {channel}")
        except discord.DiscordException as exc:
            raise DiscordGatewayError(
                f"Failed to fetch message {message_id}: {exc}"
            ) from exc
        except Exception as exc:
            raise DiscordGatewayError(
                f"Failed to fetch message {message_id}: {exc}"
            ) from exc

    def _to_discord_embed(self, embed: dict[str, Any] | None) -> discord.Embed | None:
        if embed is None:
            return None
        try:
            return discord.Embed.from_dict(embed)
        except Exception as exc:
            raise DiscordGatewayError(f"Failed to construct Discord embed: {exc}") from exc

    async def post_message(
        self,
        channel_or_thread_id: str,
        content: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> str:
        """Post a message to a channel or thread."""
        channel = await self._resolve_channel(channel_or_thread_id)
        send_kwargs: dict[str, Any] = {"content": content}
        if embed is not None:
            send_kwargs["embed"] = self._to_discord_embed(embed)

        try:
            msg = await channel.send(**send_kwargs)
            return str(msg.id)
        except discord.DiscordException as exc:
            raise DiscordGatewayError(f"Failed to post message: {exc}") from exc
        except Exception as exc:
            raise DiscordGatewayError(f"Failed to post message: {exc}") from exc

    async def edit_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
        content: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> None:
        """Edit an existing message in-place."""
        channel = await self._resolve_channel(channel_or_thread_id)
        message = await self._resolve_message(channel, message_id)
        edit_kwargs: dict[str, Any] = {"content": content}
        if embed is not None:
            edit_kwargs["embed"] = self._to_discord_embed(embed)

        try:
            await message.edit(**edit_kwargs)
        except discord.DiscordException as exc:
            raise DiscordGatewayError(f"Failed to edit message {message_id}: {exc}") from exc
        except Exception as exc:
            raise DiscordGatewayError(f"Failed to edit message {message_id}: {exc}") from exc

    async def pin_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
    ) -> None:
        """Pin a message to a channel or thread."""
        channel = await self._resolve_channel(channel_or_thread_id)
        message = await self._resolve_message(channel, message_id)
        try:
            await message.pin()
        except discord.DiscordException as exc:
            raise DiscordGatewayError(f"Failed to pin message {message_id}: {exc}") from exc
        except Exception as exc:
            raise DiscordGatewayError(f"Failed to pin message {message_id}: {exc}") from exc

    async def create_thread(
        self,
        channel_id: str,
        name: str,
        starter_message: str,
        *,
        embed: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Post a starter message in a channel and create a public thread from it."""
        channel = await self._resolve_channel(channel_id)
        send_kwargs: dict[str, Any] = {"content": starter_message}
        if embed is not None:
            send_kwargs["embed"] = self._to_discord_embed(embed)

        try:
            msg = await channel.send(**send_kwargs)
        except discord.DiscordException as exc:
            raise DiscordGatewayError(
                f"Failed to post starter message for thread {name!r}: {exc}"
            ) from exc
        except Exception as exc:
            raise DiscordGatewayError(
                f"Failed to post starter message for thread {name!r}: {exc}"
            ) from exc

        try:
            thread = await msg.create_thread(name=name)
            return (str(thread.id), str(msg.id))
        except discord.DiscordException as exc:
            raise DiscordGatewayError(
                f"Failed to create thread {name!r} from starter message: {exc}"
            ) from exc
        except Exception as exc:
            raise DiscordGatewayError(
                f"Failed to create thread {name!r} from starter message: {exc}"
            ) from exc

    async def edit_thread(
        self,
        thread_id: str,
        *,
        archived: bool = False,
        locked: bool = False,
    ) -> None:
        """Update a thread's archived or locked state."""
        thread = await self._resolve_channel(thread_id)
        try:
            await thread.edit(archived=archived, locked=locked)
        except discord.DiscordException as exc:
            raise DiscordGatewayError(
                f"Failed to edit thread {thread_id}: {exc}"
            ) from exc
        except Exception as exc:
            raise DiscordGatewayError(
                f"Failed to edit thread {thread_id}: {exc}"
            ) from exc

    async def archive_thread(
        self,
        thread_id: str,
    ) -> None:
        """Convenience helper to archive and lock a thread in a single operation."""
        await self.edit_thread(thread_id, archived=True, locked=True)

    async def delete_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
    ) -> None:
        """Delete an existing message from a channel or thread."""
        channel = await self._resolve_channel(channel_or_thread_id)
        message = await self._resolve_message(channel, message_id)
        try:
            await message.delete()
        except discord.DiscordException as exc:
            raise DiscordGatewayError(f"Failed to delete message {message_id}: {exc}") from exc
        except Exception as exc:
            raise DiscordGatewayError(f"Failed to delete message {message_id}: {exc}") from exc

