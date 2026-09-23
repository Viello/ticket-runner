"""Unit tests for Discord client lifecycle module (T073, Spec 05a)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from runner.adapters.discord import DiscordClient, client as client_module
from runner.domain.config import DiscordConfig, RunnerConfig
from runner.domain.exceptions import DiscordGatewayError


@pytest.fixture
def sample_discord_config() -> DiscordConfig:
    """Fixture providing a standard DiscordConfig."""
    return DiscordConfig(
        enabled=True,
        token_env="DISCORD_BOT_TOKEN",
        channel_id="1234567890",
        guild_id="9876543210",
        notify_user_id="",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    """Fixture providing a mock discord.Client."""
    mock = MagicMock()
    mock._connection._command_tree = None
    mock.fetch_channel = AsyncMock()
    mock.get_channel = MagicMock(return_value=None)
    mock.start = AsyncMock()
    mock.close = AsyncMock()
    mock.event = MagicMock(side_effect=lambda fn: fn)
    return mock


@pytest.fixture
def mock_tree() -> MagicMock:
    """Fixture providing a mock app_commands.CommandTree."""
    mock = MagicMock()
    mock.sync = AsyncMock()
    mock.copy_global_to = MagicMock()
    return mock


def test_client_init_defaults(sample_discord_config: DiscordConfig) -> None:
    """DiscordClient initializes client, tree, and ready_event with defaults."""
    dc = DiscordClient(sample_discord_config)

    assert isinstance(dc.client, discord.Client)
    assert dc.client.intents.message_content is True
    assert dc.tree is not None
    assert isinstance(dc.ready_event, asyncio.Event)
    assert not dc.ready_event.is_set()
    assert dc.ready_error is None


def test_client_init_with_runner_config(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """DiscordClient unwraps RunnerConfig.discord when passed a full RunnerConfig."""
    mock_runner_config = MagicMock(spec=RunnerConfig)
    mock_runner_config.discord = DiscordConfig(
        enabled=True,
        token_env="DISCORD_BOT_TOKEN",
        channel_id="11111",
        guild_id="22222",
    )
    dc = DiscordClient(mock_runner_config, client=mock_client, tree=mock_tree)

    assert dc.config.channel_id == "11111"
    assert dc.config.guild_id == "22222"
    assert dc.client is mock_client
    assert dc.tree is mock_tree


@pytest.mark.anyio
async def test_on_ready_explicit_guild_id(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """When config.guild_id is non-empty, tree.sync receives discord.Object(id=guild_id)."""
    cfg = DiscordConfig(channel_id="10001", guild_id="20002")
    mock_channel = MagicMock()
    mock_client.fetch_channel.return_value = mock_channel

    dc = DiscordClient(cfg, client=mock_client, tree=mock_tree)
    assert not dc.ready_event.is_set()

    await dc.on_ready()

    mock_client.fetch_channel.assert_awaited_once_with(10001)
    mock_tree.copy_global_to.assert_called_once_with(guild=discord.Object(id=20002))
    mock_tree.sync.assert_awaited_once_with(guild=discord.Object(id=20002))
    assert dc.ready_event.is_set()


@pytest.mark.anyio
async def test_on_ready_fallback_to_channel_guild_id(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """When config.guild_id is empty, tree.sync receives guild ID resolved from channel."""
    cfg = DiscordConfig(channel_id="10001", guild_id="")
    mock_channel = MagicMock()
    mock_channel.guild.id = 30003
    mock_client.fetch_channel.return_value = mock_channel

    dc = DiscordClient(cfg, client=mock_client, tree=mock_tree)
    assert not dc.ready_event.is_set()

    await dc.on_ready()

    mock_client.fetch_channel.assert_awaited_once_with(10001)
    mock_tree.copy_global_to.assert_called_once_with(guild=discord.Object(id=30003))
    mock_tree.sync.assert_awaited_once_with(guild=discord.Object(id=30003))
    assert dc.ready_event.is_set()


@pytest.mark.anyio
async def test_on_ready_missing_channel_and_guild_raises(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """When guild ID cannot be resolved from config or channel, raises DiscordGatewayError."""
    cfg = DiscordConfig(channel_id="", guild_id="")

    dc = DiscordClient(cfg, client=mock_client, tree=mock_tree)

    with pytest.raises(DiscordGatewayError, match="guild"):
        await dc.on_ready()

    assert not dc.ready_event.is_set()
    mock_tree.sync.assert_not_called()


@pytest.mark.anyio
async def test_on_ready_fetch_channel_error_wrapped(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """Exceptions during channel fetch in on_ready are wrapped in DiscordGatewayError."""
    cfg = DiscordConfig(channel_id="10001", guild_id="")
    mock_client.fetch_channel.side_effect = discord.HTTPException(
        MagicMock(), "Discord API error"
    )

    dc = DiscordClient(cfg, client=mock_client, tree=mock_tree)

    with pytest.raises(DiscordGatewayError, match="Failed to fetch channel"):
        await dc.on_ready()

    assert not dc.ready_event.is_set()
    mock_tree.sync.assert_not_called()


@pytest.mark.anyio
async def test_on_ready_tree_sync_error_wrapped(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """Exceptions during tree.sync in on_ready are wrapped in DiscordGatewayError."""
    cfg = DiscordConfig(channel_id="10001", guild_id="20002")
    mock_tree.sync.side_effect = discord.HTTPException(
        MagicMock(), "Sync rate limited"
    )

    dc = DiscordClient(cfg, client=mock_client, tree=mock_tree)

    with pytest.raises(DiscordGatewayError, match="Failed to sync command tree"):
        await dc.on_ready()

    assert not dc.ready_event.is_set()


@pytest.mark.anyio
async def test_on_ready_copy_global_to_error_wrapped(
    mock_client: MagicMock, mock_tree: MagicMock
) -> None:
    """Exceptions during tree.copy_global_to in on_ready are wrapped in DiscordGatewayError."""
    cfg = DiscordConfig(channel_id="10001", guild_id="20002")
    mock_tree.copy_global_to.side_effect = RuntimeError("Copy failed")

    dc = DiscordClient(cfg, client=mock_client, tree=mock_tree)

    with pytest.raises(DiscordGatewayError, match="Failed to sync command tree"):
        await dc.on_ready()

    assert not dc.ready_event.is_set()


@pytest.mark.anyio
async def test_start_with_explicit_token(
    mock_client: MagicMock, sample_discord_config: DiscordConfig
) -> None:
    """Calling start(token) passes the token directly to client.start."""
    dc = DiscordClient(sample_discord_config, client=mock_client)

    await dc.start("explicit_test_token")

    mock_client.start.assert_awaited_once_with("explicit_test_token")


@pytest.mark.anyio
async def test_start_with_env_token(
    mock_client: MagicMock,
    sample_discord_config: DiscordConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling start() without argument reads token from configured env var."""
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token_from_env_var")
    dc = DiscordClient(sample_discord_config, client=mock_client)

    await dc.start()

    mock_client.start.assert_awaited_once_with("token_from_env_var")


@pytest.mark.anyio
async def test_start_missing_env_token_raises(
    mock_client: MagicMock,
    sample_discord_config: DiscordConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling start() when env var is unset raises DiscordGatewayError."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    dc = DiscordClient(sample_discord_config, client=mock_client)

    with pytest.raises(DiscordGatewayError, match="DISCORD_BOT_TOKEN"):
        await dc.start()

    mock_client.start.assert_not_called()


@pytest.mark.anyio
async def test_start_security_token_never_stored_on_instance(
    mock_client: MagicMock, sample_discord_config: DiscordConfig
) -> None:
    """Token is never assigned to instance attributes or logged."""
    dc = DiscordClient(sample_discord_config, client=mock_client)

    await dc.start("super_secret_token_value_12345")

    assert not hasattr(dc, "token")
    assert not hasattr(dc, "_token")
    assert "token" not in dc.__dict__
    assert "_token" not in dc.__dict__
    assert "super_secret_token_value_12345" not in repr(dc)


@pytest.mark.anyio
async def test_on_error_sets_ready_error_and_event(
    mock_client: MagicMock, sample_discord_config: DiscordConfig
) -> None:
    """DiscordClient.on_error records active exception as ready_error and unblocks ready_event."""
    dc = DiscordClient(sample_discord_config, client=mock_client)
    assert not dc.ready_event.is_set()
    assert dc.ready_error is None

    test_exc = ValueError("Fatal event dispatch crash")
    try:
        raise test_exc
    except ValueError:
        await dc.on_error("on_ready")

    assert dc.ready_error is test_exc
    assert dc.ready_event.is_set()


@pytest.mark.anyio
async def test_close_normal(
    mock_client: MagicMock, sample_discord_config: DiscordConfig
) -> None:
    """Calling close() awaits client.close(), clears ready_event, and resets ready_error."""
    dc = DiscordClient(sample_discord_config, client=mock_client)
    dc.ready_event.set()
    dc.ready_error = RuntimeError("old error")

    await dc.close()

    mock_client.close.assert_awaited_once()
    assert not dc.ready_event.is_set()
    assert dc.ready_error is None


@pytest.mark.anyio
async def test_close_hang_swallowed_within_3s(
    mock_client: MagicMock, sample_discord_config: DiscordConfig
) -> None:
    """When client.close() hangs indefinitely, close() exits cleanly in ~2.0s without error."""
    async def hanging_close() -> None:
        await asyncio.sleep(10.0)

    mock_client.close.side_effect = hanging_close
    dc = DiscordClient(sample_discord_config, client=mock_client)
    dc.ready_event.set()

    start_time = time.monotonic()
    await dc.close()
    elapsed = time.monotonic() - start_time

    assert 1.9 <= elapsed < 3.0
    assert not dc.ready_event.is_set()


@pytest.mark.anyio
async def test_module_level_interface(
    monkeypatch: pytest.MonkeyPatch, mock_client: MagicMock
) -> None:
    """Module-level helpers and exports function as expected."""
    assert hasattr(client_module, "tree")
    assert hasattr(client_module, "ready_event")
    assert hasattr(client_module, "client")
    assert hasattr(client_module, "start")
    assert hasattr(client_module, "close")
    assert hasattr(client_module, "init_client")
    assert hasattr(client_module, "get_default_client")

    cfg = DiscordConfig(channel_id="123", guild_id="456")
    inst = client_module.init_client(cfg, client=mock_client)
    assert client_module.get_default_client() is inst
    assert inst.client is mock_client

    await client_module.start("module_test_token")
    mock_client.start.assert_awaited_once_with("module_test_token")

    await client_module.close()
    mock_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_on_message_delegates_to_process_thread_reply(
    mock_client: MagicMock,
    sample_discord_config: DiscordConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DiscordClient.on_message calls process_thread_reply with message, repo, and config."""
    mock_process = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "runner.adapters.discord.client.process_thread_reply", mock_process
    )

    mock_repo = MagicMock()
    dc = DiscordClient(
        sample_discord_config,
        client=mock_client,
        signal_repository=mock_repo,
    )

    fake_message = MagicMock(spec=discord.Message)
    await dc.on_message(fake_message)

    mock_process.assert_awaited_once_with(
        fake_message, mock_repo, sample_discord_config,
        presence_coordinator=None,
    )


def test_client_init_with_coordinators(
    sample_discord_config: DiscordConfig,
    mock_client: MagicMock,
    mock_tree: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DiscordClient passes presence_coordinator and state_coordinator to register_commands."""
    mock_register = MagicMock()
    monkeypatch.setattr("runner.adapters.discord.client.register_commands", mock_register)

    mock_presence = MagicMock()
    mock_state = MagicMock()
    mock_store = MagicMock()

    dc = DiscordClient(
        sample_discord_config,
        client=mock_client,
        tree=mock_tree,
        state_store=mock_store,
        presence_coordinator=mock_presence,
        state_coordinator=mock_state,
    )

    assert dc.presence_coordinator is mock_presence
    assert dc.state_coordinator is mock_state
    mock_register.assert_called_once_with(
        mock_tree,
        state_store=mock_store,
        presence_coordinator=mock_presence,
        state_coordinator=mock_state,
    )

