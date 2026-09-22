"""Discord client lifecycle module (connect, guild sync, teardown) (T073, Spec 05a)."""

from __future__ import annotations

import asyncio
import os
from typing import Any
import discord
from discord import app_commands

from runner.adapters.discord.commands import register_commands
from runner.adapters.discord.thread_listener import process_thread_reply
from runner.domain.config import DiscordConfig, RunnerConfig
from runner.domain.exceptions import DiscordGatewayError
from runner.ports.signal_repository import SignalRepository
from runner.ports.state_store import StateStore


class DiscordClient:
    """Manages the discord.py Client, CommandTree, and connection lifecycle."""

    def __init__(
        self,
        config: RunnerConfig | DiscordConfig | None = None,
        client: discord.Client | None = None,
        tree: app_commands.CommandTree | None = None,
        state_store: StateStore | None = None,
        signal_repository: SignalRepository | None = None,
    ) -> None:
        if config is not None:
            self.config: DiscordConfig = (
                config.discord if isinstance(config, RunnerConfig) else config
            )
        else:
            self.config = DiscordConfig()

        if client is not None:
            self.client = client
        else:
            intents = discord.Intents.default()
            intents.message_content = True
            self.client = discord.Client(intents=intents)

        self.tree = tree if tree is not None else app_commands.CommandTree(self.client)
        self.state_store = state_store
        self.signal_repository = signal_repository
        self.ready_event = asyncio.Event()

        # Wire lifecycle and message event handlers
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

        # Register slash commands on the command tree
        register_commands(self.tree, self.state_store)

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord messages by delegating to thread reply listener."""
        sig_repo = self.signal_repository
        if sig_repo is None:
            try:
                from runner.domain.runtime_paths import RuntimePaths
                from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository

                sig_repo = FilesystemSignalRepository(RuntimePaths.default())
            except Exception:
                sig_repo = None

        if sig_repo is not None:
            await process_thread_reply(message, sig_repo, self.config)

    async def on_ready(self) -> None:
        """Handle Discord gateway on_ready event.

        1. Fetches the channel object from config.discord.channel_id.
        2. Resolves guild_id (config.discord.guild_id or channel.guild.id).
        3. Calls tree.sync(guild=discord.Object(id=guild_id)).
        4. Sets ready_event.
        """
        channel: Any | None = None
        if self.config.channel_id:
            try:
                channel_id_int = int(self.config.channel_id)
            except (ValueError, TypeError) as exc:
                raise DiscordGatewayError(
                    f"Invalid channel_id in configuration: {self.config.channel_id!r}"
                ) from exc

            try:
                if hasattr(self.client, "fetch_channel"):
                    channel = await self.client.fetch_channel(channel_id_int)
                elif hasattr(self.client, "get_channel"):
                    channel = self.client.get_channel(channel_id_int)
            except discord.DiscordException as exc:
                raise DiscordGatewayError(
                    f"Failed to fetch channel {self.config.channel_id}: {exc}"
                ) from exc
            except Exception as exc:
                raise DiscordGatewayError(
                    f"Failed to fetch channel {self.config.channel_id}: {exc}"
                ) from exc

        # Step 2: resolve guild_id
        guild_id: int | None = None
        if self.config.guild_id:
            try:
                guild_id = int(self.config.guild_id)
            except (ValueError, TypeError) as exc:
                raise DiscordGatewayError(
                    f"Invalid guild_id in configuration: {self.config.guild_id!r}"
                ) from exc
        elif channel is not None and getattr(channel, "guild", None) is not None:
            try:
                guild_id = int(channel.guild.id)
            except (ValueError, TypeError, AttributeError) as exc:
                raise DiscordGatewayError(
                    f"Invalid guild ID retrieved from channel: {channel.guild}"
                ) from exc

        if guild_id is None:
            raise DiscordGatewayError(
                "Cannot resolve guild ID: config.guild_id is empty and channel guild is unavailable."
            )

        # Step 3: sync command tree to guild
        try:
            guild_obj = discord.Object(id=guild_id)
            await self.tree.sync(guild=guild_obj)
        except discord.DiscordException as exc:
            raise DiscordGatewayError(
                f"Failed to sync command tree to guild {guild_id}: {exc}"
            ) from exc
        except Exception as exc:
            raise DiscordGatewayError(
                f"Failed to sync command tree to guild {guild_id}: {exc}"
            ) from exc

        # Step 4: signal readiness
        self.ready_event.set()

    async def start(self, token: str | None = None) -> None:
        """Start the Discord client connection.

        Security: token is read from os.environ[config.token_env] when not explicitly passed,
        and is never stored on self or logged.
        """
        resolved_token: str
        if token is not None:
            resolved_token = token
        else:
            env_var = self.config.token_env
            val = os.environ.get(env_var, "").strip()
            if not val:
                raise DiscordGatewayError(
                    f"Missing or empty bot token in environment variable '{env_var}'"
                )
            resolved_token = val

        await self.client.start(resolved_token)

    async def close(self) -> None:
        """Close the Discord client connection with a 2-second timeout."""
        try:
            await asyncio.wait_for(self.client.close(), timeout=2.0)
        except (asyncio.TimeoutError, TimeoutError):
            pass
        finally:
            self.ready_event.clear()


_default_client: DiscordClient | None = None


def get_default_client() -> DiscordClient:
    """Return the active default DiscordClient instance or create a fallback."""
    global _default_client
    if _default_client is None:
        _default_client = DiscordClient()
    return _default_client


def init_client(
    config: RunnerConfig | DiscordConfig,
    client: discord.Client | None = None,
    tree: app_commands.CommandTree | None = None,
    state_store: StateStore | None = None,
    signal_repository: SignalRepository | None = None,
) -> DiscordClient:
    """Initialize and set the global default DiscordClient instance."""
    global _default_client
    _default_client = DiscordClient(
        config=config,
        client=client,
        tree=tree,
        state_store=state_store,
        signal_repository=signal_repository,
    )
    return _default_client


def __getattr__(name: str) -> Any:
    """Dynamic attribute proxy for module-level client, tree, and ready_event."""
    dc = get_default_client()
    if name == "client":
        return dc.client
    if name == "tree":
        return dc.tree
    if name == "ready_event":
        return dc.ready_event
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


async def start(token: str | None = None) -> None:
    """Module-level convenience delegating to default client start."""
    await get_default_client().start(token)


async def close() -> None:
    """Module-level convenience delegating to default client close."""
    await get_default_client().close()


__all__ = [
    "DiscordClient",
    "init_client",
    "get_default_client",
    "start",
    "close",
    "client",
    "tree",
    "ready_event",
]
