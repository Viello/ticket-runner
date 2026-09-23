"""Unit tests for OpenCode worker wire adapter: event decoding and command construction."""

import json
import pytest

from runner.adapters.opencode.opencode_worker import (
    KNOWN_EVENT_TYPES,
    OpenCodeEvent,
    OpenCodeWorker,
    OpenCodeWorkerCli,
    build_opencode_run_command,
    decode_event,
    extract_resource_access,
)
from runner.domain.telemetry import TokenUsage, WorkerEvent
from runner.ports.agent_worker import AgentWorker


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


def test_build_opencode_run_command_with_variant() -> None:
    cmd = build_opencode_run_command("p", variant="high")
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--variant",
        "high",
        "--auto",
        "p",
    ]


def test_build_opencode_run_command_with_session_and_variant() -> None:
    cmd = build_opencode_run_command("p", session_id="ses_01ABC123", variant="high")
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        "ses_01ABC123",
        "--variant",
        "high",
        "--auto",
        "p",
    ]


@pytest.mark.parametrize("empty_variant", ["", "   ", None])
def test_build_opencode_run_command_omits_empty_or_none_variant(
    empty_variant: str | None,
) -> None:
    cmd = build_opencode_run_command("p", variant=empty_variant)
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--auto",
        "p",
    ]


@pytest.mark.parametrize("invalid_variant", [123, True, False, ["high"], {"variant": "high"}])
def test_build_opencode_run_command_rejects_non_str_variant(invalid_variant: object) -> None:
    with pytest.raises(TypeError, match="Variant must be a string"):
        build_opencode_run_command("p", variant=invalid_variant)  # type: ignore[arg-type]


def test_build_opencode_run_command_preserves_variant_as_single_token() -> None:
    untrusted = "custom-variant; rm -rf /"
    cmd = build_opencode_run_command("p", variant=untrusted)
    assert cmd[4] == "--variant"
    assert cmd[5] == "custom-variant; rm -rf /"
    assert cmd[6] == "--auto"
    assert cmd[7] == "p"


@pytest.mark.parametrize(
    ("model_id", "variant", "expected_flags"),
    [
        # Model only: adds -m before --auto
        ("qwen/qwen-plus", None, ["-m", "qwen/qwen-plus"]),
        ("qwen/qwen-plus", "", ["-m", "qwen/qwen-plus"]),
        ("qwen/qwen-plus", "   ", ["-m", "qwen/qwen-plus"]),
        # Variant only: adds --variant before --auto
        (None, "high", ["--variant", "high"]),
        ("", "high", ["--variant", "high"]),
        ("   ", "high", ["--variant", "high"]),
        # Both: adds -m then --variant before --auto
        ("qwen/qwen-plus", "medium", ["-m", "qwen/qwen-plus", "--variant", "medium"]),
        # Neither: adds neither
        (None, None, []),
        ("", "", []),
        ("   ", "   ", []),
        (None, "", []),
        ("", None, []),
    ],
)
def test_build_opencode_run_command_model_and_variant_token_matrix(
    model_id: str | None,
    variant: str | None,
    expected_flags: list[str],
) -> None:
    cmd = build_opencode_run_command("p", model_id=model_id, variant=variant)
    expected = ["opencode", "run", "--format", "json"] + expected_flags + ["--auto", "p"]
    assert cmd == expected


def test_build_opencode_run_command_with_session_and_model_and_variant() -> None:
    cmd = build_opencode_run_command(
        "p",
        session_id="ses_01ABC123",
        model_id="anthropic/claude-3-5-sonnet",
        variant="high",
    )
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        "ses_01ABC123",
        "-m",
        "anthropic/claude-3-5-sonnet",
        "--variant",
        "high",
        "--auto",
        "p",
    ]


@pytest.mark.parametrize("invalid_model", [123, True, False, ["qwen"], {"model": "qwen"}])
def test_build_opencode_run_command_rejects_non_str_model(invalid_model: object) -> None:
    with pytest.raises(TypeError, match="Model ID must be a string"):
        build_opencode_run_command("p", model_id=invalid_model)  # type: ignore[arg-type]


def test_build_opencode_run_command_preserves_model_as_single_token() -> None:
    untrusted = "custom-model; rm -rf /"
    cmd = build_opencode_run_command("p", model_id=untrusted)
    assert cmd[4] == "-m"
    assert cmd[5] == "custom-model; rm -rf /"
    assert cmd[6] == "--auto"
    assert cmd[7] == "p"




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


def test_decode_event_tool_use_is_known() -> None:
    assert "tool_use" in KNOWN_EVENT_TYPES
    raw_line = json.dumps({
        "type": "tool_use",
        "sessionID": "ses_tool123",
        "timestamp": 1789564165000,
        "part": {
            "id": "prt_tool1",
            "type": "tool_use",
            "tool": "read",
            "input": {"filePath": ".agents/skills/implement/SKILL.md"},
        },
    })
    event = decode_event(raw_line)
    assert event is not None
    assert event.type == "tool_use"
    assert event.is_known is True
    assert event.session_id == "ses_tool123"
    assert event.part is not None
    assert event.part.get("tool") == "read"


# --- Resource Access Detection Tests ---


def test_extract_resource_access_read_tool_skills() -> None:
    # POSIX relative path
    event1 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "read",
            "input": {"filePath": ".agents/skills/implement/SKILL.md"},
        },
    }))
    assert extract_resource_access(event1) == frozenset({"implement"})

    # Windows mixed/backslash absolute path
    event2 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "read",
            "input": {"filePath": r"D:\Projects\.agents\skills\code-review\SKILL.md"},
        },
    }))
    assert extract_resource_access(event2) == frozenset({"code-review"})

    # Nested OpenCode state input structure
    event3 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "read",
            "state": {
                "input": {"filePath": "d:/projects/.agents/skills/security-review/skill.md"},
            },
        },
    }))
    assert extract_resource_access(event3) == frozenset({"security-review"})

    # Alternative argument keys (file_path, path)
    event4 = decode_event(json.dumps({
        "type": "tool_call",
        "part": {
            "name": "read",
            "args": {"path": ".agents/skills/diagnosing-bugs/SKILL.md"},
        },
    }))
    assert extract_resource_access(event4) == frozenset({"diagnosing-bugs"})


def test_extract_resource_access_read_tool_agents_md() -> None:
    # Relative AGENTS.md
    event1 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "read",
            "input": {"filePath": "AGENTS.md"},
        },
    }))
    assert extract_resource_access(event1) == frozenset({"AGENTS.md"})

    # Absolute Windows path
    event2 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "read",
            "input": {"filePath": r"D:\Projects\AGENTS.md"},
        },
    }))
    assert extract_resource_access(event2) == frozenset({"AGENTS.md"})

    # Lowercase / mixed case
    event3 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "read",
            "input": {"filePath": "./agents.md"},
        },
    }))
    assert extract_resource_access(event3) == frozenset({"AGENTS.md"})


def test_extract_resource_access_bash_tool_commands() -> None:
    # cat with POSIX path
    event1 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "bash",
            "input": {"command": "cat .agents/skills/diagnosing-bugs/SKILL.md"},
        },
    }))
    assert extract_resource_access(event1) == frozenset({"diagnosing-bugs"})

    # PowerShell Get-Content with Windows path
    event2 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "bash",
            "input": {"command": r"Get-Content D:\Projects\AGENTS.md"},
        },
    }))
    assert extract_resource_access(event2) == frozenset({"AGENTS.md"})

    # cmd type command
    event3 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "bash",
            "input": {"command": r"type .agents\skills\implement\SKILL.md"},
        },
    }))
    assert extract_resource_access(event3) == frozenset({"implement"})

    # Command inspecting multiple resources
    event4 = decode_event(json.dumps({
        "type": "tool_use",
        "part": {
            "tool": "bash",
            "input": {"command": "head -n 20 AGENTS.md .agents/skills/code-review/SKILL.md"},
        },
    }))
    assert extract_resource_access(event4) == frozenset({"AGENTS.md", "code-review"})


def test_extract_resource_access_fallback_stream_line() -> None:
    # Unstructured event string with skill path
    raw_line1 = '{"event": "agent_action", "detail": "reading .agents/skills/security-review/SKILL.md"}'
    assert extract_resource_access(raw_line=raw_line1) == frozenset({"security-review"})

    # Escaped Windows path in raw JSON
    raw_line2 = r'{"type":"raw","msg":"inspecting D:\\Projects\\AGENTS.md before coding"}'
    assert extract_resource_access(raw_line2) == frozenset({"AGENTS.md"})

    # Dual invocation with both decoded event and raw line
    event = decode_event(json.dumps({
        "type": "tool_use",
        "part": {"tool": "read", "input": {"filePath": ".agents/skills/implement/SKILL.md"}},
    }))
    raw_line = '{"type":"tool_use","part":{"tool":"read","input":{"filePath":".agents/skills/implement/SKILL.md"}}}'
    assert extract_resource_access(event, raw_line) == frozenset({"implement"})


def test_extract_resource_access_edge_cases_and_seams() -> None:
    # Unrelated files and commands
    unrelated_event = decode_event(json.dumps({
        "type": "tool_use",
        "part": {"tool": "read", "input": {"filePath": "runner/adapters/opencode/opencode_worker.py"}},
    }))
    assert extract_resource_access(unrelated_event) == frozenset()

    unrelated_bash = decode_event(json.dumps({
        "type": "tool_use",
        "part": {"tool": "bash", "input": {"command": "pytest tests/unit"}},
    }))
    assert extract_resource_access(unrelated_bash) == frozenset()

    # Unrelated words containing agents
    assert extract_resource_access(raw_line="editing NOT_AGENTS.md and agents.md.bak") == frozenset()

    # None, empty, and invalid lines
    assert extract_resource_access(None) == frozenset()
    assert extract_resource_access("") == frozenset()
    assert extract_resource_access("   \n") == frozenset()
    assert extract_resource_access("{corrupt json") == frozenset()

    # Tolerant keyword argument passing
    assert extract_resource_access(event=None, raw_line="") == frozenset()

    # OpenCodeWorkerCli namespace seam
    assert OpenCodeWorkerCli.decode_event is decode_event
    assert OpenCodeWorkerCli.extract_resource_access is extract_resource_access
    assert OpenCodeWorkerCli.build_run_command is build_opencode_run_command


# --- T094: AgentWorker Protocol Conformance & OpenCodeWorker Adapter Tests ---


def test_opencode_worker_protocol_conformance() -> None:
    worker = OpenCodeWorker()
    assert isinstance(worker, AgentWorker)
    assert OpenCodeEvent is WorkerEvent


def test_opencode_worker_maps_all_seven_event_types() -> None:
    worker = OpenCodeWorker()
    raw_payloads = [
        {"type": "step_start", "sessionID": "ses_01"},
        {"type": "step_finish", "sessionID": "ses_01", "part": {"tokens": {"total": 5000}}},
        {"type": "text", "sessionID": "ses_01", "part": {"text": "hello"}},
        {"type": "tool_call", "sessionID": "ses_01", "part": {"tool": "read"}},
        {"type": "tool_use", "sessionID": "ses_01", "part": {"tool": "bash"}},
        {"type": "tool_result", "sessionID": "ses_01", "part": {"output": "ok"}},
        {"type": "error", "sessionID": "ses_01", "part": {"message": "failed"}},
    ]

    for payload in raw_payloads:
        line = json.dumps(payload)
        event = worker.decode_event(line)
        assert event is not None
        assert isinstance(event, WorkerEvent)
        assert event.type == payload["type"]
        assert event.session_id == "ses_01"
        assert event.is_known is True

    assert KNOWN_EVENT_TYPES == frozenset({
        "step_start",
        "step_finish",
        "text",
        "tool_call",
        "tool_use",
        "tool_result",
        "error",
    })


def test_opencode_worker_delegation() -> None:
    worker = OpenCodeWorker()
    cmd = worker.build_run_command("run tests", session_id="ses_abc123", variant="low", model_id="gpt-4")
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        "ses_abc123",
        "-m",
        "gpt-4",
        "--variant",
        "low",
        "--auto",
        "run tests",
    ]

    event = worker.decode_event('{"type": "text", "part": {"text": "inspecting AGENTS.md"}}\n')
    assert event is not None
    assert isinstance(event, WorkerEvent)

    detected = worker.extract_resource_access(event, raw_line='inspecting .agents/skills/implement/SKILL.md')
    assert detected == frozenset({"AGENTS.md", "implement"})


def test_opencode_worker_security_validation() -> None:
    worker = OpenCodeWorker()

    # Reject empty or whitespace prompt
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        worker.build_run_command("")
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        worker.build_run_command("   \t\n")

    # Reject non-string prompt
    with pytest.raises(TypeError, match="Prompt must be a string"):
        worker.build_run_command(None)  # type: ignore[arg-type]

    # Reject invalid session ID allowlist violations
    with pytest.raises(ValueError, match="Invalid session ID"):
        worker.build_run_command("prompt", session_id="ses_123; rm -rf /")

    with pytest.raises(ValueError, match="Invalid session ID"):
        worker.build_run_command("prompt", session_id="../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid session ID"):
        worker.build_run_command("prompt", session_id="invalid_prefix")

    # Command is always returned as discrete token list (never a shell string)
    cmd = worker.build_run_command("clean prompt", session_id="ses_ValidSession123")
    assert isinstance(cmd, list)
    assert all(isinstance(token, str) for token in cmd)
    assert cmd[0] == "opencode"
    assert cmd[1] == "run"

