"""Unit tests for StateCoordinator application service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.filesystem.json_state_store import JsonStateStore
from runner.application.state_coordinator import StateCoordinator
from runner.domain.exceptions import StateFormatError
from runner.domain.state import RunnerState, StateStatus, TokenState


class FakeStateStore:
    """In-memory StateStore double for testing StateCoordinator."""

    def __init__(self, initial_document: dict[str, Any] | None = None) -> None:
        self._doc: dict[str, Any] | None = (
            dict(initial_document) if initial_document is not None else None
        )
        self.write_calls: list[dict[str, Any]] = []

    def read(self) -> dict[str, Any] | None:
        if self._doc is None:
            return None
        return dict(self._doc)

    def write(self, document: Any) -> None:
        doc_copy = dict(document)
        self.write_calls.append(doc_copy)
        self._doc = doc_copy


def _sample_persisted_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "active_ticket_id": "T042",
        "status": "WORKING",
        "opencode_session_id": "session-xyz",
        "selected_model": "test/model",
        "presence_mode": "nearby",
        "verification_attempts": 0,
        "tokens": {
            "current": 10000,
            "warning_sent": False,
        },
        "branch": "agent/ticket-runner",
        "started_at": "2026-09-19T10:00:00+00:00",
        "last_checkpoint": None,
        "tui_open": False,
        "tui_session_id": None,
        "last_updated": "2026-09-19T10:05:00+00:00",
    }
    base.update(overrides)
    return base


def test_load_state_returns_none_when_store_empty() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)

    assert coordinator.load_state() is None
    assert coordinator.current_state is None


def test_load_state_parses_existing_document() -> None:
    store = FakeStateStore(_sample_persisted_dict())
    coordinator = StateCoordinator(state_store=store)

    state = coordinator.load_state()
    assert state is not None
    assert state.active_ticket_id == "T042"
    assert state.status == StateStatus.WORKING
    assert coordinator.current_state == state


def test_load_state_raises_on_corrupt_data() -> None:
    store = FakeStateStore({"status": "INVALID_STATUS"})
    coordinator = StateCoordinator(state_store=store)

    with pytest.raises(StateFormatError):
        coordinator.load_state()


def test_save_state_atomically_writes_to_store() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)

    state = RunnerState.idle(branch="main", selected_model="gpt-4o")
    coordinator.save_state(state)

    assert len(store.write_calls) == 1
    persisted = store.write_calls[0]
    assert persisted["status"] == "IDLE"
    assert persisted["branch"] == "main"
    assert persisted["selected_model"] == "gpt-4o"
    assert coordinator.current_state == state


def test_save_state_preserves_unmanaged_keys() -> None:
    existing = {
        "selected_model": "deepseek/chat",
        "custom_plugin_meta": {"version": "1.0"},
        "operator_note": "preserved",
    }
    store = FakeStateStore(existing)
    coordinator = StateCoordinator(state_store=store)

    state = RunnerState.idle(branch="agent/ticket-runner")
    # state.selected_model is None by default in idle() unless specified
    coordinator.save_state(state)

    persisted = store.write_calls[-1]
    assert persisted["status"] == "IDLE"
    assert persisted["custom_plugin_meta"] == {"version": "1.0"}
    assert persisted["operator_note"] == "preserved"
    # Should retain selected_model from existing since state.selected_model is None
    assert persisted["selected_model"] == "deepseek/chat"


def test_save_state_overwrites_selected_model_if_state_has_it() -> None:
    existing = {"selected_model": "old/model"}
    store = FakeStateStore(existing)
    coordinator = StateCoordinator(state_store=store)

    state = RunnerState.idle(selected_model="new/model")
    coordinator.save_state(state)

    persisted = store.write_calls[-1]
    assert persisted["selected_model"] == "new/model"


# --- Dispatcher Tests ---


def test_transition_to_working_updates_and_persists() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store, branch="agent/ticket-runner")

    updated = coordinator.transition_to_working(ticket_id="T053", session_id="sess-1")
    assert updated.status == StateStatus.WORKING
    assert updated.active_ticket_id == "T053"
    assert updated.opencode_session_id == "sess-1"

    persisted = store.write_calls[-1]
    assert persisted["status"] == "WORKING"
    assert persisted["active_ticket_id"] == "T053"
    assert persisted["opencode_session_id"] == "sess-1"


def test_transition_to_gatekeeper_updates_and_persists() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    gk = coordinator.transition_to_gatekeeper(verification_attempts=1)
    assert gk.status == StateStatus.GATEKEEPER
    assert gk.active_ticket_id == "T053"
    assert gk.verification_attempts == 1

    persisted = store.write_calls[-1]
    assert persisted["status"] == "GATEKEEPER"
    assert persisted["verification_attempts"] == 1


def test_transition_to_idle_updates_and_persists() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    idle = coordinator.transition_to_idle()
    assert idle.status == StateStatus.IDLE
    assert idle.active_ticket_id is None

    persisted = store.write_calls[-1]
    assert persisted["status"] == "IDLE"
    assert persisted["active_ticket_id"] is None


def test_transition_to_pause_requested() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    paused = coordinator.transition_to_pause_requested()
    assert paused.status == StateStatus.PAUSE_REQUESTED

    persisted = store.write_calls[-1]
    assert persisted["status"] == "PAUSE_REQUESTED"


def test_transition_to_waiting_for_user() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    waiting = coordinator.transition_to_waiting_for_user()
    assert waiting.status == StateStatus.WAITING_FOR_USER

    persisted = store.write_calls[-1]
    assert persisted["status"] == "WAITING_FOR_USER"


def test_transition_to_circuit_breaker_tripped() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    tripped = coordinator.transition_to_circuit_breaker_tripped()
    assert tripped.status == StateStatus.CIRCUIT_BREAKER_TRIPPED

    persisted = store.write_calls[-1]
    assert persisted["status"] == "CIRCUIT_BREAKER_TRIPPED"


def test_record_tokens_persists() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    updated = coordinator.record_tokens(current=75000, warning_sent=True)
    assert updated.tokens.current == 75000
    assert updated.tokens.warning_sent is True

    persisted = store.write_calls[-1]
    assert persisted["tokens"]["current"] == 75000
    assert persisted["tokens"]["warning_sent"] is True


def test_set_presence_mode_persists() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)

    updated = coordinator.set_presence_mode("away")
    assert updated.presence_mode == "away"

    persisted = store.write_calls[-1]
    assert persisted["presence_mode"] == "away"


def test_tui_dispatchers_persist() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053", session_id="opencode-1")

    opened = coordinator.set_tui_open()
    assert opened.tui_open is True
    assert opened.tui_session_id == "opencode-1"

    cleared = coordinator.clear_tui()
    assert cleared.tui_open is False
    assert cleared.tui_session_id is None


def test_record_checkpoint_and_session_id() -> None:
    store = FakeStateStore(None)
    coordinator = StateCoordinator(state_store=store)
    coordinator.transition_to_working(ticket_id="T053")

    with_checkpoint = coordinator.record_checkpoint(".agent/checkpoints/T053/handoff.md")
    assert with_checkpoint.last_checkpoint == ".agent/checkpoints/T053/handoff.md"

    with_session = coordinator.record_session_id("new-session-id")
    assert with_session.opencode_session_id == "new-session-id"


def test_filesystem_integration_with_json_state_store(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    # Pre-write an existing file with an unmanaged key and selected_model
    initial_data = {
        "selected_model": "claude-3-7-sonnet",
        "custom_key": "unmanaged_value",
    }
    state_file.write_text(json.dumps(initial_data), encoding="utf-8")

    json_store = JsonStateStore(path=state_file)
    coordinator = StateCoordinator(state_store=json_store)

    # Transition to working
    coordinator.transition_to_working(ticket_id="T053")

    # Read back directly from disk
    content = json.loads(state_file.read_text(encoding="utf-8"))
    assert content["status"] == "WORKING"
    assert content["active_ticket_id"] == "T053"
    assert content["selected_model"] == "claude-3-7-sonnet"
    assert content["custom_key"] == "unmanaged_value"
