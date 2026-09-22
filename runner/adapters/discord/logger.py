"""DiscordLoggerImpl adapter implementing DiscordLogger port (T082)."""

from __future__ import annotations

from typing import Any

from runner.ports.discord_gateway import DiscordGateway
from runner.ports.discord_logger import DiscordLogger

__all__ = [
    "COLOR_BLURPLE",
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "CRITICAL_EMBED_CONFIG",
    "CRITICAL_EVENT_TYPES",
    "DiscordLoggerImpl",
    "MAX_EMBED_FIELD_NAME_LENGTH",
    "MAX_EMBED_FIELD_VALUE_LENGTH",
    "MAX_EMBED_TITLE_LENGTH",
    "MAX_PAYLOAD_CHUNK_LENGTH",
    "ROUTINE_EVENT_EMOJIS",
    "chunk_payload",
    "format_chunks",
    "sanitize_embed",
    "split_chunks",
]

MAX_PAYLOAD_CHUNK_LENGTH = 1950
MAX_EMBED_TITLE_LENGTH = 256
MAX_EMBED_FIELD_NAME_LENGTH = 256
MAX_EMBED_FIELD_VALUE_LENGTH = 1024

COLOR_RED = 0xFF0000
COLOR_YELLOW = 0xFEE75C
COLOR_GREEN = 0x57F287
COLOR_BLURPLE = 0x5865F2

CRITICAL_EVENT_TYPES = frozenset(
    {
        "circuit_breaker_trip",
        "hard_ceiling_hit",
        "hard_ceiling",
        "handoff_triggered",
        "handoff",
        "question_signal",
        "question_posted",
        "runner_shutdown",
        "runner_crash",
        "verification_failed",
        "live_digest",
        "critical",
    }
)

CRITICAL_EMBED_CONFIG: dict[str, tuple[str, int]] = {
    "circuit_breaker_trip": ("Circuit Breaker Tripped", COLOR_RED),
    "hard_ceiling_hit": ("Hard Ceiling Hit", COLOR_RED),
    "hard_ceiling": ("Hard Ceiling Hit", COLOR_RED),
    "runner_shutdown": ("Runner Shutdown", COLOR_RED),
    "runner_crash": ("Runner Crash", COLOR_RED),
    "verification_failed": ("Verification Failed", COLOR_RED),
    "handoff_triggered": ("Handoff Triggered", COLOR_YELLOW),
    "handoff": ("Handoff Triggered", COLOR_YELLOW),
    "question_signal": ("❓ Worker Question", COLOR_YELLOW),
    "question_posted": ("❓ Worker Question", COLOR_YELLOW),
    "critical": ("Critical Alert", COLOR_RED),
}

ROUTINE_EVENT_EMOJIS: dict[str, str] = {
    "phase_transition": "🔄",
    "worker_phase_transition": "🔄",
    "milestone_notice": "✅",
    "milestone": "✅",
    "token_warning": "⚠️",
    "security_review": "🔒",
    "queue_state_change": "📋",
    "queue_change": "📋",
    "ticket_committed": "✅",
    "runner_startup": "🚀",
}


def split_chunks(text: str, limit: int = MAX_PAYLOAD_CHUNK_LENGTH) -> list[str]:
    """Split text into raw chunks of at most `limit` characters.

    Splits on the last newline at or before `limit`. If no newline exists,
    falls back to a hard split at `limit`. Preserves all characters without loss.
    """
    if len(text) <= limit:
        return [text] if text else []

    raw_chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        nl_idx = remaining.rfind("\n", 0, limit)
        if nl_idx != -1:
            split_pos = nl_idx + 1
        else:
            split_pos = limit
        raw_chunks.append(remaining[:split_pos])
        remaining = remaining[split_pos:]

    if remaining:
        raw_chunks.append(remaining)

    return raw_chunks


def format_chunks(raw_chunks: list[str]) -> list[str]:
    """Format chunks with continuation headers.

    Chunk 1 has no prefix. Chunks 2...M are prefixed with `[continued N/M]\n`.
    Total chunk count M is computed before formatting.
    """
    m = len(raw_chunks)
    if m <= 1:
        return list(raw_chunks)

    formatted = [raw_chunks[0]]
    for i in range(1, m):
        formatted.append(f"[continued {i + 1}/{m}]\n{raw_chunks[i]}")
    return formatted


def chunk_payload(text: str, limit: int = MAX_PAYLOAD_CHUNK_LENGTH) -> list[str]:
    """Split and format payload into Discord-safe chunks."""
    raw = split_chunks(text, limit=limit)
    return format_chunks(raw)


def sanitize_embed(embed_dict: dict[str, Any]) -> dict[str, Any]:
    """Truncate embed titles and field values to Discord API limits."""
    sanitized = dict(embed_dict)
    if "title" in sanitized and isinstance(sanitized["title"], str):
        if len(sanitized["title"]) > MAX_EMBED_TITLE_LENGTH:
            sanitized["title"] = sanitized["title"][:MAX_EMBED_TITLE_LENGTH]

    if "fields" in sanitized and isinstance(sanitized["fields"], list):
        sanitized_fields = []
        for f in sanitized["fields"]:
            field_copy = dict(f)
            if "name" in field_copy and isinstance(field_copy["name"], str):
                if len(field_copy["name"]) > MAX_EMBED_FIELD_NAME_LENGTH:
                    field_copy["name"] = field_copy["name"][:MAX_EMBED_FIELD_NAME_LENGTH]
            if "value" in field_copy and isinstance(field_copy["value"], str):
                if len(field_copy["value"]) > MAX_EMBED_FIELD_VALUE_LENGTH:
                    field_copy["value"] = field_copy["value"][:MAX_EMBED_FIELD_VALUE_LENGTH]
            sanitized_fields.append(field_copy)
        sanitized["fields"] = sanitized_fields

    return sanitized


class DiscordLoggerImpl(DiscordLogger):
    """Production implementation of DiscordLogger port wrapping a DiscordGateway."""

    def __init__(
        self,
        gateway: DiscordGateway,
        notify_user_id: str | None = None,
    ) -> None:
        self._gateway = gateway
        self.notify_user_id = notify_user_id

    def resolve_severity(self, event_type: str, explicit_severity: str | None = None) -> str:
        """Resolve event severity to 'critical' or 'routine'."""
        if explicit_severity is not None:
            return explicit_severity.lower()
        if event_type.lower() in CRITICAL_EVENT_TYPES:
            return "critical"
        return "routine"

    def is_suppressed(self, severity: str, presence_mode: str) -> bool:
        """Evaluate mode gate: routine events are suppressed unless presence_mode is 'away'."""
        if severity == "critical":
            return False
        return presence_mode.lower() != "away"

    async def log(
        self,
        event_type: str,
        payload: str,
        thread_id: str,
        presence_mode: str = "nearby",
        *,
        severity: str | None = None,
    ) -> list[str]:
        """Log a structured event to a thread subject to severity routing and chunking."""
        resolved_severity = self.resolve_severity(event_type, severity)
        if self.is_suppressed(resolved_severity, presence_mode):
            return []

        lower_event = event_type.lower()

        # Handle critical embed events
        if lower_event in CRITICAL_EMBED_CONFIG or (
            resolved_severity == "critical" and lower_event != "live_digest"
        ):
            title, color = CRITICAL_EMBED_CONFIG.get(
                lower_event, ("Critical Alert", COLOR_RED)
            )
            embed_payload: dict[str, Any] = {
                "title": title,
                "description": payload,
                "color": color,
            }

            if lower_event in ("question_signal", "question_posted") and self.notify_user_id:
                # Post standalone user mention first, then yellow embed
                mention_id = await self._gateway.post_message(
                    thread_id, f"<@{self.notify_user_id}>"
                )
                embed_msg_ids = await self.post_embed(thread_id, embed_payload)
                return [mention_id, *embed_msg_ids]

            return await self.post_embed(thread_id, embed_payload)

        # Handle routine posts or plain-text critical events (e.g. live_digest)
        if lower_event in ROUTINE_EVENT_EMOJIS:
            emoji = ROUTINE_EVENT_EMOJIS[lower_event]
            content = payload if payload.startswith(emoji) else f"{emoji} {payload}"
        else:
            content = payload

        chunks = chunk_payload(content)
        if not chunks:
            chunks = [""]

        posted_ids: list[str] = []
        for chunk in chunks:
            msg_id = await self._gateway.post_message(thread_id, chunk)
            posted_ids.append(msg_id)
        return posted_ids

    async def post_embed(
        self,
        thread_id: str,
        embed_dict: dict[str, Any],
    ) -> list[str]:
        """Post a Discord embed dictionary subject to chunking and field limits."""
        sanitized = sanitize_embed(embed_dict)
        description = sanitized.get("description", "")

        if description and len(description) > MAX_PAYLOAD_CHUNK_LENGTH:
            raw_chunks = split_chunks(description, limit=MAX_PAYLOAD_CHUNK_LENGTH)
            m = len(raw_chunks)
            posted_ids: list[str] = []

            for i, chunk in enumerate(raw_chunks):
                if i == 0:
                    chunk_embed = dict(sanitized)
                    chunk_embed["description"] = chunk
                    msg_id = await self._gateway.post_message(
                        thread_id, "", embed=chunk_embed
                    )
                    posted_ids.append(msg_id)
                else:
                    continuation_embed: dict[str, Any] = {
                        "description": f"[continued {i + 1}/{m}]\n{chunk}",
                    }
                    if "color" in sanitized:
                        continuation_embed["color"] = sanitized["color"]
                    if "colour" in sanitized:
                        continuation_embed["colour"] = sanitized["colour"]

                    msg_id = await self._gateway.post_message(
                        thread_id, "", embed=continuation_embed
                    )
                    posted_ids.append(msg_id)
            return posted_ids

        msg_id = await self._gateway.post_message(thread_id, "", embed=sanitized)
        return [msg_id]
