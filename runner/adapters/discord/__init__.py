"""Discord remote notification adapters."""

from runner.adapters.discord import client, commands, logger, thread_listener
from runner.adapters.discord.client import DiscordClient
from runner.adapters.discord.commands import register_commands
from runner.adapters.discord.gateway import DiscordPyGateway
from runner.adapters.discord.logger import (
    COLOR_BLURPLE,
    COLOR_GREEN,
    COLOR_RED,
    COLOR_YELLOW,
    DiscordLoggerImpl,
    chunk_payload,
    format_chunks,
    split_chunks,
)
from runner.adapters.discord.thread_listener import process_thread_reply

__all__ = [
    "COLOR_BLURPLE",
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "DiscordClient",
    "DiscordLoggerImpl",
    "DiscordPyGateway",
    "chunk_payload",
    "client",
    "commands",
    "format_chunks",
    "logger",
    "process_thread_reply",
    "register_commands",
    "split_chunks",
    "thread_listener",
]
