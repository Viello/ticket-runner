"""Opt-in live smoke test verifying real Antigravity (agy) CLI JSON streaming via SubprocessRunner.

To run manually against a real agy installation:
    $env:TICKET_RUNNER_LIVE=1; pytest tests/unit/adapters/test_live_antigravity_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import pytest

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.antigravity.antigravity_worker import build_antigravity_run_command
from runner.ports.command_runner import ProcessHandle

pytestmark = pytest.mark.skipif(
    os.environ.get("TICKET_RUNNER_LIVE") != "1",
    reason="Opt-in live smoke test skipped unless TICKET_RUNNER_LIVE=1 is set",
)


def _resolve_agy_binary(which_fn=None) -> str | None:
    """Resolve agy binary respecting AGENT_ANTIGRAVITY_BIN env-var override and which resolver."""
    resolver = which_fn or shutil.which
    env_override = os.environ.get("AGENT_ANTIGRAVITY_BIN")
    if env_override:
        return env_override
    return resolver("agy")


def test_live_antigravity_json_streaming_smoke(tmp_path) -> None:
    """Verify live agy process streams valid JSON events carrying a conversation_id and exits cleanly."""
    agy_bin = _resolve_agy_binary()
    if not agy_bin:
        pytest.skip("Antigravity CLI binary 'agy' is not installed or accessible on PATH")

    runner = SubprocessRunner()

    async def _run() -> None:
        cmd = [
            agy_bin,
            "-p",
            "Respond with: OK",
            "--output-format",
            "stream-json",
            "--print-timeout",
            "0",
        ]
        handle = await runner.spawn(cmd, cwd=tmp_path)
        assert isinstance(handle, ProcessHandle)

        events: list[dict[str, object]] = []
        found_conversation_id = False
        valid_events = {"init", "step_update", "result"}
        found_valid_event = False

        async for line in handle.stdout_lines():
            line_str = line.strip()
            if not line_str:
                continue
            event = json.loads(line_str)
            assert isinstance(event, dict), f"Expected JSON object, got: {event}"
            events.append(event)

            # Check conversation_id across top-level or nested event envelopes
            conv_id = (
                event.get("conversation_id")
                or (event.get("step_update", {}).get("conversation_id") if isinstance(event.get("step_update"), dict) else None)
                or (event.get("result", {}).get("conversation_id") if isinstance(event.get("result"), dict) else None)
            )
            if conv_id:
                found_conversation_id = True

            event_type = event.get("event")
            if event_type in valid_events:
                found_valid_event = True

        exit_code = await handle.wait()
        assert exit_code == 0, f"Process exited with code {exit_code}, stderr: {handle.stderr}"
        assert len(events) > 0, "Expected at least one JSON stream event from agy"
        assert found_conversation_id, f"Expected conversation_id field across stream events, got: {events}"
        assert found_valid_event, f"Expected at least one event with type in {valid_events}, got: {events}"

    asyncio.run(_run())


def test_live_antigravity_default_turn_completes(tmp_path) -> None:
    """The adapter's default argv must let a real turn finish (non-empty response, non-zero usage).

    Regression for the hard-coded `--print-timeout 5s` default that truncated every Worker
    turn into an empty-but-SUCCESS result.
    """
    agy_bin = _resolve_agy_binary()
    if not agy_bin:
        pytest.skip("Antigravity CLI binary 'agy' is not installed or accessible on PATH")

    cmd = build_antigravity_run_command(
        prompt="Respond with exactly: PROBE_OK",
        model_id="gemini-3.8-flash-high",
    )
    # The adapter emits the bare 'agy' token; swap in the resolved binary path.
    cmd[0] = agy_bin

    runner = SubprocessRunner()

    async def _run() -> tuple[int, dict | None]:
        handle = await runner.spawn(cmd, cwd=tmp_path)
        assert isinstance(handle, ProcessHandle)

        result_event: dict | None = None
        async for line in handle.stdout_lines():
            line_str = line.strip()
            if not line_str:
                continue
            try:
                event = json.loads(line_str)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event") == "result":
                result_event = event

        exit_code = await handle.wait()
        return exit_code, result_event

    exit_code, result_event = asyncio.run(_run())

    assert exit_code == 0, f"Process exited with code {exit_code}"
    assert result_event is not None, "Expected a 'result' event from agy"

    result = result_event.get("result", {})
    assert result.get("status") == "SUCCESS"
    assert result.get("response", "").strip() != "", (
        f"Expected a non-empty response from a completed turn, got: {result!r}"
    )
    assert result.get("usage", {}).get("total_tokens", 0) > 0, (
        f"Expected non-zero token usage from a completed turn, got: {result.get('usage')!r}"
    )
