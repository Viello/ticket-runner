"""Unit tests for Antigravity worker adapter: command construction, event decoding, and wire models (T018)."""

import json
import pytest

from runner.adapters.antigravity.antigravity_worker import (
    DEFAULT_PRINT_TIMEOUT,
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
        "0",
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
        "0",
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
        "0",
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
        "0",
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
        "0",
    ]


def test_build_antigravity_run_command_with_all_options() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        session_id="d3336873-0561-4a98-b9a9-13da3c00b3af",
        model_id="gemini-pro",
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
        "gemini-pro",
        "--effort",
        "medium",
        "--print-timeout",
        "30s",
    ]


@pytest.mark.parametrize(
    ("model_slug", "expected_base_model"),
    [
        ("gemini-3.8-flash-high", "gemini-3.8-flash"),
        ("gemini-3.8-flash-medium", "gemini-3.8-flash"),
        ("gemini-3.8-flash-low", "gemini-3.8-flash"),
        ("gemini-4-argon-medium", "gemini-4-argon"),
        ("gemini-4-argon-high", "gemini-4-argon"),
        ("gemini-4-argon-low", "gemini-4-argon"),
        ("claude-opus-5-5-high", "claude-opus-5-5"),
        ("claude-sonnet-5-5-high", "claude-sonnet-5-5"),
        ("custom-model-xhigh", "custom-model"),
        ("custom-model-max", "custom-model"),
        ("GEMINI-3.8-FLASH-HIGH", "GEMINI-3.8-FLASH"),
    ],
)
def test_build_antigravity_run_command_normalizes_model_and_passes_effort(
    model_slug: str,
    expected_base_model: str,
) -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        model_id=model_slug,
        variant="medium",
    )
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == expected_base_model
    assert "--effort" in cmd
    effort_idx = cmd.index("--effort")
    assert cmd[effort_idx + 1] == "medium"


def test_build_antigravity_run_command_retains_model_without_effort_when_variant_omitted() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        model_id="gemini-3.8-flash-high",
        variant=None,
    )
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "gemini-3.8-flash-high"
    assert "--effort" not in cmd


def test_build_antigravity_run_command_includes_effort_when_model_has_no_effort_suffix() -> None:
    cmd = build_antigravity_run_command(
        prompt="Implement ticket T018",
        model_id="gemini-pro",
        variant="medium",
    )
    assert "--model" in cmd
    assert "gemini-pro" in cmd
    assert "--effort" in cmd
    assert "medium" in cmd


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
        "0",
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
    assert cmd[6] == "0"
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
        total=None,
    )
    assert event.token_usage.occupancy == 21466


def test_decode_event_step_update_computes_true_context_occupancy_with_total_none() -> None:
    """In agy, step_update.usage.total_tokens omits cache_read_tokens and thinking_tokens.

    Setting total=None allows TokenUsage.occupancy to reflect the true context window
    (input + output + reasoning + cache_read + cache_write) per ADR 0015.
    """
    payload = {
        "event": "step_update",
        "step_update": {
            "conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af",
            "step_index": 1,
            "state": "DONE",
            "step_type": "agent_response",
            "text_delta": "PONG\n",
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 300,
                "thinking_tokens": 500,
                "cache_read_tokens": 35000,
                "cache_write_tokens": 20,
                "total_tokens": 1500,  # agy wire total = input + output only
            },
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.token_usage is not None
    assert event.token_usage.total is None
    # True occupancy includes cached prompt (35k) and thinking (500)
    assert event.token_usage.occupancy == 1200 + 300 + 500 + 35000 + 20



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


# --- Print Timeout Default (regression: truncated Worker turns) ---


def test_default_print_timeout_waits_for_turn_completion() -> None:
    """The default print timeout must not truncate a long turn (agy: 0 waits until done)."""
    assert DEFAULT_PRINT_TIMEOUT == "0"

    cmd = build_antigravity_run_command("Implement ticket T018")
    assert cmd[-2:] == ["--print-timeout", "0"]
    assert "5s" not in cmd


# --- Empty-Success Anomaly Detection ---


def test_decode_event_flags_empty_success_result_as_anomaly() -> None:
    """A SUCCESS result with an empty response and zero usage is surfaced as an anomaly."""
    payload = {
        "event": "result",
        "result": {
            "conversation_id": "d3336873-0561-4a98-b9a9-13da3c00b3af",
            "status": "SUCCESS",
            "response": "",
            "duration_seconds": 0,
            "num_turns": 1,
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "thinking_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 0,
            },
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.anomaly is not None
    assert "zero token usage" in event.anomaly
    assert "empty response" in event.anomaly


def test_decode_event_does_not_flag_productive_success_result() -> None:
    """A SUCCESS result that consumed tokens is a normal turn, not an anomaly."""
    payload = {
        "event": "result",
        "result": {
            "status": "SUCCESS",
            "response": "PROBE_OK\n",
            "usage": {"input_tokens": 13874, "output_tokens": 64, "total_tokens": 13938},
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.anomaly is None


def test_decode_event_does_not_flag_zero_usage_failure_result() -> None:
    """A non-SUCCESS result is not anomalous even with zero usage."""
    payload = {
        "event": "result",
        "result": {
            "status": "FAILED",
            "response": "",
            "usage": {"total_tokens": 0},
        },
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.anomaly is None


def test_decode_event_does_not_flag_zero_usage_non_result_events() -> None:
    """Only 'result' events are eligible for the empty-success anomaly."""
    payload = {
        "event": "step_update",
        "step_update": {"state": "DONE", "usage": {"total_tokens": 0}},
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.anomaly is None


def test_decode_event_flags_success_result_with_absent_usage_as_anomaly() -> None:
    """A SUCCESS result with no usage block and an empty response is still anomalous."""
    payload = {
        "event": "result",
        "result": {"status": "SUCCESS", "response": ""},
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.anomaly is not None
    assert "absent token usage" in event.anomaly


def test_decode_event_does_not_flag_success_result_without_usage_but_with_response() -> None:
    """A SUCCESS result missing usage but carrying a response is not treated as anomalous."""
    payload = {
        "event": "result",
        "result": {"status": "SUCCESS", "response": "did work\n"},
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    assert event.anomaly is None


def test_decode_event_judges_anomaly_on_result_usage_not_sibling_envelope() -> None:
    """The anomaly verdict uses the result envelope's own usage, not a sibling envelope's."""
    payload = {
        "event": "result",
        "step_update": {"usage": {"input_tokens": 999, "total_tokens": 999}},
        "result": {"status": "SUCCESS", "response": "", "usage": {"total_tokens": 0}},
    }
    event = decode_event(json.dumps(payload))
    assert event is not None
    # Cumulative token_usage still resolves from step_update first ...
    assert event.token_usage is not None and event.token_usage.occupancy == 999
    # ... but the anomaly is judged on the result's own zero usage.
    assert event.anomaly is not None
