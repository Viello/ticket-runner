"""OpenCode worker CLI adapter: command building, event decoding, and wire models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from runner.domain.runtime_paths import is_valid_session_id
from runner.domain.telemetry import TokenUsage

# Six canonical event types emitted by opencode run --format json
KNOWN_EVENT_TYPES: frozenset[str] = frozenset({
    "step_start",
    "step_finish",
    "text",
    "tool_call",
    "tool_result",
    "error",
})

# Maximum permitted line length to prevent memory exhaustion from oversized lines
MAX_LINE_CHARS: int = 5_000_000


@dataclass(frozen=True)
class OpenCodeEvent:
    """Decoded OpenCode JSONL stream event."""

    type: str
    session_id: str | None = None
    timestamp: int | None = None
    token_usage: TokenUsage | None = None
    part: Mapping[str, Any] | None = None
    raw: Mapping[str, Any] | None = None
    is_known: bool = True


def build_opencode_run_command(
    prompt: str,
    session_id: str | None = None,
) -> list[str]:
    """Construct the argv token list for opencode run.

    Args:
        prompt: Task instruction or resume message. Must be a non-empty string.
        session_id: Optional session identifier for resuming an existing session.

    Returns:
        Token list: ['opencode', 'run', '--format', 'json', ...]

    Raises:
        TypeError: If prompt is not a string.
        ValueError: If prompt is empty or session_id fails the session allowlist.
    """
    if not isinstance(prompt, str):
        raise TypeError(f"Prompt must be a string, got {type(prompt).__name__}")
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    cmd = ["opencode", "run", "--format", "json"]

    if session_id is not None:
        if not is_valid_session_id(session_id):
            raise ValueError(
                f"Invalid session ID '{session_id}'; must match ^ses_[A-Za-z0-9]+$"
            )
        cmd.extend(["--session", session_id])

    cmd.extend(["--auto", prompt])
    return cmd


def _extract_token_usage(tokens_data: Any) -> TokenUsage | None:
    """Safely extract a TokenUsage domain entity from untrusted token dictionary data."""
    if not isinstance(tokens_data, dict):
        return None

    try:
        total = tokens_data.get("total")
        input_tokens = tokens_data.get("input", 0)
        output_tokens = tokens_data.get("output", 0)
        reasoning_tokens = tokens_data.get("reasoning", 0)

        cache = tokens_data.get("cache")
        if isinstance(cache, dict):
            cache_read = cache.get("read", 0)
            cache_write = cache.get("write", 0)
        else:
            cache_read = tokens_data.get("cache_read", 0)
            cache_write = tokens_data.get("cache_write", 0)

        return TokenUsage(
            input=int(input_tokens),
            output=int(output_tokens),
            reasoning=int(reasoning_tokens),
            cache_read=int(cache_read),
            cache_write=int(cache_write),
            total=int(total) if total is not None else None,
        )
    except (ValueError, TypeError):
        return None


def decode_event(line: str) -> OpenCodeEvent | None:
    """Decode a single raw stdout line into an OpenCodeEvent domain model.

    Tolerant of unknown event types, unparseable lines, and oversized payloads.
    Returns None if the line cannot be parsed as a valid OpenCode event dictionary.
    """
    if not isinstance(line, str):
        return None

    stripped = line.rstrip("\r\n").strip()
    if not stripped:
        return None

    if len(stripped) > MAX_LINE_CHARS:
        return None

    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        return None

    if not isinstance(payload, dict):
        return None

    event_type = payload.get("type")
    if not isinstance(event_type, str) or not event_type:
        return None

    # Extract sessionID (tolerant of camelCase and snake_case)
    session_id = payload.get("sessionID") or payload.get("sessionId") or payload.get("session_id")
    if not isinstance(session_id, str):
        session_id = None

    # Extract timestamp if present and numeric
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        timestamp = None

    part = payload.get("part")
    if not isinstance(part, dict):
        part = None

    is_known = event_type in KNOWN_EVENT_TYPES

    # Extract token telemetry on step_finish events
    token_usage: TokenUsage | None = None
    if event_type == "step_finish":
        tokens_data = None
        if part is not None and "tokens" in part:
            tokens_data = part["tokens"]
        elif "tokens" in payload:
            tokens_data = payload["tokens"]

        if tokens_data is not None:
            token_usage = _extract_token_usage(tokens_data)

    return OpenCodeEvent(
        type=event_type,
        session_id=session_id,
        timestamp=timestamp,
        token_usage=token_usage,
        part=part,
        raw=payload,
        is_known=is_known,
    )
