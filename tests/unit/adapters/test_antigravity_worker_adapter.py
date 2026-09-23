"""Unit tests for Antigravity worker adapter: command construction, event decoding, and wire models (T095)."""

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
    cmd = build_antigravity_run_command("Implement ticket T095")
    assert cmd == [
        "agy",
        "run",
        "--auto",
        "Implement ticket T095",
    ]
    assert cmd[:3] == ["agy", "run", "--auto"]


def test_build_antigravity_run_command_with_session() -> None:
    cmd = build_antigravity_run_command(
        prompt="Continue ticket T095",
        session_id="ses_antigravity123",
    )
    assert cmd == [
        "agy",
        "run",
        "--auto",
        "Continue ticket T095",
        "--session",
        "ses_antigravity123",
    ]
    assert cmd[:3] == ["agy", "run", "--auto"]


def test_build_antigravity_run_command_with_model() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T095",
        model_id="gemini-2.5-pro",
    )
    assert cmd == [
        "agy",
        "run",
        "--auto",
        "Implement ticket T095",
        "-m",
        "gemini-2.5-pro",
    ]


def test_build_antigravity_run_command_with_variant() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T095",
        variant="high",
    )
    assert cmd == [
        "agy",
        "run",
        "--auto",
        "Implement ticket T095",
        "--variant",
        "high",
    ]


def test_build_antigravity_run_command_with_all_options() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T095",
        session_id="ses_abc999",
        model_id="gemini-2.5-flash",
        variant="medium",
    )
    assert cmd == [
        "agy",
        "run",
        "--auto",
        "Implement ticket T095",
        "--session",
        "ses_abc999",
        "-m",
        "gemini-2.5-flash",
        "--variant",
        "medium",
    ]
    assert cmd[:3] == ["agy", "run", "--auto"]


def test_build_antigravity_run_command_adapter_instance_delegates() -> None:
    worker = AntigravityWorker()
    cmd = worker.build_run_command(
        prompt="Execute task",
        session_id="ses_001",
        variant="low",
        model_id="gemini-flash",
    )
    assert cmd == [
        "agy",
        "run",
        "--auto",
        "Execute task",
        "--session",
        "ses_001",
        "-m",
        "gemini-flash",
        "--variant",
        "low",
    ]


# --- Security & Validation Tests ---


def test_build_antigravity_run_command_security_parameterization() -> None:
    malicious_prompt = "; rm -rf / ; cat /etc/passwd && echo 'hacked' | bash"
    cmd = build_antigravity_run_command(malicious_prompt)
    assert cmd[0] == "agy"
    assert cmd[1] == "run"
    assert cmd[2] == "--auto"
    assert cmd[3] == malicious_prompt
    assert len(cmd) == 4


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


# --- Event Decoding Tests ---


def test_decode_event_empty_or_invalid() -> None:
    assert decode_event("") is None
    assert decode_event("   \n") is None
    assert decode_event(123) is None  # type: ignore[arg-type]
    assert decode_event("not-json-line\n") is None
    assert decode_event("[]\n") is None
    assert decode_event('"just a string"\n') is None


def test_decode_event_oversized_line() -> None:
    huge_line = '{"type": "text", "content": "' + ("x" * 5_000_001) + '"}\n'
    assert decode_event(huge_line) is None


def test_decode_event_valid_json() -> None:
    payload = {
        "type": "text",
        "sessionId": "ses_agy_001",
        "timestamp": 1711234567,
        "content": "Processing ticket...",
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert isinstance(event, WorkerEvent)
    assert event.type == "text"
    assert event.session_id == "ses_agy_001"
    assert event.timestamp == 1711234567
    assert event.is_known is True
    assert event.raw == payload


def test_decode_event_session_id_variants() -> None:
    p1 = {"type": "step_start", "session_id": "ses_snake"}
    assert decode_event(json.dumps(p1)).session_id == "ses_snake"  # type: ignore[union-attr]

    p2 = {"type": "step_start", "sessionID": "ses_upper"}
    assert decode_event(json.dumps(p2)).session_id == "ses_upper"  # type: ignore[union-attr]

    p3 = {"type": "step_start", "conversation_id": "ses_conv"}
    assert decode_event(json.dumps(p3)).session_id == "ses_conv"  # type: ignore[union-attr]


def test_decode_event_token_usage_extraction() -> None:
    payload = {
        "type": "step_finish",
        "session_id": "ses_agy_001",
        "tokens": {
            "input": 5000,
            "output": 1200,
            "reasoning": 800,
            "cache": {
                "read": 3000,
                "write": 500,
            },
            "total": 9500,
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.token_usage == TokenUsage(
        input=5000,
        output=1200,
        reasoning=800,
        cache_read=3000,
        cache_write=500,
        total=9500,
    )


def test_decode_event_via_worker_instance() -> None:
    worker = AntigravityWorker()
    line = json.dumps({"type": "step_start", "session_id": "ses_test"})
    event = worker.decode_event(line)
    assert event is not None
    assert event.type == "step_start"
    assert event.session_id == "ses_test"


# --- Resource Access Extraction Tests ---


def test_extract_resource_access_from_raw_line() -> None:
    line = 'Reading .agents/skills/implement/SKILL.md and AGENTS.md for context'
    resources = extract_resource_access(raw_line=line)
    assert resources == frozenset({"implement", "AGENTS.md"})


def test_extract_resource_access_windows_backslashes() -> None:
    line = r'Reading .agents\skills\code-review\skill.md'
    resources = extract_resource_access(raw_line=line)
    assert resources == frozenset({"code-review"})


def test_extract_resource_access_from_event() -> None:
    payload = {
        "type": "tool_call",
        "tool": "read_file",
        "args": {"path": ".agents/skills/security-review/SKILL.md"},
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    resources = extract_resource_access(event=event)
    assert resources == frozenset({"security-review"})


def test_extract_resource_access_via_worker_instance() -> None:
    worker = AntigravityWorker()
    line = "Checked AGENTS.md guidelines"
    resources = worker.extract_resource_access(raw_line=line)
    assert resources == frozenset({"AGENTS.md"})


def test_extract_resource_access_empty() -> None:
    assert extract_resource_access() == frozenset()
    assert extract_resource_access(raw_line="Just regular output") == frozenset()
