"""Unit tests for hotkey action dispatcher and presence toggle coordination (T058)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from runner.application.hotkey_dispatch import HotkeyDispatcher
from runner.application.presence_coordinator import PresenceCoordinator
from runner.application.queue_orchestrator import QueueOrchestrator
from runner.application.state_coordinator import StateCoordinator
from runner.application.worker_supervisor import RunTerminationReason, WorkerSupervisor
from runner.domain.state import RunnerState
from runner.ports.state_store import StateStore
from runner.ports.terminal_display import TerminalDisplay, UiEventSink


class InMemoryStateStore:
    def __init__(self, initial_doc: dict[str, Any] | None = None) -> None:
        self.doc: dict[str, Any] | None = initial_doc

    def read(self) -> dict[str, Any] | None:
        return self.doc

    def write(self, document: Mapping[str, Any]) -> None:
        self.doc = dict(document)


def test_hotkey_p_toggles_pause_and_unpause() -> None:
    mock_orchestrator = MagicMock(spec=QueueOrchestrator)
    mock_orchestrator.is_paused = False

    dispatcher = HotkeyDispatcher(orchestrator=mock_orchestrator)

    # First press [p]: pauses execution
    dispatcher.dispatch("p")
    mock_orchestrator.pause.assert_called_once()
    mock_orchestrator.resume.assert_not_called()

    # Orchestrator is now paused
    mock_orchestrator.is_paused = True
    mock_orchestrator.pause.reset_mock()

    # Second press [p]: unpauses execution
    dispatcher.dispatch("p")
    mock_orchestrator.resume.assert_called_once()
    mock_orchestrator.pause.assert_not_called()


def test_hotkey_p_case_insensitive() -> None:
    mock_orchestrator = MagicMock(spec=QueueOrchestrator)
    mock_orchestrator.is_paused = False

    dispatcher = HotkeyDispatcher(orchestrator=mock_orchestrator)
    dispatcher.dispatch("P")
    mock_orchestrator.pause.assert_called_once()


def test_presence_coordinator_toggle_mode_nearby_to_away_and_back() -> None:
    store = InMemoryStateStore()
    state_coord = StateCoordinator(state_store=store)
    mock_display = MagicMock(spec=TerminalDisplay)
    mock_sink = MagicMock(spec=UiEventSink)

    presence_coord = PresenceCoordinator(
        state_coordinator=state_coord,
        terminal_display=mock_display,
        ui_event_sink=mock_sink,
    )

    # Initial state is nearby
    assert state_coord.get_or_create_state().presence_mode == "nearby"

    # Toggle 1: nearby -> away
    new_mode = presence_coord.toggle_mode()
    assert new_mode == "away"
    assert state_coord.get_or_create_state().presence_mode == "away"
    assert store.doc is not None
    assert store.doc["presence_mode"] == "away"
    mock_display.update_state.assert_called()
    last_state = mock_display.update_state.call_args[0][0]
    assert last_state.presence_mode == "away"
    mock_sink.emit.assert_called_with("runner", "Presence mode changed to away")

    # Toggle 2: away -> nearby
    new_mode_2 = presence_coord.toggle_mode()
    assert new_mode_2 == "nearby"
    assert state_coord.get_or_create_state().presence_mode == "nearby"
    assert store.doc is not None
    assert store.doc["presence_mode"] == "nearby"


def test_hotkey_m_invokes_presence_coordinator_toggle() -> None:
    mock_presence = MagicMock(spec=PresenceCoordinator)
    dispatcher = HotkeyDispatcher(presence_coordinator=mock_presence)

    dispatcher.dispatch("m")
    mock_presence.toggle_mode.assert_called_once()

    mock_presence.reset_mock()
    dispatcher.dispatch("M")
    mock_presence.toggle_mode.assert_called_once()


def test_hotkey_q_triggers_graceful_shutdown() -> None:
    stop_event = asyncio.Event()
    mock_supervisor = MagicMock(spec=WorkerSupervisor)
    store = InMemoryStateStore()
    state_coord = StateCoordinator(state_store=store)
    shutdown_called = False

    def on_shutdown() -> None:
        nonlocal shutdown_called
        shutdown_called = True

    dispatcher = HotkeyDispatcher(
        supervisor=mock_supervisor,
        stop_event=stop_event,
        state_coordinator=state_coord,
        on_shutdown=on_shutdown,
    )

    assert not stop_event.is_set()
    dispatcher.dispatch("q")

    assert stop_event.is_set()
    mock_supervisor.request_kill.assert_called_once_with(
        RunTerminationReason.KILLED_INTERRUPT
    )
    assert shutdown_called is True


def test_hotkey_unknown_key_ignored() -> None:
    dispatcher = HotkeyDispatcher()
    result = dispatcher.dispatch("x")
    assert result is None


def test_hotkey_custom_handler_registration() -> None:
    dispatcher = HotkeyDispatcher()
    custom_called = False

    def custom_handler() -> str:
        nonlocal custom_called
        custom_called = True
        return "custom_action"

    dispatcher.register_handler("o", custom_handler)
    res = dispatcher.dispatch("o")

    assert custom_called is True
    assert res == "custom_action"
