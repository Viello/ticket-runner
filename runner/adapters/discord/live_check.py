"""Live Discord connectivity and permission verification helper (T076, Spec 05a)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable
import discord

from runner.adapters.discord.smoke import REQUIRED_DISCORD_PERMISSIONS, verify_channel_permissions


@dataclass(frozen=True)
class LivePermissionCheckOutcome:
    """Result of live Discord permission check."""

    passed: bool
    missing_permissions: list[str]
    error_message: str | None = None
    is_auth_error: bool = False
    is_timeout: bool = False


async def check_live_discord_permissions(
    token: str,
    channel_id: str,
    timeout: float = 10.0,
    client_factory: Callable[[], discord.Client] | None = None,
) -> LivePermissionCheckOutcome:
    """Open minimal discord.py connection, fetch channel, verify permissions, and close.

    Args:
        token: Discord bot authentication token.
        channel_id: Snowflake ID of the target channel.
        timeout: Timeout in seconds for fetch_channel and connection (default 10.0s).
        client_factory: Optional factory for discord.Client instance.

    Returns:
        LivePermissionCheckOutcome with status and details.
    """
    intents = discord.Intents.default()
    client = client_factory() if client_factory is not None else discord.Client(intents=intents)

    start_task = asyncio.create_task(client.start(token))
    try:
        ready_task = asyncio.create_task(client.wait_until_ready())
        done, pending = await asyncio.wait(
            [start_task, ready_task],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=timeout,
        )

        if not done:
            for t in pending:
                t.cancel()
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=[],
                error_message="Connection timed out connecting to Discord.",
                is_timeout=True,
            )

        if start_task in done:
            exc = start_task.exception()
            if exc is not None:
                if isinstance(exc, (discord.errors.LoginFailure, discord.errors.PrivilegedIntentsRequired)):
                    return LivePermissionCheckOutcome(
                        passed=False,
                        missing_permissions=[],
                        error_message=f"Authentication failed: {exc}",
                        is_auth_error=True,
                    )
                if isinstance(exc, discord.errors.HTTPException) and getattr(exc, "status", None) == 401:
                    return LivePermissionCheckOutcome(
                        passed=False,
                        missing_permissions=[],
                        error_message=f"Authentication failed: {exc}",
                        is_auth_error=True,
                    )
                return LivePermissionCheckOutcome(
                    passed=False,
                    missing_permissions=[],
                    error_message=f"Connection error: {exc}",
                )

        try:
            chan_int = int(channel_id)
        except (ValueError, TypeError):
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=[],
                error_message=f"Invalid channel ID: {channel_id!r}",
            )

        channel: Any = None
        try:
            channel = client.get_channel(chan_int)
            if channel is None:
                channel = await asyncio.wait_for(
                    client.fetch_channel(chan_int),
                    timeout=timeout,
                )
        except asyncio.TimeoutError:
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=[],
                error_message=f"Timed out fetching channel {channel_id}.",
                is_timeout=True,
            )
        except discord.errors.NotFound:
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=[],
                error_message=f"Channel {channel_id} not found.",
            )
        except discord.errors.Forbidden:
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=list(REQUIRED_DISCORD_PERMISSIONS.values()),
                error_message=f"Bot lacks permission to access channel {channel_id}.",
            )
        except Exception as exc:
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=[],
                error_message=f"Failed to fetch channel {channel_id}: {exc}",
            )

        if channel is None:
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=[],
                error_message=f"Channel {channel_id} not found.",
            )

        missing = await verify_channel_permissions(channel, client)
        if missing:
            return LivePermissionCheckOutcome(
                passed=False,
                missing_permissions=missing,
                error_message=f"Missing required permission(s): {', '.join(missing)}",
            )

        return LivePermissionCheckOutcome(
            passed=True,
            missing_permissions=[],
            error_message=None,
        )
    finally:
        await client.close()
        if not start_task.done():
            start_task.cancel()
            try:
                await start_task
            except (asyncio.CancelledError, Exception):
                pass
