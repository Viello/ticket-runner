"""Antigravity worker CLI adapter: command building, event decoding, and wire models.

Empirical Surface Notes (agy 1.2.16+):
- agy does NOT provide a 'run' subcommand or '--auto' flag. Calling 'agy run'
  fails immediately with: Error: unexpected argument "run" (exit code 2).
- Headless invocation format:
    agy -p "<prompt>" --output-format stream-json
        [--effort low|medium|high|xhigh|max]
        [--model <slug>]
        [--continue|--conversation <uuid>]
        --print-timeout <dur>
- NDJSON output stream uses a closed 3-event vocabulary:
    {"event": "init", ...}
    {"event": "step_update", ...}
    {"event": "result", ...}
- Token telemetry is surfaced under 'step_update.usage' and 'result.usage' with wire keys:
    input_tokens, output_tokens, thinking_tokens, cache_read_tokens, cache_write_tokens, total_tokens.
- Tool access parameters appear under 'step_update.tool_info.parameters'.
- Conversation identifiers are UUIDs emitted as 'conversation_id'.

Single source of truth:
T002 empirical research note on branch 'research/agy-flag-surface' (commit 0c30f9a),
located at '.agents/skills/research/out/agy-flag-surface.md'.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from runner.domain.runtime_paths import is_valid_session_id
from runner.domain.telemetry import TokenUsage, WorkerEvent
from runner.ports.agent_worker import AgentWorker

# Maximum permitted line length to prevent memory exhaustion from oversized lines
MAX_LINE_CHARS: int = 5_000_000

# Default print-timeout ceiling to prevent unbounded execution (agy default is 0s)
DEFAULT_PRINT_TIMEOUT: str = "5s"

# Closed set of event types emitted by agy headless stream-json
KNOWN_EVENT_TYPES: frozenset[str] = frozenset({
    "init",
    "step_update",
    "result",
})

# Regex to match project-local skills: .agents/skills/<name>/SKILL.md
SKILL_RESOURCE_PATTERN: re.Pattern[str] = re.compile(
    r"\.agents/skills/([a-z0-9_-]+)/skill\.md",
    re.IGNORECASE,
)

# Regex to match workspace AGENTS.md references
AGENTS_MD_PATTERN: re.Pattern[str] = re.compile(
    r"(?:^|[/\\\"'\s(\[{:;,])agents\.md(?:$|[/\\\"'\s)\]}:;,])",
    re.IGNORECASE,
)


def build_antigravity_run_command(
    prompt: str,
    session_id: str | None = None,
    variant: str | None = None,
    model_id: str | None = None,
    print_timeout: str = DEFAULT_PRINT_TIMEOUT,
) -> list[str]:
    """Construct the argv token list for agy headless execution.

    Args:
        prompt: Task instruction or resume message. Must be a non-empty string.
        session_id: Optional session identifier for resuming an existing session.
            Accepts 'continue' for most recent session, or a UUID string for --conversation.
        variant: Optional reasoning effort flag passed via ``--effort`` (low|medium|high|xhigh|max).
        model_id: Optional model identifier flag passed via ``--model``.
        print_timeout: Wall-clock timeout ceiling passed via ``--print-timeout`` (default '5s').

    Returns:
        Token list: ['agy', '-p', prompt, '--output-format', 'stream-json', ...]

    Raises:
        TypeError: If prompt, session_id, variant, model_id, or print_timeout is not a string.
        ValueError: If prompt is empty or session_id/print_timeout is empty/whitespace.
    """
    if not isinstance(prompt, str):
        raise TypeError(f"Prompt must be a string, got {type(prompt).__name__}")
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    cmd = ["agy", "-p", prompt, "--output-format", "stream-json"]

    if session_id is not None:
        if not isinstance(session_id, str):
            raise TypeError(f"Session ID must be a string, got {type(session_id).__name__}")
        clean_session_id = session_id.strip()
        if not clean_session_id:
            raise ValueError("Session ID cannot be empty")
        if clean_session_id.lower() in ("continue", "--continue"):
            cmd.append("--continue")
        else:
            cmd.extend(["--conversation", clean_session_id])

    if model_id is not None:
        if not isinstance(model_id, str):
            raise TypeError(f"Model ID must be a string, got {type(model_id).__name__}")
        clean_model_id = model_id.strip()
        if clean_model_id:
            cmd.extend(["--model", clean_model_id])

    if variant is not None:
        if not isinstance(variant, str):
            raise TypeError(f"Variant must be a string, got {type(variant).__name__}")
        clean_variant = variant.strip()
        if clean_variant:
            cmd.extend(["--effort", clean_variant])

    if not isinstance(print_timeout, str):
        raise TypeError(f"Print timeout must be a string, got {type(print_timeout).__name__}")
    clean_timeout = print_timeout.strip()
    if not clean_timeout:
        raise ValueError("Print timeout cannot be empty")
    cmd.extend(["--print-timeout", clean_timeout])

    return cmd


def _extract_token_usage(tokens_data: Any) -> TokenUsage | None:
    """Safely extract a TokenUsage domain entity from empirical agy usage dictionary.

    Wire keys mapping:
    - input_tokens (or input) -> input
    - output_tokens (or output) -> output
    - thinking_tokens (or reasoning) -> reasoning
    - cache_read_tokens (or cache.read) -> cache_read
    - cache_write_tokens (or cache.write) -> cache_write
    - total_tokens (or total) -> total
    """
    if not isinstance(tokens_data, Mapping):
        return None

    try:
        total = tokens_data.get("total_tokens")
        if total is None:
            total = tokens_data.get("total")

        input_tokens = tokens_data.get("input_tokens")
        if input_tokens is None:
            input_tokens = tokens_data.get("input", 0)

        output_tokens = tokens_data.get("output_tokens")
        if output_tokens is None:
            output_tokens = tokens_data.get("output", 0)

        reasoning_tokens = tokens_data.get("thinking_tokens")
        if reasoning_tokens is None:
            reasoning_tokens = tokens_data.get("reasoning", 0)

        cache = tokens_data.get("cache")
        if isinstance(cache, Mapping):
            cache_read = cache.get("read", 0)
            cache_write = cache.get("write", 0)
        else:
            cache_read = tokens_data.get("cache_read_tokens")
            if cache_read is None:
                cache_read = tokens_data.get("cache_read", 0)
            cache_write = tokens_data.get("cache_write_tokens")
            if cache_write is None:
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


def decode_event(line: str) -> WorkerEvent | None:
    """Decode a single raw stdout line into a normalized WorkerEvent domain model.

    Tolerant of unknown event formats, unparseable lines, and oversized payloads.
    Returns None if the line cannot be parsed as a valid Antigravity event dictionary.
    """
    if not isinstance(line, str):
        return None

    stripped = line.rstrip("\r\n").strip()
    if not stripped or len(stripped) > MAX_LINE_CHARS:
        return None

    try:
        payload = json.loads(stripped)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        return None

    if not isinstance(payload, Mapping):
        return None

    # Empirical agy streams use top-level 'event' discriminator (init, step_update, result)
    event_type = payload.get("event") or payload.get("type")
    if not isinstance(event_type, str) or not event_type:
        return None

    is_known = event_type in KNOWN_EVENT_TYPES

    # Extract conversation_id across top-level, step_update, result, and legacy fields
    session_id = (
        payload.get("conversation_id")
        or (payload.get("step_update", {}).get("conversation_id") if isinstance(payload.get("step_update"), Mapping) else None)
        or (payload.get("result", {}).get("conversation_id") if isinstance(payload.get("result"), Mapping) else None)
        or payload.get("session_id")
        or payload.get("sessionId")
        or payload.get("sessionID")
    )
    if not isinstance(session_id, str):
        session_id = None

    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        timestamp = None

    # Map payload[event_type] as part envelope (e.g. payload.step_update, payload.result, payload.init)
    part = None
    if isinstance(payload.get(event_type), Mapping):
        part = payload[event_type]
    elif isinstance(payload.get("part"), Mapping):
        part = payload["part"]

    # Look for usage exclusively under step_update.usage and result.usage, never top level
    tokens_data = None
    step_update = payload.get("step_update")
    result = payload.get("result")
    if isinstance(step_update, Mapping) and isinstance(step_update.get("usage"), Mapping):
        tokens_data = step_update["usage"]
    elif isinstance(result, Mapping) and isinstance(result.get("usage"), Mapping):
        tokens_data = result["usage"]

    token_usage = _extract_token_usage(tokens_data) if tokens_data is not None else None

    return WorkerEvent(
        type=event_type,
        session_id=session_id,
        timestamp=timestamp,
        token_usage=token_usage,
        part=part,
        raw=payload,
        is_known=is_known,
    )


def _check_and_add_resource(text: str, detected: set[str]) -> None:
    """Normalize text and add recognized skill or AGENTS.md resources to detected set."""
    if not isinstance(text, str) or not text:
        return
    norm = text.replace("\\", "/").lower()
    for m in SKILL_RESOURCE_PATTERN.finditer(norm):
        detected.add(m.group(1).lower())
    if AGENTS_MD_PATTERN.search(norm):
        detected.add("AGENTS.md")


def _scan_obj_for_resources(obj: Any, detected: set[str]) -> None:
    """Recursively inspect an object for skill or AGENTS.md resource paths."""
    if isinstance(obj, str):
        _check_and_add_resource(obj, detected)
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            if isinstance(k, str):
                _check_and_add_resource(k, detected)
            _scan_obj_for_resources(v, detected)
    elif isinstance(obj, (list, tuple, set, frozenset)):
        for item in obj:
            _scan_obj_for_resources(item, detected)


def extract_resource_access(
    event_or_line: WorkerEvent | str | None = None,
    raw_line: str | None = None,
    *,
    event: WorkerEvent | None = None,
) -> frozenset[str]:
    """Detect project-local skill and AGENTS.md resource accesses from event stream.

    Performs dual resource access detection:
    - Structured detection: inspects step_update.tool_info.parameters.
    - Fallback detection: scans raw stream line strings.

    Args:
        event_or_line: Decoded WorkerEvent domain model, or raw stream line string.
        raw_line: Optional raw JSONL line string when event is passed positionally.
        event: Optional WorkerEvent keyword argument.

    Returns:
        frozenset of canonical resource identifiers (e.g. 'implement', 'code-review', 'AGENTS.md').
    """
    actual_event: WorkerEvent | None = event
    actual_line: str = ""

    if isinstance(event_or_line, WorkerEvent):
        actual_event = event_or_line
        if isinstance(raw_line, str):
            actual_line = raw_line
    elif isinstance(event_or_line, str):
        actual_line = event_or_line
        if isinstance(raw_line, WorkerEvent):
            actual_event = raw_line
    elif event_or_line is None:
        if isinstance(raw_line, str):
            actual_line = raw_line

    detected: set[str] = set()

    # 1. Structured detection on step_update.tool_info.parameters
    if actual_event is not None:
        raw = actual_event.raw if isinstance(actual_event.raw, Mapping) else {}
        part = actual_event.part if isinstance(actual_event.part, Mapping) else {}

        step_update = None
        if isinstance(raw.get("step_update"), Mapping):
            step_update = raw["step_update"]
        elif isinstance(part.get("step_update"), Mapping):
            step_update = part["step_update"]
        elif raw.get("event") == "step_update" or "tool_info" in raw:
            step_update = raw
        elif "tool_info" in part:
            step_update = part

        if isinstance(step_update, Mapping):
            tool_info = step_update.get("tool_info")
            if isinstance(tool_info, Mapping):
                parameters = tool_info.get("parameters")
                if parameters is not None:
                    _scan_obj_for_resources(parameters, detected)

    # 2. Fallback stream line scanning
    if actual_line:
        _check_and_add_resource(actual_line, detected)
    if actual_event is not None and isinstance(actual_event.raw, Mapping):
        try:
            _check_and_add_resource(json.dumps(actual_event.raw), detected)
        except Exception:
            pass

    return frozenset(detected)


class AntigravityWorker:
    """Antigravity CLI adapter implementing AgentWorker protocol."""

    def build_run_command(
        self,
        prompt: str,
        session_id: str | None = None,
        variant: str | None = None,
        model_id: str | None = None,
        print_timeout: str = DEFAULT_PRINT_TIMEOUT,
    ) -> list[str]:
        """Construct the argv token list for agy headless execution."""
        return build_antigravity_run_command(
            prompt=prompt,
            session_id=session_id,
            variant=variant,
            model_id=model_id,
            print_timeout=print_timeout,
        )

    def decode_event(self, line: str) -> WorkerEvent | None:
        """Decode a single raw stdout line into a normalized WorkerEvent domain model."""
        return decode_event(line)

    def extract_resource_access(
        self,
        event: WorkerEvent | None = None,
        raw_line: str | None = None,
        *,
        event_or_line: WorkerEvent | str | None = None,
    ) -> frozenset[str]:
        """Detect project-local skill and AGENTS.md resource accesses from event stream."""
        actual_event = event if event is not None else (event_or_line if isinstance(event_or_line, WorkerEvent) else None)
        actual_line = raw_line if raw_line is not None else (event_or_line if isinstance(event_or_line, str) else None)
        return extract_resource_access(
            event_or_line=actual_event or actual_line,
            raw_line=actual_line,
            event=actual_event,
        )


class AntigravityWorkerCli(AntigravityWorker):
    """Namespace seam exposing Antigravity CLI adapter methods."""

    decode_event = staticmethod(decode_event)
    build_run_command = staticmethod(build_antigravity_run_command)
    extract_resource_access = staticmethod(extract_resource_access)
