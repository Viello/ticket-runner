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
from ticket_runner import create_parser, main, run_bot


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
