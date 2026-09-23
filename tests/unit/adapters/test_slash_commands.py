"""Unit tests for Discord slash commands (/status, /pause, /mode) (T074, Spec 05a)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
import discord
from discord import app_commands

from runner.adapters.discord.commands import (
    OFFLINE_NOTICE,
    PAUSE_CONFIRMATION,
    format_status_response,
    handle_mode,
    handle_pause,
    handle_status,
    register_commands,
)
from runner.domain.state import VALID_PRESENCE_MODES
from tests.fakes.fake_state_store import FakeStateStore


class FakePresenceCoordinator:
    """Fake presence coordinator recording set_mode calls."""

    def __init__(self, initial_mode: str = "nearby") -> None:
        self.current_mode = initial_mode
        self.set_mode_calls: list[str] = []

    def set_mode(self, mode: str) -> str:
        self.set_mode_calls.append(mode)
        self.current_mode = mode
        return mode


class FakeStateCoordinator:
    """Fake state coordinator recording request_pause calls."""

    def __init__(self) -> None:
        self.request_pause_called = False

    def request_pause(self) -> None:
        self.request_pause_called = True


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
    """/pause replies with non-empty offline notice string when coordinator is None."""
    await handle_pause(mock_interaction, state_coordinator=None)

    mock_interaction.response.send_message.assert_awaited_once_with(OFFLINE_NOTICE)
    assert OFFLINE_NOTICE != ""
    assert "offline" in OFFLINE_NOTICE.lower()


@pytest.mark.anyio
async def test_handle_pause_with_coordinator_requests_pause_and_replies(
    mock_interaction: MagicMock,
) -> None:
    """/pause calls request_pause on StateCoordinator and replies with confirmation."""
    coordinator = FakeStateCoordinator()
    await handle_pause(mock_interaction, state_coordinator=coordinator)

    assert coordinator.request_pause_called is True
    mock_interaction.response.send_message.assert_awaited_once_with(PAUSE_CONFIRMATION)


@pytest.mark.anyio
async def test_handle_mode_replies_with_offline_notice(
    mock_interaction: MagicMock,
) -> None:
    """/mode replies with non-empty offline notice string when coordinator is None."""
    await handle_mode(mock_interaction, mode="away", presence_coordinator=None)

    mock_interaction.response.send_message.assert_awaited_once_with(OFFLINE_NOTICE)
    assert OFFLINE_NOTICE != ""
    assert "offline" in OFFLINE_NOTICE.lower()


@pytest.mark.anyio
async def test_handle_mode_away_switches_presence(
    mock_interaction: MagicMock,
) -> None:
    """/mode away calls set_mode('away') and replies with confirmation."""
    coordinator = FakePresenceCoordinator(initial_mode="nearby")
    await handle_mode(mock_interaction, mode="away", presence_coordinator=coordinator)

    assert coordinator.set_mode_calls == ["away"]
    assert coordinator.current_mode == "away"
    mock_interaction.response.send_message.assert_awaited_once_with("Presence mode set to away.")


@pytest.mark.anyio
async def test_handle_mode_nearby_switches_presence(
    mock_interaction: MagicMock,
) -> None:
    """/mode nearby calls set_mode('nearby') and replies with confirmation."""
    coordinator = FakePresenceCoordinator(initial_mode="away")
    await handle_mode(mock_interaction, mode="nearby", presence_coordinator=coordinator)

    assert coordinator.set_mode_calls == ["nearby"]
    assert coordinator.current_mode == "nearby"
    mock_interaction.response.send_message.assert_awaited_once_with("Presence mode set to nearby.")


@pytest.mark.anyio
async def test_handle_mode_accepts_choice_object(
    mock_interaction: MagicMock,
) -> None:
    """/mode accepts an app_commands.Choice[str] object and unwraps value."""
    coordinator = FakePresenceCoordinator(initial_mode="nearby")
    choice = app_commands.Choice(name="away", value="away")
    await handle_mode(mock_interaction, mode=choice, presence_coordinator=coordinator)

    assert coordinator.set_mode_calls == ["away"]
    mock_interaction.response.send_message.assert_awaited_once_with("Presence mode set to away.")


@pytest.mark.anyio
async def test_handle_mode_invalid_value_replies_with_ephemeral_error(
    mock_interaction: MagicMock,
) -> None:
    """/mode with invalid value responds with ephemeral error and does not call set_mode."""
    coordinator = FakePresenceCoordinator(initial_mode="nearby")
    await handle_mode(mock_interaction, mode="invalid_mode", presence_coordinator=coordinator)

    assert len(coordinator.set_mode_calls) == 0
    mock_interaction.response.send_message.assert_awaited_once()
    args, kwargs = mock_interaction.response.send_message.await_args
    assert kwargs.get("ephemeral") is True
    reply = args[0]
    assert "invalid" in reply.lower()
    for valid_m in VALID_PRESENCE_MODES:
        assert valid_m in reply


def test_register_commands_on_command_tree_wiring_and_choices() -> None:
    """register_commands registers /status, /pause, and /mode with Choices restriction."""
    mock_client = MagicMock()
    mock_client._connection._command_tree = None
    tree = app_commands.CommandTree(mock_client)
    store = FakeStateStore({"runner_status": "running"})
    fake_presence = FakePresenceCoordinator()
    fake_state = FakeStateCoordinator()

    status_cmd, pause_cmd, mode_cmd = register_commands(
        tree,
        state_store=store,
        presence_coordinator=fake_presence,
        state_coordinator=fake_state,
    )

    assert status_cmd.name == "status"
    assert pause_cmd.name == "pause"
    assert mode_cmd.name == "mode"

    registered = {cmd.name for cmd in tree.get_commands()}
    assert {"status", "pause", "mode"}.issubset(registered)

    # Verify Choices restriction on /mode parameter
    assert len(mode_cmd.parameters) == 1
    mode_param = mode_cmd.parameters[0]
    assert mode_param.name == "mode"
    assert len(mode_param.choices) == len(VALID_PRESENCE_MODES)
    choice_values = {c.value for c in mode_param.choices}
    assert choice_values == set(VALID_PRESENCE_MODES)


@pytest.mark.anyio
async def test_register_commands_callbacks_execute_live_coordinators(
    mock_interaction: MagicMock,
) -> None:
    """Command tree callbacks properly route to live coordinators."""
    mock_client = MagicMock()
    mock_client._connection._command_tree = None
    tree = app_commands.CommandTree(mock_client)
    store = FakeStateStore({"runner_status": "running"})
    fake_presence = FakePresenceCoordinator()
    fake_state = FakeStateCoordinator()

    status_cmd, pause_cmd, mode_cmd = register_commands(
        tree,
        state_store=store,
        presence_coordinator=fake_presence,
        state_coordinator=fake_state,
    )

    # Invoke pause callback
    await pause_cmd._callback(mock_interaction)
    assert fake_state.request_pause_called is True

    # Invoke mode callback with choice
    choice = app_commands.Choice(name="away", value="away")
    await mode_cmd._callback(mock_interaction, mode=choice)
    assert fake_presence.set_mode_calls == ["away"]


@pytest.mark.anyio
async def test_register_commands_backward_compatibility(
    mock_interaction: MagicMock,
) -> None:
    """Calling register_commands with only state_store leaves coordinators None (offline safe)."""
    mock_client = MagicMock()
    mock_client._connection._command_tree = None
    tree = app_commands.CommandTree(mock_client)
    store = FakeStateStore({"runner_status": "running"})

    status_cmd, pause_cmd, mode_cmd = register_commands(tree, store)

    await pause_cmd._callback(mock_interaction)
    mock_interaction.response.send_message.assert_awaited_with(OFFLINE_NOTICE)

    await mode_cmd._callback(mock_interaction, mode="away")
    mock_interaction.response.send_message.assert_awaited_with(OFFLINE_NOTICE)
