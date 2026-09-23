"""Unit tests for AgentWorker protocol contract and FakeAgentWorker test double (T094)."""

import inspect
import pytest

from runner.adapters.opencode.opencode_worker import OpenCodeWorker
from runner.domain.telemetry import TokenUsage, WorkerEvent
from runner.ports.agent_worker import AgentWorker
from tests.fakes.fake_agent_worker import FakeAgentWorker


def test_agent_worker_protocol_methods() -> None:
    """AgentWorker protocol defines expected methods and zero adapter dependencies."""
    methods = [name for name, _ in inspect.getmembers(AgentWorker, predicate=inspect.isfunction)]
    assert "build_run_command" in methods
    assert "decode_event" in methods
    assert "extract_resource_access" in methods

    # Verify no concrete adapter modules are imported by ports
    import runner.ports.agent_worker as port_module
    source = inspect.getsource(port_module)
    assert "runner.adapters" not in source


def test_opencode_worker_conforms_to_protocol() -> None:
    """OpenCodeWorker satisfies the AgentWorker protocol at runtime."""
    worker = OpenCodeWorker()
    assert isinstance(worker, AgentWorker)


def test_fake_agent_worker_conforms_to_protocol() -> None:
    """FakeAgentWorker satisfies the AgentWorker protocol at runtime."""
    fake = FakeAgentWorker()
    assert isinstance(fake, AgentWorker)


def test_fake_agent_worker_records_calls_and_uses_defaults() -> None:
    """FakeAgentWorker records invocations and generates expected standard commands."""
    fake = FakeAgentWorker()

    cmd = fake.build_run_command(
        prompt="Implement T094",
        session_id="ses_abc123",
        variant="high",
        model_id="gemini-flash",
    )
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        "ses_abc123",
        "-m",
        "gemini-flash",
        "--variant",
        "high",
        "--auto",
        "Implement T094",
    ]
    assert len(fake.commands_built) == 1
    assert fake.commands_built[0]["prompt"] == "Implement T094"
    assert fake.commands_built[0]["session_id"] == "ses_abc123"

    # Decode event
    raw_line = '{"type": "step_finish", "sessionID": "ses_abc123", "tokens": {"total": 125000}}\n'
    event = fake.decode_event(raw_line)
    assert event is not None
    assert isinstance(event, WorkerEvent)
    assert event.type == "step_finish"
    assert event.session_id == "ses_abc123"
    assert event.token_usage == TokenUsage(total=125000)
    assert len(fake.decoded_lines) == 1

    # Extract resource access
    resources = fake.extract_resource_access(event, raw_line=raw_line)
    assert resources == frozenset()
    assert len(fake.resource_access_calls) == 1


def test_fake_agent_worker_custom_configuration() -> None:
    """FakeAgentWorker respects custom commands, canned events, and canned resources."""
    canned_event = WorkerEvent(type="text", raw={"custom": True})
    fake = FakeAgentWorker(
        custom_command=["custom", "cli", "run"],
        canned_events={"line1\n": canned_event},
        canned_resources=frozenset({"implement", "AGENTS.md"}),
    )

    cmd = fake.build_run_command("test")
    assert cmd == ["custom", "cli", "run"]

    event1 = fake.decode_event("line1\n")
    assert event1 is canned_event

    resources = fake.extract_resource_access(event1)
    assert resources == frozenset({"implement", "AGENTS.md"})


def test_fake_agent_worker_error_simulation() -> None:
    """FakeAgentWorker can simulate command build and decode errors."""
    fake_build_err = FakeAgentWorker(raise_on_build=RuntimeError("Build failed"))
    with pytest.raises(RuntimeError, match="Build failed"):
        fake_build_err.build_run_command("prompt")

    fake_decode_err = FakeAgentWorker(raise_on_decode=ValueError("Corrupt stream"))
    with pytest.raises(ValueError, match="Corrupt stream"):
        fake_decode_err.decode_event("line")


def test_worker_event_immutability() -> None:
    """WorkerEvent is a frozen domain dataclass."""
    event = WorkerEvent(type="text", session_id="ses_123")
    with pytest.raises(AttributeError):
        event.type = "tool_call"  # type: ignore[misc]
