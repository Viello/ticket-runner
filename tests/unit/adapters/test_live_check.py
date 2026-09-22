"""Unit tests for check_live_discord_permissions helper (T076)."""

from __future__ import annotations

import asyncio
from typing import Any
import discord
import pytest

from runner.adapters.discord.live_check import check_live_discord_permissions
from runner.adapters.discord.smoke import REQUIRED_DISCORD_PERMISSIONS


class FakePermissions:
    def __init__(self, granted: set[str]) -> None:
        for attr in REQUIRED_DISCORD_PERMISSIONS.keys():
            setattr(self, attr, attr in granted)


class FakeMember:
    def __init__(self, id: int = 123) -> None:
        self.id = id


class FakeGuild:
    def __init__(self, me: FakeMember | None = None) -> None:
        self.me = me

    def get_member(self, user_id: int) -> FakeMember | None:
        return self.me


class FakeChannel:
    def __init__(self, permissions: set[str], guild: FakeGuild | None = None) -> None:
        self.guild = guild or FakeGuild(me=FakeMember())
        self._perms = permissions

    def permissions_for(self, member: Any) -> FakePermissions:
        return FakePermissions(self._perms)


class FakeDiscordClient:
    """Minimal test double for discord.Client."""

    def __init__(
        self,
        *,
        fail_start: Exception | None = None,
        channels: dict[int, Any] | None = None,
        start_delay: float = 0.0,
        fetch_delay: float = 0.0,
    ) -> None:
        self.fail_start = fail_start
        self.channels = channels or {}
        self.start_delay = start_delay
        self.fetch_delay = fetch_delay
        self.closed = False
        self.user = FakeMember(id=999)
        self._ready_event = asyncio.Event()

    async def start(self, token: str) -> None:
        if self.start_delay > 0:
            await asyncio.sleep(self.start_delay)
        if self.fail_start:
            raise self.fail_start
        self._ready_event.set()

    async def wait_until_ready(self) -> None:
        await self._ready_event.wait()

    def get_channel(self, channel_id: int) -> Any | None:
        return self.channels.get(channel_id)

    async def fetch_channel(self, channel_id: int) -> Any:
        if self.fetch_delay > 0:
            await asyncio.sleep(self.fetch_delay)
        if channel_id in self.channels:
            return self.channels[channel_id]

        class FakeResponse:
            status = 404
            reason = "Not Found"

        raise discord.errors.NotFound(FakeResponse(), "Channel not found")

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_live_check_success_all_permissions() -> None:
    """Live check succeeds when all 7 permissions are present in channel."""
    all_perms = set(REQUIRED_DISCORD_PERMISSIONS.keys())
    channel = FakeChannel(permissions=all_perms)
    client = FakeDiscordClient(channels={123456: channel})

    outcome = await check_live_discord_permissions(
        token="test-token",
        channel_id="123456",
        client_factory=lambda: client,
    )

    assert outcome.passed is True
    assert outcome.missing_permissions == []
    assert client.closed is True


@pytest.mark.anyio
async def test_live_check_missing_permissions() -> None:
    """Live check reports missing permissions when some are denied."""
    # Omit manage_messages and create_public_threads
    subset = set(REQUIRED_DISCORD_PERMISSIONS.keys()) - {
        "manage_messages",
        "create_public_threads",
    }
    channel = FakeChannel(permissions=subset)
    client = FakeDiscordClient(channels={123456: channel})

    outcome = await check_live_discord_permissions(
        token="test-token",
        channel_id="123456",
        client_factory=lambda: client,
    )

    assert outcome.passed is False
    assert "Manage Messages" in outcome.missing_permissions
    assert "Create Public Threads" in outcome.missing_permissions
    assert client.closed is True


@pytest.mark.anyio
async def test_live_check_authentication_failure() -> None:
    """Live check identifies authentication failure from client.start."""
    login_err = discord.errors.LoginFailure("Improper token has been passed.")
    client = FakeDiscordClient(fail_start=login_err)

    outcome = await check_live_discord_permissions(
        token="invalid-token",
        channel_id="123456",
        client_factory=lambda: client,
    )

    assert outcome.passed is False
    assert outcome.is_auth_error is True
    assert "Authentication failed" in (outcome.error_message or "")
    assert client.closed is True


@pytest.mark.anyio
async def test_live_check_timeout() -> None:
    """Live check reports timeout when connection or fetch exceeds timeout."""
    # Simulate hang on start
    client = FakeDiscordClient(start_delay=5.0)

    outcome = await check_live_discord_permissions(
        token="test-token",
        channel_id="123456",
        timeout=0.05,
        client_factory=lambda: client,
    )

    assert outcome.passed is False
    assert outcome.is_timeout is True
    assert client.closed is True


@pytest.mark.anyio
async def test_live_check_channel_not_found() -> None:
    """Live check reports error when channel is not found."""
    client = FakeDiscordClient(channels={})

    outcome = await check_live_discord_permissions(
        token="test-token",
        channel_id="999999",
        client_factory=lambda: client,
    )

    assert outcome.passed is False
    assert "not found" in (outcome.error_message or "").lower()
    assert client.closed is True
