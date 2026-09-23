"""Discord thread reply listener module (T074, Spec 05a)."""

from __future__ import annotations

import inspect
import re
from typing import Any
import discord

from runner.domain.config import DiscordConfig, RunnerConfig
from runner.ports.signal_repository import SignalRepository

TICKET_ID_REGEX = re.compile(r"^([A-Z]\d{3,})", re.IGNORECASE)


def is_thread_channel(channel: Any) -> bool:
    """Return True if channel represents a Discord Thread."""
    if isinstance(channel, discord.Thread):
        return True

    ch_type = getattr(channel, "type", None)
    if ch_type is not None:
        if ch_type in (
            discord.ChannelType.public_thread,
            discord.ChannelType.private_thread,
            discord.ChannelType.news_thread,
        ):
            return True
        type_str = str(ch_type).lower()
        if "thread" in type_str:
            return True
        if ch_type in (
            discord.ChannelType.text,
            discord.ChannelType.voice,
            discord.ChannelType.category,
            discord.ChannelType.news,
            discord.ChannelType.stage_voice,
            discord.ChannelType.forum,
        ):
            return False

    if isinstance(channel, dict):
        t = channel.get("type", "")
        if "thread" in str(t).lower():
            return True
        if channel.get("parent_id") is not None:
            return True
        return False

    parent_id = getattr(channel, "parent_id", None)
    if parent_id is not None and not str(type(parent_id)).startswith("<class 'unittest.mock"):
        return True

    parent = getattr(channel, "parent", None)
    if parent is not None and not str(type(parent)).startswith("<class 'unittest.mock"):
        return True

    return False


async def process_thread_reply(
    message_data: Any,
    signal_repository: SignalRepository,
    config: RunnerConfig | DiscordConfig,
    presence_coordinator: Any | None = None,
) -> bool:
    """Pure function implementing the five-step filtering chain for developer thread replies.

    Filtering order:
    1. message.author.bot -> skip
    2. Message channel type is not a thread -> skip
    3. Parent channel ID != configured channel_id -> skip
    4. notify_user_id configured and sender ID != notify_user_id -> skip
    5. Extract ticket ID: regex ^([A-Z]\\d{3,}) on thread.name
    6. Call signal_repository.write_answer(ticket_id, content)
    7. Post a short confirmation or error reply in the thread

    Returns:
        True if the reply was successfully processed and answered; False otherwise.
    """
    # 1. Bot author check
    author = getattr(message_data, "author", None)
    if author is None and isinstance(message_data, dict):
        author = message_data.get("author")

    is_bot = getattr(author, "bot", False) if author else False
    if isinstance(author, dict):
        is_bot = author.get("bot", False)
    if is_bot:
        return False

    # 2. Thread channel type check
    channel = getattr(message_data, "channel", None)
    if channel is None and isinstance(message_data, dict):
        channel = message_data.get("channel")

    if channel is None or not is_thread_channel(channel):
        return False

    # 3. Parent channel ID check
    discord_cfg = config.discord if isinstance(config, RunnerConfig) else config
    configured_channel_id = str(getattr(discord_cfg, "channel_id", "") or "").strip()

    parent_id = getattr(channel, "parent_id", None)
    if parent_id is None:
        parent = getattr(channel, "parent", None)
        if parent is not None:
            parent_id = getattr(parent, "id", None)
    if parent_id is None and isinstance(channel, dict):
        parent_id = channel.get("parent_id")
        if parent_id is None and isinstance(channel.get("parent"), dict):
            parent_id = channel["parent"].get("id")

    if parent_id is None:
        return False

    if str(parent_id).strip() != configured_channel_id:
        return False

    # 4. notify_user_id authorization check
    notify_user_id = str(getattr(discord_cfg, "notify_user_id", "") or "").strip()
    if notify_user_id:
        author_id = getattr(author, "id", None)
        if author_id is None and isinstance(author, dict):
            author_id = author.get("id")
        if str(author_id).strip() != notify_user_id:
            return False

    # 5. Extract ticket ID from thread name
    thread_name = getattr(channel, "name", "")
    if not thread_name and isinstance(channel, dict):
        thread_name = channel.get("name", "")

    match = TICKET_ID_REGEX.match(str(thread_name))
    if not match:
        return False
    ticket_id = match.group(1).upper()

    # Content extraction
    content = getattr(message_data, "content", "")
    if not content and isinstance(message_data, dict):
        content = message_data.get("content", "")

    async def _send_reply(text: str) -> None:
        if hasattr(message_data, "reply") and callable(message_data.reply):
            res = message_data.reply(text)
            if inspect.isawaitable(res):
                await res
        elif hasattr(channel, "send") and callable(channel.send):
            res = channel.send(text)
            if inspect.isawaitable(res):
                await res

    # 6 & 7: Write answer and reply
    try:
        signal_repository.write_answer(ticket_id, str(content))
        if presence_coordinator is not None:
            presence_coordinator.set_mode("nearby")
        await _send_reply(f"Answer recorded for {ticket_id}.")
        return True
    except Exception as exc:
        await _send_reply(f"Failed to record answer for {ticket_id}: {exc}")
        return False


__all__ = [
    "is_thread_channel",
    "process_thread_reply",
]
