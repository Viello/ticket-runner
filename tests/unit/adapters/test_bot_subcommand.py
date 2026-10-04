"""Unit tests for ticket_runner bot subcommand (--smoke and --run) (T075, Spec 05a)."""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from runner.adapters.discord.client import DiscordClient
from runner.adapters.discord.smoke import REQUIRED_DISCORD_PERMISSIONS
from runner.container import BotContainer
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.exceptions import DiscordGatewayError
from tests.fakes.fake_discord_gateway import FakeDiscordGateway
from ticket_runner import create_parser, main, run_bot, run_notify


def _make_test_config(
    enabled: bool = True,
    channel_id: str = "1234567890",
    token_env: str = "TEST_DISCORD_TOKEN",
) -> RunnerConfig:
    return RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(
            enabled=enabled,
            channel_id=channel_id,
            token_env=token_env,
        ),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
    )



def test_parser_bot_help() -> None:
    """--help on bot subcommand includes --smoke and --run."""
    parser = create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["bot", "--help"])
    assert exc_info.value.code == 0


def test_parser_bot_smoke_flag() -> None:
    """bot subcommand parses --smoke flag correctly."""
    parser = create_parser()
    args = parser.parse_args(["bot", "--smoke"])
    assert args.command == "bot"
    assert args.smoke is True
    assert args.run is False


def test_parser_bot_run_flag() -> None:
    """bot subcommand parses --run flag correctly."""
    parser = create_parser()
    args = parser.parse_args(["bot", "--run"])
    assert args.command == "bot"
    assert args.smoke is False
    assert args.run is True


def test_parser_bot_mutually_exclusive() -> None:
    """Providing both --smoke and --run raises argument error."""
    parser = create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["bot", "--smoke", "--run"])
    assert exc_info.value.code == 2


def test_parser_bot_requires_flag() -> None:
    """bot subcommand without either flag raises argument error."""
    parser = create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["bot"])
    assert exc_info.value.code == 2


@pytest.mark.anyio
async def test_run_bot_smoke_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --smoke executes smoke sequence, closes client, and exits 0."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()

    fake_gateway = FakeDiscordGateway()
    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.ready_event.set()
    mock_discord_client.start = AsyncMock()
    mock_discord_client.close = AsyncMock()

    mock_channel = MagicMock()
    mock_client_obj = MagicMock()
    mock_client_obj.get_channel.return_value = mock_channel
    mock_discord_client.client = mock_client_obj

    async def fake_perm_checker(chan: Any, cl: Any) -> list[str]:
        return []

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        smoke=True,
        container_instance=container,
        gateway=fake_gateway,
        permission_checker=fake_perm_checker,
        stderr=stderr,
    )

    assert exit_code == 0
    assert len(fake_gateway.calls) == 5
    assert fake_gateway.calls[0].method == "create_thread"
    assert fake_gateway.calls[-1].method == "delete_message"
    mock_discord_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_run_bot_smoke_missing_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --smoke fails with code 1 and error message when token is missing."""
    monkeypatch.delenv("TEST_DISCORD_TOKEN", raising=False)
    config = _make_test_config()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_bot(
        smoke=True,
        container_instance=container,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert "TEST_DISCORD_TOKEN" in err_output
    assert "token" in err_output.lower()


@pytest.mark.anyio
async def test_run_bot_smoke_missing_permission(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --smoke reports missing permission names to stderr and exits 1."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()

    fake_gateway = FakeDiscordGateway()
    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.ready_event.set()
    mock_discord_client.start = AsyncMock()
    mock_discord_client.close = AsyncMock()

    mock_channel = MagicMock()
    mock_client_obj = MagicMock()
    mock_client_obj.get_channel.return_value = mock_channel
    mock_discord_client.client = mock_client_obj

    async def fake_perm_checker(chan: Any, cl: Any) -> list[str]:
        return ["Manage Messages", "Create Public Threads"]

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        smoke=True,
        container_instance=container,
        gateway=fake_gateway,
        permission_checker=fake_perm_checker,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert "Manage Messages" in err_output
    assert "Create Public Threads" in err_output
    # run_smoke must not have been executed
    assert len(fake_gateway.calls) == 0
    mock_discord_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_run_bot_smoke_auth_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --smoke exits 1 if client.start() raises authentication error."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "invalid_token")
    config = _make_test_config()

    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.start = AsyncMock(
        side_effect=DiscordGatewayError("Improper token has been passed.")
    )
    mock_discord_client.close = AsyncMock()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        smoke=True,
        container_instance=container,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert "Authentication failed" in err_output
    mock_discord_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_run_bot_smoke_ready_error_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --smoke reports client.ready_error to stderr and exits 1 without timing out."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()

    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.ready_error = DiscordGatewayError("Failed to sync command tree to guild 123: 403 Forbidden")
    mock_discord_client.ready_event.set()
    mock_discord_client.start = AsyncMock()
    mock_discord_client.close = AsyncMock()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        smoke=True,
        container_instance=container,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert "Discord connection error" in err_output
    assert "Failed to sync command tree" in err_output
    mock_discord_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_run_bot_run_ready_error_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --run reports client.ready_error to stderr and exits 1."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()

    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.ready_error = DiscordGatewayError("Failed to sync command tree to guild 123: 403 Forbidden")
    mock_discord_client.ready_event.set()
    mock_discord_client.start = AsyncMock()
    mock_discord_client.close = AsyncMock()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        run=True,
        container_instance=container,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert "Discord connection error" in err_output
    assert "Failed to sync command tree" in err_output
    mock_discord_client.close.assert_awaited_once()


@pytest.mark.anyio
async def test_run_bot_run_sigint_clean_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_bot --run exits 130 cleanly on SIGINT / stop_event."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()

    stop_event = asyncio.Event()

    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()

    async def fake_start() -> None:
        stop_event.set()
        await asyncio.sleep(10)

    mock_discord_client.start = AsyncMock(side_effect=fake_start)
    mock_discord_client.close = AsyncMock()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        run=True,
        container_instance=container,
        stderr=stderr,
        stop_event=stop_event,
    )

    assert exit_code == 130
    mock_discord_client.close.assert_awaited_once()


def test_main_catches_keyboard_interrupt_returns_130_for_bot() -> None:
    """main returns 130 if KeyboardInterrupt is raised during bot execution."""
    with patch("ticket_runner.run_bot", side_effect=KeyboardInterrupt):
        code = main(["bot", "--run"])
        assert code == 130



@pytest.mark.anyio
async def test_security_token_never_in_stderr_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Secret bot token is never printed to stderr or included in failure messages."""
    secret_token = "SECRET_SUPER_SENSITIVE_BOT_TOKEN_998877"
    monkeypatch.setenv("TEST_DISCORD_TOKEN", secret_token)
    config = _make_test_config()

    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.start = AsyncMock(
        side_effect=Exception("Failed connection to discord gateway")
    )
    mock_discord_client.close = AsyncMock()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    stderr = StringIO()
    exit_code = await run_bot(
        smoke=True,
        container_instance=container,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert secret_token not in err_output


def test_main_bot_smoke_delegation() -> None:
    """main with ['bot', '--smoke'] routes to run_bot and returns its exit code."""
    with patch("ticket_runner.run_bot", new=AsyncMock(return_value=0)) as mock_run_bot:
        code = main(["bot", "--smoke"])
        assert code == 0
        mock_run_bot.assert_awaited_once()


@pytest.mark.anyio
async def test_run_notify_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify posts a message via injected gateway and exits 0."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config(channel_id="1234567890")
    fake_gateway = FakeDiscordGateway()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    exit_code = await run_notify(
        message="live-qa: scenario 1 — verified",
        container_instance=container,
        gateway=fake_gateway,
    )

    assert exit_code == 0
    assert len(fake_gateway.calls) == 1
    call = fake_gateway.calls[0]
    assert call.method == "post_message"
    assert call.channel_or_thread_id == "1234567890"
    assert call.content == "live-qa: scenario 1 — verified"


@pytest.mark.anyio
async def test_run_notify_disabled_discord(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify exits 1 with diagnostic if discord is disabled in config."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config(enabled=False)
    fake_gateway = FakeDiscordGateway()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="hello",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    assert len(fake_gateway.calls) == 0
    err_output = stderr.getvalue()
    assert "discord.enabled" in err_output
    assert "disabled" in err_output.lower()


@pytest.mark.anyio
async def test_run_notify_missing_channel_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify exits 1 with diagnostic if discord.channel_id is missing."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config(channel_id="")
    fake_gateway = FakeDiscordGateway()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="hello",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    assert len(fake_gateway.calls) == 0
    err_output = stderr.getvalue()
    assert "channel_id" in err_output


@pytest.mark.anyio
async def test_run_notify_invalid_channel_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify exits 1 with diagnostic if discord.channel_id is not numeric."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config(channel_id="not_a_number")
    fake_gateway = FakeDiscordGateway()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="hello",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    assert len(fake_gateway.calls) == 0
    err_output = stderr.getvalue()
    assert "channel_id" in err_output


@pytest.mark.anyio
async def test_run_notify_missing_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify exits 1 naming the token env var when token is unset or empty."""
    monkeypatch.delenv("TEST_DISCORD_TOKEN", raising=False)
    config = _make_test_config()
    fake_gateway = FakeDiscordGateway()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="hello",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    assert len(fake_gateway.calls) == 0
    err_output = stderr.getvalue()
    assert "TEST_DISCORD_TOKEN" in err_output
    assert "token" in err_output.lower()


@pytest.mark.anyio
async def test_run_notify_empty_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify exits 1 when message is empty or whitespace-only."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()
    fake_gateway = FakeDiscordGateway()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="   ",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    assert len(fake_gateway.calls) == 0
    err_output = stderr.getvalue()
    assert "empty" in err_output.lower()


@pytest.mark.anyio
async def test_run_notify_gateway_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify exits 1 and reports error message when gateway raises exception."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()
    fake_gateway = FakeDiscordGateway(
        raise_on_post_message=DiscordGatewayError("Remote API 500 server error")
    )

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="hello",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert "Remote API 500 server error" in err_output


@pytest.mark.anyio
async def test_run_notify_security_token_never_in_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Secret bot token is never logged, echoed in diagnostics, or printed on error."""
    secret_token = "SECRET_SUPER_SENSITIVE_BOT_TOKEN_12345"
    monkeypatch.setenv("TEST_DISCORD_TOKEN", secret_token)
    config = _make_test_config()
    fake_gateway = FakeDiscordGateway(
        raise_on_post_message=DiscordGatewayError(f"Failed with token {secret_token}")
    )

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=MagicMock(spec=DiscordClient),
    )

    stderr = StringIO()
    exit_code = await run_notify(
        message="hello",
        container_instance=container,
        gateway=fake_gateway,
        stderr=stderr,
    )

    assert exit_code == 1
    err_output = stderr.getvalue()
    assert secret_token not in err_output


@pytest.mark.anyio
async def test_run_notify_live_client_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_notify connects client, posts via DiscordPyGateway, and closes client when gateway is None."""
    monkeypatch.setenv("TEST_DISCORD_TOKEN", "valid_token_123")
    config = _make_test_config()

    mock_discord_client = MagicMock(spec=DiscordClient)
    mock_discord_client.client = MagicMock()
    mock_discord_client.ready_event = asyncio.Event()
    mock_discord_client.ready_event.set()
    mock_discord_client.ready_error = None
    mock_discord_client.start = AsyncMock()
    mock_discord_client.close = AsyncMock()

    container = BotContainer(
        config=config,
        runtime_paths=MagicMock(),
        signal_repository=MagicMock(),
        discord_client=mock_discord_client,
    )

    with patch("ticket_runner.DiscordPyGateway") as mock_gw_class:
        mock_gw_instance = AsyncMock()
        mock_gw_instance.post_message = AsyncMock(return_value="msg_123")
        mock_gw_class.return_value = mock_gw_instance

        exit_code = await run_notify(
            message="hello live",
            container_instance=container,
        )

        assert exit_code == 0
        mock_discord_client.start.assert_called_once()
        mock_gw_instance.post_message.assert_awaited_once_with(
            "1234567890", "hello live"
        )
        mock_discord_client.close.assert_awaited_once()


def test_main_notify_delegation() -> None:
    """main with ['notify', 'hello'] routes to run_notify and returns exit code 0."""
    with patch("ticket_runner.run_notify", new=AsyncMock(return_value=0)) as mock_run_notify:
        code = main(["notify", "hello"])
        assert code == 0
        mock_run_notify.assert_awaited_once()


def test_main_notify_catches_keyboard_interrupt_returns_130() -> None:
    """main returns 130 if KeyboardInterrupt is raised during notify execution."""
    with patch("ticket_runner.run_notify", side_effect=KeyboardInterrupt):
        code = main(["notify", "hello"])
        assert code == 130
