"""In-memory fake implementation of AgentWorker for deterministic testing."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from typing import Any

from runner.domain.telemetry import TokenUsage, WorkerEvent


class FakeAgentWorker:
    """Deterministic in-memory test double conforming to the AgentWorker protocol."""

    def __init__(
        self,
        custom_command: list[str] | Callable[..., list[str]] | None = None,
        canned_events: Mapping[str, WorkerEvent | None] | list[WorkerEvent | None] | None = None,
        canned_resources: frozenset[str] | Callable[..., frozenset[str]] | None = None,
        raise_on_build: Exception | None = None,
        raise_on_decode: Exception | None = None,
    ) -> None:
        self._custom_command = custom_command
        self._canned_events = canned_events
        self._canned_resources = canned_resources
        self._raise_on_build = raise_on_build
        self._raise_on_decode = raise_on_decode

        self.commands_built: list[dict[str, Any]] = []
        self.decoded_lines: list[str] = []
        self.resource_access_calls: list[dict[str, Any]] = []
        self._event_index = 0

    def build_run_command(
        self,
        prompt: str,
        session_id: str | None = None,
        variant: str | None = None,
        model_id: str | None = None,
    ) -> list[str]:
        """Construct deterministic argv token list or return configured command."""
        self.commands_built.append({
            "prompt": prompt,
            "session_id": session_id,
            "variant": variant,
            "model_id": model_id,
        })
        if self._raise_on_build is not None:
            raise self._raise_on_build

        if callable(self._custom_command):
            return self._custom_command(
                prompt=prompt,
                session_id=session_id,
                variant=variant,
                model_id=model_id,
            )
        if self._custom_command is not None:
            return list(self._custom_command)

        # Default standard command mimicking real agent workers
        cmd = ["opencode", "run", "--format", "json"]
        if session_id:
            cmd.extend(["--session", session_id])
        if model_id:
            cmd.extend(["-m", model_id])
        if variant:
            cmd.extend(["--variant", variant])
        cmd.extend(["--auto", prompt])
        return cmd

    def decode_event(self, line: str) -> WorkerEvent | None:
        """Decode stdout line using canned events or basic JSON parsing."""
        self.decoded_lines.append(line)
        if self._raise_on_decode is not None:
            raise self._raise_on_decode

        if isinstance(self._canned_events, dict):
            if line in self._canned_events:
                return self._canned_events[line]
        elif isinstance(self._canned_events, list):
            if self._event_index < len(self._canned_events):
                event = self._canned_events[self._event_index]
                self._event_index += 1
                return event

        stripped = line.strip()
        if not stripped:
            return None

        try:
            payload = json.loads(stripped)
            if not isinstance(payload, dict):
                return None
            event_type = payload.get("type", "text")
            session_id = payload.get("sessionID") or payload.get("session_id")
            token_usage = None
            tokens_data = payload.get("tokens") or (payload.get("part", {}).get("tokens") if isinstance(payload.get("part"), dict) else None)
            if isinstance(tokens_data, dict):
                token_usage = TokenUsage(
                    input=int(tokens_data.get("input", 0)),
                    output=int(tokens_data.get("output", 0)),
                    reasoning=int(tokens_data.get("reasoning", 0)),
                    cache_read=int(tokens_data.get("cache_read", 0)),
                    cache_write=int(tokens_data.get("cache_write", 0)),
                    total=int(tokens_data["total"]) if tokens_data.get("total") is not None else None,
                )
            return WorkerEvent(
                type=str(event_type),
                session_id=session_id,
                timestamp=payload.get("timestamp"),
                token_usage=token_usage,
                part=payload.get("part") if isinstance(payload.get("part"), dict) else None,
                raw=payload,
                is_known=True,
            )
        except Exception:
            return None

    def extract_resource_access(
        self,
        event: WorkerEvent | None = None,
        raw_line: str | None = None,
    ) -> frozenset[str]:
        """Record and return configured resource accesses."""
        self.resource_access_calls.append({"event": event, "raw_line": raw_line})
        if callable(self._canned_resources):
            return self._canned_resources(event=event, raw_line=raw_line)
        if self._canned_resources is not None:
            return frozenset(self._canned_resources)
        return frozenset()
