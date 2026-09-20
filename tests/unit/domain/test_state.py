"""Unit tests for RunnerState domain entity, StateStatus enum, and TokenState."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from runner.domain.exceptions import StateFormatError
from runner.domain.state import RunnerState, StateStatus, TokenState


def _sample_state_dict(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "active_ticket_id": "T042",
        "status": "WORKING",
        "opencode_session_id": "session-123",
        "selected_model": "test/model",
        "presence_mode": "nearby",
        "verification_attempts": 1,
        "tokens": {
            "current": 45000,
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


# --- TokenState tests ---


def test_token_state_validation_valid() -> None:
    tokens = TokenState(current=1000, warning_sent=True)
    assert tokens.current == 1000
    assert tokens.warning_sent is True
    assert tokens["current"] == 1000
    assert tokens["warning_sent"] is True
    assert tokens.to_dict() == {"current": 1000, "warning_sent": True}


def test_token_state_rejects_negative_current() -> None:
    with pytest.raises(StateFormatError, match="non-negative integer"):
        TokenState(current=-1)


def test_token_state_rejects_boolean_current() -> None:
    with pytest.raises(StateFormatError, match="non-negative integer"):
        TokenState(current=True)  # type: ignore[arg-type]


def test_token_state_rejects_non_bool_warning_sent() -> None:
    with pytest.raises(StateFormatError, match="boolean"):
        TokenState(current=10, warning_sent="yes")  # type: ignore[arg-type]


def test_token_state_from_dict_success() -> None:
    tokens = TokenState.from_dict({"current": 500, "warning_sent": False})
    assert tokens.current == 500
    assert tokens.warning_sent is False


def test_token_state_from_dict_invalid() -> None:
    with pytest.raises(StateFormatError):
        TokenState.from_dict("not-a-dict")  # type: ignore[arg-type]

    with pytest.raises(StateFormatError, match="Missing required field 'current'"):
        TokenState.from_dict({"warning_sent": False})

    with pytest.raises(StateFormatError, match="Missing required field 'warning_sent'"):
        TokenState.from_dict({"current": 100})


# --- RunnerState Parsing & Validation ---


def test_runner_state_from_dict_parses_all_13_fields() -> None:
    data = _sample_state_dict()
    state = RunnerState.from_dict(data)

    assert state.active_ticket_id == "T042"
    assert state.status == StateStatus.WORKING
    assert state.status.value == "WORKING"
    assert state.opencode_session_id == "session-123"
    assert state.selected_model == "test/model"
    assert state.presence_mode == "nearby"
    assert state.verification_attempts == 1
    assert state.tokens.current == 45000
    assert state.tokens.warning_sent is False
    assert state.branch == "agent/ticket-runner"
    assert state.started_at == "2026-09-19T10:00:00+00:00"
    assert state.last_checkpoint is None
    assert state.tui_open is False
    assert state.tui_session_id is None
    assert state.last_updated == "2026-09-19T10:05:00+00:00"


def test_runner_state_from_dict_defaults_tui_fields_if_omitted() -> None:
    data = _sample_state_dict()
    data.pop("tui_open")
    data.pop("tui_session_id")
    state = RunnerState.from_dict(data)
    assert state.tui_open is False
    assert state.tui_session_id is None


def test_runner_state_to_dict_round_trip() -> None:
    data = _sample_state_dict(last_checkpoint=".agent/checkpoints/T042/handoff.md")
    state = RunnerState.from_dict(data)
    dumped = state.to_dict()
    assert dumped == data
    restored = RunnerState.from_dict(dumped)
    assert restored == state


def test_runner_state_from_dict_rejects_non_mapping() -> None:
    with pytest.raises(StateFormatError, match="mapping"):
        RunnerState.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "missing_key",
    [
        "active_ticket_id",
        "status",
        "opencode_session_id",
        "selected_model",
        "presence_mode",
        "verification_attempts",
        "tokens",
        "branch",
        "started_at",
        "last_checkpoint",
        "last_updated",
    ],
)
def test_runner_state_from_dict_missing_required_field_raises(missing_key: str) -> None:
    data = _sample_state_dict()
    data.pop(missing_key)
    with pytest.raises(StateFormatError, match=f"Missing required field '{missing_key}'"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_invalid_status_raises() -> None:
    data = _sample_state_dict(status="UNKNOWN_STATUS")
    with pytest.raises(StateFormatError, match="Invalid status 'UNKNOWN_STATUS'"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_invalid_presence_mode_raises() -> None:
    data = _sample_state_dict(presence_mode="flying")
    with pytest.raises(StateFormatError, match="presence_mode"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_negative_attempts_raises() -> None:
    data = _sample_state_dict(verification_attempts=-1)
    with pytest.raises(StateFormatError, match="verification_attempts"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_boolean_attempts_raises() -> None:
    data = _sample_state_dict(verification_attempts=True)
    with pytest.raises(StateFormatError, match="verification_attempts"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_negative_tokens_raises() -> None:
    data = _sample_state_dict(tokens={"current": -10, "warning_sent": False})
    with pytest.raises(StateFormatError, match="non-negative integer"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_invalid_timestamp_raises() -> None:
    data = _sample_state_dict(started_at="invalid-date")
    with pytest.raises(StateFormatError, match="started_at"):
        RunnerState.from_dict(data)

    data = _sample_state_dict(last_updated="")
    with pytest.raises(StateFormatError, match="last_updated"):
        RunnerState.from_dict(data)


def test_runner_state_from_dict_empty_branch_raises() -> None:
    data = _sample_state_dict(branch="")
    with pytest.raises(StateFormatError, match="branch"):
        RunnerState.from_dict(data)


# --- RunnerState Transitions & Immutability ---


def test_runner_state_idle_factory() -> None:
    state = RunnerState.idle(branch="main", selected_model="custom/model")
    assert state.status == StateStatus.IDLE
    assert state.active_ticket_id is None
    assert state.opencode_session_id is None
    assert state.selected_model == "custom/model"
    assert state.branch == "main"
    assert state.verification_attempts == 0
    assert state.tokens.current == 0
    assert state.tokens.warning_sent is False
    assert state.tui_open is False


def test_transition_to_working_immutability() -> None:
    initial = RunnerState.idle(branch="agent/ticket-runner")
    updated = initial.to_working(ticket_id="T053", session_id="sess-abc")

    # Original remains idle
    assert initial.status == StateStatus.IDLE
    assert initial.active_ticket_id is None

    # Updated is working
    assert updated.status == StateStatus.WORKING
    assert updated.active_ticket_id == "T053"
    assert updated.opencode_session_id == "sess-abc"
    assert updated.verification_attempts == 0
    assert updated.last_updated >= initial.last_updated


def test_transition_to_working_requires_non_empty_ticket_id() -> None:
    initial = RunnerState.idle()
    with pytest.raises(StateFormatError, match="ticket_id"):
        initial.to_working(ticket_id="")


def test_transition_to_gatekeeper_enforces_active_ticket() -> None:
    idle = RunnerState.idle()
    with pytest.raises(StateFormatError, match="Cannot transition to GATEKEEPER without active ticket"):
        idle.to_gatekeeper()


def test_transition_to_gatekeeper_immutability() -> None:
    working = RunnerState.idle().to_working(ticket_id="T053", session_id="sess-1")
    gatekeeper = working.to_gatekeeper(verification_attempts=2)

    assert working.status == StateStatus.WORKING
    assert gatekeeper.status == StateStatus.GATEKEEPER
    assert gatekeeper.active_ticket_id == "T053"
    assert gatekeeper.verification_attempts == 2
    assert gatekeeper.last_updated >= working.last_updated


def test_transition_to_idle_resets_ticket_and_tokens() -> None:
    working = (
        RunnerState.idle()
        .to_working(ticket_id="T053", session_id="sess-1")
        .record_tokens(50000, warning_sent=True)
    )
    idle = working.to_idle()

    assert working.status == StateStatus.WORKING
    assert working.tokens.current == 50000

    assert idle.status == StateStatus.IDLE
    assert idle.active_ticket_id is None
    assert idle.opencode_session_id is None
    assert idle.tokens.current == 0
    assert idle.tokens.warning_sent is False
    assert idle.verification_attempts == 0
    assert idle.last_checkpoint is None


def test_transition_to_pause_requested() -> None:
    working = RunnerState.idle().to_working(ticket_id="T053")
    paused = working.to_pause_requested()

    assert working.status == StateStatus.WORKING
    assert paused.status == StateStatus.PAUSE_REQUESTED
    assert paused.active_ticket_id == "T053"


def test_transition_to_waiting_for_user() -> None:
    working = RunnerState.idle().to_working(ticket_id="T053")
    waiting = working.to_waiting_for_user()

    assert waiting.status == StateStatus.WAITING_FOR_USER
    assert waiting.active_ticket_id == "T053"


def test_transition_to_circuit_breaker_tripped() -> None:
    working = RunnerState.idle().to_working(ticket_id="T053")
    tripped = working.to_circuit_breaker_tripped()

    assert tripped.status == StateStatus.CIRCUIT_BREAKER_TRIPPED
    assert tripped.active_ticket_id == "T053"


def test_record_tokens_validates_non_negative() -> None:
    state = RunnerState.idle()
    updated = state.record_tokens(85000)
    assert updated.tokens.current == 85000
    assert updated.tokens.warning_sent is False

    with pytest.raises(StateFormatError, match="non-negative integer"):
        state.record_tokens(-5)


def test_set_presence_mode_validates() -> None:
    state = RunnerState.idle()
    away = state.set_presence_mode("away")
    assert away.presence_mode == "away"

    nearby = away.set_presence_mode("nearby")
    assert nearby.presence_mode == "nearby"

    with pytest.raises(StateFormatError, match="presence_mode"):
        state.set_presence_mode("offline")


def test_set_tui_open_and_clear_tui() -> None:
    working = RunnerState.idle().to_working(ticket_id="T053", session_id="sess-xyz")
    tui_state = working.set_tui_open()

    assert tui_state.tui_open is True
    assert tui_state.tui_session_id == "sess-xyz"

    cleared = tui_state.clear_tui()
    assert cleared.tui_open is False
    assert cleared.tui_session_id is None
