"""Unit tests for Discord bot smoke verification sequence and permission checks (T075)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from runner.adapters.discord.smoke import (
    REQUIRED_DISCORD_PERMISSIONS,
    run_smoke,
    verify_channel_permissions,
)
from runner.domain.exceptions import DiscordGatewayError
from tests.fakes.fake_discord_gateway import FakeDiscordGateway


@pytest.mark.anyio
async def test_run_smoke_sequence_and_cleanup() -> None:
    """run_smoke executes the exact 5-step sequence and deletes the starter message."""
    fake = FakeDiscordGateway()
    channel_id = "1122334455"

    await run_smoke(fake, channel_id)

    assert len(fake.calls) == 5
    call_methods = [call.method for call in fake.calls]
    assert call_methods == [
        "create_thread",
        "post_message",
        "edit_message",
        "archive_thread",
        "delete_message",
    ]

    create_call = fake.calls[0]
    assert create_call.channel_id == channel_id
    assert create_call.name == "_smoke-test-verify"
    starter_msg_id = create_call.args[2]  # or returned from create_thread

    # Find thread_id and starter_msg_id
    thread_id = list(fake.threads.keys())[0]
    starter_msg_id = fake.threads[thread_id]["starter_message_id"]

    post_call = fake.calls[1]
    assert post_call.channel_or_thread_id == thread_id

    edit_call = fake.calls[2]
    assert edit_call.channel_or_thread_id == thread_id
    assert edit_call.content == "verified"

    archive_call = fake.calls[3]
    assert archive_call.thread_id == thread_id
    assert fake.threads[thread_id]["archived"] is True
    assert fake.threads[thread_id]["locked"] is True

    delete_call = fake.calls[4]
    assert delete_call.channel_or_thread_id == channel_id
    assert delete_call.message_id == starter_msg_id

    # The starter message must have been deleted from in-memory messages
    assert starter_msg_id not in fake.messages


@pytest.mark.anyio
async def test_run_smoke_propagates_gateway_error() -> None:
    """run_smoke lets DiscordGatewayError propagate if a gateway call fails."""
    mock_gateway = MagicMock()
    mock_gateway.create_thread = AsyncMock(
        side_effect=DiscordGatewayError("Failed to create thread")
    )

    with pytest.raises(DiscordGatewayError, match="Failed to create thread"):
        await run_smoke(mock_gateway, "channel-1")


@pytest.mark.anyio
async def test_verify_channel_permissions_all_granted() -> None:
    """verify_channel_permissions returns an empty list when all 7 permissions are granted."""
    mock_channel = MagicMock()
    mock_guild = MagicMock()
    mock_me = MagicMock()
    mock_perms = MagicMock(spec=discord.Permissions)
    for perm_attr in REQUIRED_DISCORD_PERMISSIONS:
        setattr(mock_perms, perm_attr, True)

    mock_channel.permissions_for.return_value = mock_perms
    mock_guild.me = mock_me
    mock_channel.guild = mock_guild

    mock_client = MagicMock()
    mock_client.user.id = 99999

    missing = await verify_channel_permissions(mock_channel, mock_client)
    assert missing == []


@pytest.mark.anyio
async def test_verify_channel_permissions_missing_permissions() -> None:
    """verify_channel_permissions lists human-readable names of missing permissions."""
    mock_channel = MagicMock()
    mock_guild = MagicMock()
    mock_me = MagicMock()
    mock_perms = MagicMock(spec=discord.Permissions)
    for perm_attr in REQUIRED_DISCORD_PERMISSIONS:
        setattr(mock_perms, perm_attr, True)

    # Revoke two permissions
    setattr(mock_perms, "manage_messages", False)
    setattr(mock_perms, "create_public_threads", False)

    mock_channel.permissions_for.return_value = mock_perms
    mock_guild.me = mock_me
    mock_channel.guild = mock_guild

    mock_client = MagicMock()
    mock_client.user.id = 99999

    missing = await verify_channel_permissions(mock_channel, mock_client)
    assert "Manage Messages" in missing
    assert "Create Public Threads" in missing
    assert len(missing) == 2
