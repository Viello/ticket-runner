"""Unit tests for OpenCode worker wire adapter: event decoding and command construction."""

import json
import pytest

from runner.adapters.opencode.opencode_worker import (
    KNOWN_EVENT_TYPES,
    OpenCodeEvent,
    build_opencode_run_command,
    decode_event,
)
from runner.domain.telemetry import TokenUsage


# --- Command Construction Tests ---


def test_build_opencode_run_command_new_session() -> None:
    cmd = build_opencode_run_command("Implement ticket T019")
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--auto",
        "Implement ticket T019",
    ]


def test_build_opencode_run_command_resumed_session() -> None:
    cmd = build_opencode_run_command(
        prompt="Continue ticket T019",
        session_id="ses_01ABC123",
    )
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        "ses_01ABC123",
        "--auto",
        "Continue ticket T019",
    ]


def test_build_opencode_run_command_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        build_opencode_run_command("")

    with pytest.raises(TypeError, match="Prompt must be a string"):
        build_opencode_run_command(123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Invalid session ID"):
        build_opencode_run_command("prompt", session_id="invalid_session")

    with pytest.raises(ValueError, match="Invalid session ID"):
        build_opencode_run_command("prompt", session_id="../../escape")


# --- Event Decoding Tests ---


def test_decode_event_step_start() -> None:
    raw_line = json.dumps({
        "type": "step_start",
        "timestamp": 1789564162744,
        "sessionID": "ses_f55aa0e33ffeUDl1DvFKlpFsPO",
        "part": {
            "id": "prt_0aa5612b20019IAXa0WUIhYPUD",
            "type": "step-start",
        },
    })
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "step_start"
    assert event.session_id == "ses_f55aa0e33ffeUDl1DvFKlpFsPO"
    assert event.timestamp == 1789564162744
    assert event.is_known is True
    assert event.token_usage is None


def test_decode_event_text() -> None:
    raw_line = json.dumps({
        "type": "text",
        "timestamp": 1789564163486,
        "sessionID": "ses_f55aa0e33ffeUDl1DvFKlpFsPO",
        "part": {
            "type": "text",
            "text": "Hello world",
        },
    })
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "text"
    assert event.session_id == "ses_f55aa0e33ffeUDl1DvFKlpFsPO"
    assert event.is_known is True
    assert event.part is not None
    assert event.part.get("text") == "Hello world"


def test_decode_event_step_finish_with_nested_cache() -> None:
    # Realistic OpenCode v1.18.x payload with nested cache dictionary
    raw_line = json.dumps({
        "type": "step_finish",
        "timestamp": 1789564163987,
        "sessionID": "ses_f55aa0e33ffeUDl1DvFKlpFsPO",
        "part": {
            "type": "step-finish",
            "reason": "stop",
            "tokens": {
                "total": 125000,
                "input": 20000,
                "output": 5000,
                "reasoning": 1000,
                "cache": {
                    "write": 4000,
                    "read": 95000,
                },
            },
        },
    })
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "step_finish"
    assert event.session_id == "ses_f55aa0e33ffeUDl1DvFKlpFsPO"
    assert event.is_known is True
    assert event.token_usage is not None

    usage = event.token_usage
    assert isinstance(usage, TokenUsage)
    assert usage.input == 20000
    assert usage.output == 5000
    assert usage.reasoning == 1000
    assert usage.cache_write == 4000
    assert usage.cache_read == 95000
    assert usage.total == 125000
    assert usage.occupancy == 125000


def test_decode_event_step_finish_flat_tokens() -> None:
    # Alternate schema with flat cache fields and no part wrapper
    raw_line = json.dumps({
        "type": "step_finish",
        "sessionID": "ses_test123",
        "tokens": {
            "input": 1000,
            "output": 200,
            "cache_read": 300,
            "cache_write": 50,
        },
    })
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "step_finish"
    assert event.session_id == "ses_test123"
    assert event.token_usage is not None
    assert event.token_usage.input == 1000
    assert event.token_usage.output == 200
    assert event.token_usage.cache_read == 300
    assert event.token_usage.cache_write == 50
    assert event.token_usage.total is None
    assert event.token_usage.occupancy == 1550


def test_decode_event_unknown_type_marks_not_known() -> None:
    raw_line = json.dumps({
        "type": "future_opencode_event",
        "sessionID": "ses_test123",
        "data": {"custom": True},
    })
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "future_opencode_event"
    assert event.is_known is False
    assert event.type not in KNOWN_EVENT_TYPES
    assert event.session_id == "ses_test123"


def test_decode_event_unparseable_and_invalid_lines_return_none() -> None:
    assert decode_event("{broken json") is None
    assert decode_event("") is None
    assert decode_event("   \r\n") is None
    assert decode_event('"just a json string"') is None
    assert decode_event("12345") is None
    assert decode_event("[1, 2, 3]") is None
    assert decode_event('{"no_type_key": 1}') is None
    assert decode_event('{"type": 123}') is None


def test_decode_event_oversized_line_returns_none() -> None:
    oversized = '{"type":"text","payload":"' + ("x" * 6_000_000) + '"}'
    assert decode_event(oversized) is None


def test_decode_event_crlf_tolerance() -> None:
    raw_line = '{"type":"step_start","sessionID":"ses_123"}\r\n'
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "step_start"
    assert event.session_id == "ses_123"
