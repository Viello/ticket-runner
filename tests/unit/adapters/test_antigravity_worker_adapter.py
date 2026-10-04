"""Unit tests for Antigravity worker adapter: command construction, event decoding, and wire models (T018)."""

import json
import pytest

from runner.adapters.antigravity.antigravity_worker import (
    AntigravityWorker,
    AntigravityWorkerCli,
    build_antigravity_run_command,
    decode_event,
    extract_resource_access,
)
from runner.domain.telemetry import TokenUsage, WorkerEvent
from runner.ports.agent_worker import AgentWorker


# --- Protocol Conformance ---


def test_antigravity_worker_conforms_to_agent_worker_protocol() -> None:
    worker = AntigravityWorker()
    assert isinstance(worker, AgentWorker)


def test_antigravity_worker_cli_subclass() -> None:
    worker = AntigravityWorkerCli()
    assert isinstance(worker, AgentWorker)
    assert hasattr(worker, "build_run_command")
    assert hasattr(worker, "decode_event")
    assert hasattr(worker, "extract_resource_access")


# --- Command Construction Tests ---


def test_build_antigravity_run_command_basic() -> None:
    cmd = build_antigravity_run_command("Implement ticket T018")
    assert cmd == [
        "agy",
        "-p",
        "Implement ticket T018",
        "--output-format",
        "stream-json",
        "--print-timeout",
        "5s",
    ]


def test_build_antigravity_run_command_with_conversation_uuid() -> None:
    cmd = build_antigravity_run_command(
        prompt="Continue ticket T018",
        session_id="d3336873-0561-4a98-b9a9-13da3c00b3af",
    )
    assert cmd == [
        "agy",
        "-p",
        "Continue ticket T018",
        "--output-format",
        "stream-json",
        "--conversation",
        "d3336873-0561-4a98-b9a9-13da3c00b3af",
        "--print-timeout",
        "5s",
    ]


def test_build_antigravity_run_command_with_continue_flag() -> None:
    cmd = build_antigravity_run_command(
        prompt="Continue most recent session",
        session_id="continue",
    )
    assert cmd == [
        "agy",
        "-p",
        "Continue most recent session",
        "--output-format",
        "stream-json",
        "--continue",
        "--print-timeout",
        "5s",
    ]


def test_build_antigravity_run_command_with_model() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        model_id="gemini-3.8-flash-low",
    )
    assert cmd == [
        "agy",
        "-p",
        "Implement ticket T018",
        "--output-format",
        "stream-json",
        "--model",
        "gemini-3.8-flash-low",
        "--print-timeout",
        "5s",
    ]


def test_build_antigravity_run_command_with_effort_variant() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        variant="high",
    )
    assert cmd == [
        "agy",
        "-p",
        "Implement ticket T018",
        "--output-format",
        "stream-json",
        "--effort",
        "high",
        "--print-timeout",
        "5s",
    ]


def test_build_antigravity_run_command_with_all_options() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        session_id="d3336873-0561-4a98-b9a9-13da3c00b3af",
        model_id="gemini-3.8-flash-low",
        variant="medium",
        print_timeout="30s",
    )
    assert cmd == [
        "agy",
        "-p",
        "Implement ticket T018",
        "--output-format",
        "stream-json",
        "--conversation",
        "d3336873-0561-4a98-b9a9-13da3c00b3af",
        "--model",
        "gemini-3.8-flash-low",
        "--effort",
        "medium",
        "--print-timeout",
        "30s",
    ]


def test_build_antigravity_run_command_adapter_instance_delegates() -> None:
    worker = AntigravityWorker()
    cmd = worker.build_run_command(
        prompt="Execute task",
        session_id="continue",
        variant="low",
        model_id="gemini-flash",
    )
    assert cmd == [
        "agy",
        "-p",
        "Execute task",
        "--output-format",
        "stream-json",
        "--continue",
        "--model",
        "gemini-flash",
        "--effort",
        "low",
        "--print-timeout",
        "5s",
    ]


# --- Security & Validation Tests ---


def test_build_antigravity_run_command_security_parameterization() -> None:
    malicious_prompt = "; rm -rf / ; cat /etc/passwd && echo 'hacked' | bash"
    cmd = build_antigravity_run_command(malicious_prompt)
    assert cmd[0] == "agy"
    assert cmd[1] == "-p"
    assert cmd[2] == malicious_prompt
    assert cmd[3] == "--output-format"
    assert cmd[4] == "stream-json"
    assert cmd[5] == "--print-timeout"
    assert cmd[6] == "5s"
    assert len(cmd) == 7


def test_build_antigravity_run_command_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        build_antigravity_run_command("")

    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        build_antigravity_run_command("   ")

    with pytest.raises(TypeError, match="Prompt must be a string"):
        build_antigravity_run_command(123)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Session ID must be a string"):
        build_antigravity_run_command("prompt", session_id=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Session ID cannot be empty"):
        build_antigravity_run_command("prompt", session_id="   ")

    with pytest.raises(TypeError, match="Model ID must be a string"):
        build_antigravity_run_command("prompt", model_id=123)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Variant must be a string"):
        build_antigravity_run_command("prompt", variant=123)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="Print timeout must be a string"):
        build_antigravity_run_command("prompt", print_timeout=123)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Print timeout cannot be empty"):
        build_antigravity_run_command("prompt", print_timeout="   ")


# --- Event Decoding Tests ---


def test_decode_event_empty_or_invalid() -> None:
    assert decode_event("") is None
    assert decode_event("   \n") is None
    assert decode_event(123) is None  # type: ignore[arg-type]
    assert decode_event("not-json-line\n") is None
    assert decode_event("[]\n") is None
    assert decode_event('"just a string"\n') is None
    assert decode_event("{}\n") is None


def test_decode_event_oversized_line() -> None:
    huge_line = '{"event": "step_update", "step_update": {"text_delta": "' + ("x" * 5_000_001) + '"}}\n'
    assert decode_event(huge_line) is None


def test_decode_event_closed_allowlist() -> None:
    # Known closed set
    for event_name in ("init", "step_update", "result"):
        line = json.dumps({"event": event_name, "conversation_id": "ses_001"})
        event = decode_event(line)
        assert event is not None
        assert event.type == event_name
        assert event.is_known is True

    # Unknown or OpenCode-only event types are marked is_known=False
    for unknown_name in ("text", "step_start", "step_finish", "tool_call", "tool_result", "heartbeat"):
        line = json.dumps({"event": unknown_name, "conversation_id": "ses_001"})
        event = decode_event(line)
        assert event is not None
        assert event.type == unknown_name
        assert event.is_known is False


def test_decode_event_init() -> None:
    payload = {
        "event": "init",
        "conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af",
        "init": {
            "model": "gemini-3.8-flash-low",
            "cwd": "D:\\Projects",
            "tools": ["run_command", "view_file"],
            "permission_mode": "always-proceed",
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert isinstance(event, WorkerEvent)
    assert event.type == "init"
    assert event.session_id == "d3336873-0561-4a98-b9a9-13da3c00b3af"
    assert event.is_known is True
    assert event.part == payload["init"]
    assert event.raw == payload


def test_decode_event_step_update_with_usage() -> None:
    payload = {
        "event": "step_update",
        "step_update": {
            "conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af",
            "step_index": 1,
            "state": "DONE",
            "step_type": "agent_response",
            "text_delta": "PONG\n",
            "duration_seconds": 2.03,
            "usage": {
                "input_tokens": 21299,
                "output_tokens": 2,
                "thinking_tokens": 100,
                "cache_read_tokens": 50,
                "cache_write_tokens": 15,
                "total_tokens": 21466,
            },
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.type == "step_update"
    assert event.session_id == "d3336873-0561-4a98-b9a9-13da3c00b3af"
    assert event.token_usage == TokenUsage(
        input=21299,
        output=2,
        reasoning=100,
        cache_read=50,
        cache_write=15,
        total=21466,
    )


def test_decode_event_result_with_usage() -> None:
    payload = {
        "event": "result",
        "result": {
            "conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af",
            "status": "SUCCESS",
            "response": "PONG\n",
            "duration_seconds": 3.68,
            "num_turns": 1,
            "usage": {
                "input_tokens": 21299,
                "output_tokens": 2,
                "thinking_tokens": 0,
                "cache_read_tokens": 0,
                "total_tokens": 21301,
            },
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.type == "result"
    assert event.session_id == "d3336873-0561-4a98-b9a9-13da3c00b3af"
    assert event.token_usage == TokenUsage(
        input=21299,
        output=2,
        reasoning=0,
        cache_read=0,
        cache_write=0,
        total=21301,
    )


def test_decode_event_ignores_top_level_usage() -> None:
    payload = {
        "event": "step_update",
        "usage": {
            "input_tokens": 9999,
            "output_tokens": 99,
            "total_tokens": 10098,
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.token_usage is None


def test_decode_event_nested_conversation_id() -> None:
    p1 = {
        "event": "step_update",
        "step_update": {"conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af"},
    }
    assert decode_event(json.dumps(p1)).session_id == "d3336873-0561-4a98-b9a9-13da3c00b3af"  # type: ignore[union-attr]

    p2 = {
        "event": "result",
        "result": {"conversation_id": "edb1c8c1-50ba-4f3f-87eb-412d0e9d47c3"},
    }
    assert decode_event(json.dumps(p2)).session_id == "edb1c8c1-50ba-4f3f-87eb-412d0e9d47c3"  # type: ignore[union-attr]


def test_decode_event_via_worker_instance() -> None:
    worker = AntigravityWorker()
    line = json.dumps({"event": "step_update", "conversation_id": "ses_test"})
    event = worker.decode_event(line)
    assert event is not None
    assert event.type == "step_update"
    assert event.session_id == "ses_test"


# --- Resource Access Extraction Tests ---


def test_extract_resource_access_from_raw_line() -> None:
    line = "Reading .agents/skills/implement/SKILL.md and AGENTS.md for context"
    resources = extract_resource_access(raw_line=line)
    assert resources == frozenset({"implement", "AGENTS.md"})


def test_extract_resource_access_windows_backslashes() -> None:
    line = r"Reading .agents\skills\code-review\skill.md"
    resources = extract_resource_access(raw_line=line)
    assert resources == frozenset({"code-review"})


def test_extract_resource_access_from_step_update_tool_info() -> None:
    payload = {
        "event": "step_update",
        "step_update": {
            "conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af",
            "step_index": 4,
            "state": "DONE",
            "step_type": "tool",
            "tool_name": "view_file",
            "tool_info": {
                "name": "view_file",
                "parameters": {
                    "AbsolutePath": ".agents/skills/security-review/SKILL.md",
                    "guide": "AGENTS.md",
                },
            },
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    resources = extract_resource_access(event=event)
    assert resources == frozenset({"security-review", "AGENTS.md"})


def test_extract_resource_access_nested_parameters() -> None:
    payload = {
        "event": "step_update",
        "step_update": {
            "step_type": "tool",
            "tool_name": "run_command",
            "tool_info": {
                "name": "run_command",
                "parameters": {
                    "args": ["python", ".agents/skills/implement/SKILL.md"],
                },
            },
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    resources = extract_resource_access(event=event)
    assert resources == frozenset({"implement"})


def test_extract_resource_access_via_worker_instance() -> None:
    worker = AntigravityWorker()
    line = "Checked AGENTS.md guidelines"
    resources = worker.extract_resource_access(raw_line=line)
    assert resources == frozenset({"AGENTS.md"})


def test_extract_resource_access_empty() -> None:
    assert extract_resource_access() == frozenset()
    assert extract_resource_access(raw_line="Just regular output") == frozenset()
