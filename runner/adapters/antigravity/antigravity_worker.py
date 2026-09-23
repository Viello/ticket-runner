"""Antigravity worker CLI adapter: command building, event decoding, and wire models (Spec 11 / T095)."""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from runner.domain.telemetry import TokenUsage, WorkerEvent
from runner.ports.agent_worker import AgentWorker

# Maximum permitted line length to prevent memory exhaustion from oversized lines
MAX_LINE_CHARS: int = 5_000_000

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
) -> list[str]:
    """Construct the argv token list for agy run.

    Args:
        prompt: Task instruction or resume message. Must be a non-empty string.
        session_id: Optional session identifier for resuming an existing session.
        variant: Optional reasoning variant flag passed via ``--variant``.
        model_id: Optional model identifier flag passed via ``-m``.

    Returns:
        Token list: ['agy', 'run', '--auto', prompt, ...]

    Raises:
        TypeError: If prompt, session_id, variant, or model_id is not a string.
        ValueError: If prompt is empty or session_id is empty/whitespace.
    """
    if not isinstance(prompt, str):
        raise TypeError(f"Prompt must be a string, got {type(prompt).__name__}")
    if not prompt.strip():
        raise ValueError("Prompt cannot be empty")

    cmd = ["agy", "run", "--auto", prompt]

    if session_id is not None:
        if not isinstance(session_id, str):
            raise TypeError(f"Session ID must be a string, got {type(session_id).__name__}")
        clean_session_id = session_id.strip()
        if not clean_session_id:
            raise ValueError("Session ID cannot be empty")
        cmd.extend(["--session", clean_session_id])

    if model_id is not None:
        if not isinstance(model_id, str):
            raise TypeError(f"Model ID must be a string, got {type(model_id).__name__}")
        clean_model_id = model_id.strip()
        if clean_model_id:
            cmd.extend(["-m", clean_model_id])

    if variant is not None:
        if not isinstance(variant, str):
            raise TypeError(f"Variant must be a string, got {type(variant).__name__}")
        clean_variant = variant.strip()
        if clean_variant:
            cmd.extend(["--variant", clean_variant])

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

    if not isinstance(payload, dict):
        return None

    event_type = payload.get("type") or payload.get("event") or "text"
    if not isinstance(event_type, str) or not event_type:
        event_type = "text"

    session_id = (
        payload.get("session_id")
        or payload.get("sessionId")
        or payload.get("sessionID")
        or payload.get("conversation_id")
    )
    if not isinstance(session_id, str):
        session_id = None

    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        timestamp = None

    part = payload.get("part") if isinstance(payload.get("part"), dict) else None

    # Tokens can be in 'tokens', 'part.tokens', or 'usage'
    tokens_data = None
    if part is not None and "tokens" in part:
        tokens_data = part["tokens"]
    elif "tokens" in payload:
        tokens_data = payload["tokens"]
    elif "usage" in payload:
        tokens_data = payload["usage"]

    token_usage = _extract_token_usage(tokens_data) if tokens_data is not None else None

    return WorkerEvent(
        type=event_type,
        session_id=session_id,
        timestamp=timestamp,
        token_usage=token_usage,
        part=part,
        raw=payload,
        is_known=True,
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


def extract_resource_access(
    event_or_line: WorkerEvent | str | None = None,
    raw_line: str | None = None,
    *,
    event: WorkerEvent | None = None,
) -> frozenset[str]:
    """Detect project-local skill and AGENTS.md resource accesses from event stream.

    Performs dual resource access detection:
    - Structured detection: inspects tool_use and tool_call event payloads.
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

    # 1. Structured detection on WorkerEvent
    if actual_event is not None:
        tool_name = ""
        part = actual_event.part if isinstance(actual_event.part, dict) else {}
        raw = actual_event.raw if isinstance(actual_event.raw, dict) else {}

        # Discover tool identifier
        for container in (part, raw):
            for k in ("tool", "name", "tool_name"):
                v = container.get(k)
                if isinstance(v, str) and v:
                    tool_name = v.lower()
                    break
            if tool_name:
                break

        # Collect candidate argument dictionaries
        input_dicts: list[Mapping[str, Any]] = []

        if isinstance(part.get("state"), dict) and isinstance(part["state"].get("input"), dict):
            input_dicts.append(part["state"]["input"])

        for container in (part, raw):
            for key in ("input", "args", "arguments", "parameters"):
                val = container.get(key)
                if isinstance(val, dict):
                    input_dicts.append(val)
                elif isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, dict):
                            input_dicts.append(parsed)
                    except Exception:
                        pass

        # Inspect tool arguments
        for inp in input_dicts:
            for fk in ("filePath", "file_path", "path", "file", "filename", "target"):
                fval = inp.get(fk)
                if isinstance(fval, str):
                    _check_and_add_resource(fval, detected)

            for ck in ("command", "cmd", "input", "script"):
                cval = inp.get(ck)
                if isinstance(cval, str):
                    _check_and_add_resource(cval, detected)

            for val in inp.values():
                if isinstance(val, str):
                    _check_and_add_resource(val, detected)

    # 2. Fallback stream line scanning
    if actual_line:
        _check_and_add_resource(actual_line, detected)
    if actual_event is not None and isinstance(actual_event.raw, dict):
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
    ) -> list[str]:
        """Construct the argv token list for agy run."""
        return build_antigravity_run_command(
            prompt=prompt,
            session_id=session_id,
            variant=variant,
            model_id=model_id,
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
