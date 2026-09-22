"""Unit tests for Discord slash commands (/status, /pause, /mode) (T074, Spec 05a)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
import discord
from discord import app_commands

from runner.adapters.discord.commands import (
    OFFLINE_NOTICE,
    format_status_response,
    handle_mode,
    handle_pause,
    handle_status,
    register_commands,
)
from tests.fakes.fake_state_store import FakeStateStore


@pytest.fixture
def mock_interaction() -> MagicMock:
    """Fixture providing a mock discord.Interaction."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


def test_format_status_response_none_state() -> None:
    """When state is None (absent file), response includes badge and no state message."""
    resp = format_status_response(None)
    assert "[Offline / Standalone Bot]" in resp
    assert "No runner state available" in resp


def test_format_status_response_offline_runner() -> None:
    """When runner_status != 'running', response includes [Offline / Standalone Bot] badge."""
    state = {
        "runner_status": "idle",
        "active_ticket_id": "T042",
        "selected_model": "deepseek/deepseek-chat",
    }
    resp = format_status_response(state)
    assert "[Offline / Standalone Bot]" in resp
    assert "idle" in resp
    assert "T042" in resp
    assert "deepseek/deepseek-chat" in resp


def test_format_status_response_running_runner() -> None:
    """When runner_status == 'running', response omits [Offline / Standalone Bot] badge."""
    state = {
        "runner_status": "running",
        "active_ticket_id": "T042",
        "tokens": {"current": 45000, "warning_sent": False},
    }
    resp = format_status_response(state)
    assert "[Offline / Standalone Bot]" not in resp
    assert "running" in resp
    assert "T042" in resp
    assert "45000" in resp


@pytest.mark.anyio
async def test_handle_status_reads_offline_state_and_sends(
    mock_interaction: MagicMock,
) -> None:
    """/status reads persisted state via StateStore and sends response with badge."""
    store = FakeStateStore({"runner_status": "stopped", "active_ticket_id": "T010"})
    await handle_status(mock_interaction, store)

    mock_interaction.response.send_message.assert_awaited_once()
    reply = mock_interaction.response.send_message.await_args.args[0]
    assert "[Offline / Standalone Bot]" in reply
    assert "stopped" in reply
    assert "T010" in reply


@pytest.mark.anyio
async def test_handle_status_handles_none_state_gracefully(
    mock_interaction: MagicMock,
) -> None:
    """/status handles uninitialized StateStore without raising an exception."""
    store = FakeStateStore(None)
    await handle_status(mock_interaction, store)

    mock_interaction.response.send_message.assert_awaited_once()
    reply = mock_interaction.response.send_message.await_args.args[0]
    assert "[Offline / Standalone Bot]" in reply
    assert "No runner state available" in reply


@pytest.mark.anyio
async def test_handle_pause_replies_with_offline_notice(
    mock_interaction: MagicMock,
) -> None:
    """/pause replies with non-empty offline notice string and does not mutate state."""
    await handle_pause(mock_interaction)

    mock_interaction.response.send_message.assert_awaited_once_with(OFFLINE_NOTICE)
    assert OFFLINE_NOTICE != ""
    assert "offline" in OFFLINE_NOTICE.lower()


@pytest.mark.anyio
async def test_handle_mode_replies_with_offline_notice(
    mock_interaction: MagicMock,
) -> None:
    """/mode replies with non-empty offline notice string."""
    await handle_mode(mock_interaction)

    mock_interaction.response.send_message.assert_awaited_once_with(OFFLINE_NOTICE)
    assert OFFLINE_NOTICE != ""
    assert "offline" in OFFLINE_NOTICE.lower()


def test_register_commands_on_command_tree() -> None:
    """register_commands registers /status, /pause, and /mode on a CommandTree."""
    mock_client = MagicMock()
    mock_client._connection._command_tree = None
    tree = app_commands.CommandTree(mock_client)
    store = FakeStateStore({"runner_status": "running"})

    status_cmd, pause_cmd, mode_cmd = register_commands(tree, store)

    assert status_cmd.name == "status"
    assert pause_cmd.name == "pause"
    assert mode_cmd.name == "mode"

    registered = {cmd.name for cmd in tree.get_commands()}
    assert {"status", "pause", "mode"}.issubset(registered)
