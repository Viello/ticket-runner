"""Opt-in live smoke test verifying real OpenCode CLI JSON streaming via SubprocessRunner."""

import asyncio
import json
import os
import pytest

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.ports.command_runner import ProcessHandle


pytestmark = pytest.mark.skipif(
    os.environ.get("TICKET_RUNNER_LIVE") != "1",
    reason="Opt-in live smoke test skipped unless TICKET_RUNNER_LIVE=1 is set",
)


def test_live_opencode_json_streaming_smoke() -> None:
    """Verify live OpenCode process streams valid JSON events carrying a sessionID and exits cleanly."""
    runner = SubprocessRunner()

    async def _run() -> None:
        cmd = ["opencode", "run", "--format", "json", "Respond with: OK"]
        handle = await runner.spawn(cmd)
        assert isinstance(handle, ProcessHandle)

        events: list[dict[str, object]] = []
        async for line in handle.stdout_lines():
            if not line.strip():
                continue
            event = json.loads(line)
            assert isinstance(event, dict), f"Expected JSON object, got: {event}"
            assert "sessionID" in event, f"Expected sessionID in event, got keys: {event.keys()}"
            assert event["sessionID"], "sessionID should not be empty"
            events.append(event)

        exit_code = await handle.wait()
        assert exit_code == 0, f"Process exited with code {exit_code}, stderr: {handle.stderr}"
        assert len(events) > 0, "Expected at least one JSON stream event from opencode"

    asyncio.run(_run())
