"""DiscordLoggerImpl adapter implementing DiscordLogger port (T082)."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any

from runner.ports.discord_gateway import DiscordGateway
from runner.ports.discord_logger import DiscordLogger

__all__ = [
    "BREADCRUMB_TRAIL",
    "COLOR_BLURPLE",
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "CRITICAL_EMBED_CONFIG",
    "CRITICAL_EVENT_TYPES",
    "DEFAULT_CEILING",
    "DiscordLoggerImpl",
    "HANDOFF_THRESHOLD",
    "LIVE_DIGEST_RATE_LIMIT_FLOOR",
    "LIVE_DIGEST_WINDOW_SIZE",
    "LiveDigestState",
    "MAX_EMBED_FIELD_NAME_LENGTH",
    "MAX_EMBED_FIELD_VALUE_LENGTH",
    "MAX_EMBED_TITLE_LENGTH",
    "MAX_PAYLOAD_CHUNK_LENGTH",
    "ROUTINE_EVENT_EMOJIS",
    "WARNING_THRESHOLD",
    "build_status_card_description",
    "build_status_card_embed",
    "build_token_bar",
    "chunk_payload",
    "format_chunks",
    "format_token_bar",
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

BREADCRUMB_TRAIL = "Running → Reviewing → Verifying → ✅ Committed"
WARNING_THRESHOLD = 120_000
HANDOFF_THRESHOLD = 135_000
DEFAULT_CEILING = 150_000
LIVE_DIGEST_WINDOW_SIZE = 500
LIVE_DIGEST_RATE_LIMIT_FLOOR = 5.0


def build_token_bar(current: int, ceiling: int = DEFAULT_CEILING) -> str:
    """Construct a 10-block █/░ token bar string.

    Rules:
    - 10 blocks wide.
    - Blocks 1–8: green/plain filled blocks representing current token progress.
    - Block 9: yellow at >= 120,000 (warning threshold).
    - Block 10: red at >= 135,000 (handoff threshold).
    - Clamped to [0, ceiling].
    """
    safe_current = max(0, current)
    tenth = ceiling / 10 if ceiling > 0 else 15_000
    green_count = (
        min(8, math.ceil(safe_current / tenth))
        if safe_current > 0 and ceiling > 0
        else 0
    )
    green_filled = "█" * green_count
    green_empty = "░" * (8 - green_count)

    b9 = "█" if safe_current >= WARNING_THRESHOLD else "░"
    b10 = "█" if safe_current >= HANDOFF_THRESHOLD else "░"

    return f"{green_filled}{green_empty}{b9}{b10}"


def format_token_bar(current: int, ceiling: int = DEFAULT_CEILING) -> str:
    """Format token bar line: ~{round(current/1000)}k / 150k  {bar} {pct}%."""
    safe_current = max(0, current)
    bar = build_token_bar(safe_current, ceiling=ceiling)
    k_val = round(safe_current / 1000)
    pct = min(100, max(0, round(safe_current / ceiling * 100))) if ceiling > 0 else 0
    return f"~{k_val}k / {round(ceiling / 1000)}k  {bar} {pct}%"


def build_status_card_description(
    ticket_id: str,
    slug: str,
    spec: str,
    status: str,
    attempt: int | str = 1,
    tokens_current: int = 0,
    started_at: str = "",
    last_updated: str = "",
) -> str:
    """Construct monospace status card description text matching verbatim spec layout."""
    ticket_str = f"{ticket_id} · {slug}" if slug else ticket_id
    spec_str = Path(spec).stem if spec else "unknown"

    if BREADCRUMB_TRAIL in status:
        status_str = status
    else:
        status_str = f"{status}   ({BREADCRUMB_TRAIL})"

    attempt_str = f"{attempt} / 3" if isinstance(attempt, int) else str(attempt)
    tokens_str = format_token_bar(tokens_current)

    if not started_at:
        started_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    elif "UTC" in started_at:
        started_str = started_at
    else:
        try:
            dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            started_str = dt.strftime("%H:%M UTC")
        except Exception:
            started_str = f"{started_at} UTC"

    if not last_updated:
        last_updated_str = datetime.now(timezone.utc).strftime("%H:%M UTC")
    elif "UTC" in last_updated:
        last_updated_str = last_updated
    else:
        try:
            dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            last_updated_str = dt.strftime("%H:%M UTC")
        except Exception:
            last_updated_str = f"{last_updated} UTC"

    lines = [
        f"{'Ticket:':<14}{ticket_str}",
        f"{'Spec:':<14}{spec_str}",
        f"{'Status:':<14}{status_str}",
        f"{'Attempt:':<14}{attempt_str}",
        f"{'Tokens:':<14}{tokens_str}",
        f"{'Started:':<14}{started_str}",
        f"{'Last updated:':<14}{last_updated_str}",
    ]

    body = "\n".join(lines)
    return f"```\n{body}\n```"


def build_status_card_embed(
    ticket_id: str,
    slug: str,
    spec: str,
    status: str,
    attempt: int | str = 1,
    tokens_current: int = 0,
    started_at: str = "",
    last_updated: str = "",
) -> dict[str, Any]:
    """Construct blurple embed dictionary for Status Card."""
    desc = build_status_card_description(
        ticket_id=ticket_id,
        slug=slug,
        spec=spec,
        status=status,
        attempt=attempt,
        tokens_current=tokens_current,
        started_at=started_at,
        last_updated=last_updated,
    )
    return {
        "description": desc,
        "color": COLOR_BLURPLE,
    }


@dataclass
class LiveDigestState:
    """State tracking for a rolling Live Digest in a thread."""

    thread_id: str
    message_id: str
    buffer: str = ""
    last_edit_time: float = 0.0
    flush_task: asyncio.Task[None] | None = None
    done: bool = False


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
        live_digest_rate_limit_floor: float = LIVE_DIGEST_RATE_LIMIT_FLOOR,
    ) -> None:
        self._gateway = gateway
        self.notify_user_id = notify_user_id
        self.live_digest_rate_limit_floor = live_digest_rate_limit_floor
        self._status_cards: dict[str, dict[str, Any]] = {}
        self._live_digests: dict[str, LiveDigestState] = {}
        self._active_live_digest_thread_id: str | None = None

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

    async def post_status_card(
        self,
        ticket: Any,
        thread_id: str,
        *,
        status: str = "🟡 Running",
        attempt: int | str = 1,
        tokens_current: int = 0,
        started_at: str = "",
    ) -> str:
        """Post the initial pinned Status Card embed in a ticket thread."""
        ticket_id = getattr(ticket, "id", None) or (
            ticket.get("id") if isinstance(ticket, dict) else ""
        )
        slug = (
            getattr(ticket, "slug", None)
            or getattr(ticket, "title", "")
            or (ticket.get("slug") or ticket.get("title") if isinstance(ticket, dict) else "")
        )
        spec = (
            getattr(ticket, "spec_slug", None)
            or getattr(ticket, "spec_path", "")
            or (ticket.get("spec") or ticket.get("spec_path") if isinstance(ticket, dict) else "")
        )
        if not started_at:
            started_at = datetime.now(timezone.utc).strftime("%H:%M UTC")

        embed = build_status_card_embed(
            ticket_id=str(ticket_id),
            slug=str(slug),
            spec=str(spec),
            status=status,
            attempt=attempt,
            tokens_current=tokens_current,
            started_at=started_at,
        )

        msg_id = await self._gateway.post_message(thread_id, "", embed=embed)
        await self._gateway.pin_message(thread_id, msg_id)

        card_state = {
            "ticket_id": str(ticket_id),
            "slug": str(slug),
            "spec": str(spec),
            "started_at": started_at,
            "status": status,
            "attempt": attempt,
            "tokens_current": tokens_current,
        }
        self._status_cards[thread_id] = card_state
        self._status_cards[msg_id] = card_state
        return msg_id

    async def update_status_card(
        self,
        thread_id: str,
        message_id: str,
        *,
        status: str,
        attempt: int | str = 1,
        tokens_current: int = 0,
        started_at: str = "",
        ticket: Any = None,
        spec: str | None = None,
    ) -> None:
        """Update an existing Status Card message in-place with current execution state."""
        saved = self._status_cards.get(message_id) or self._status_cards.get(thread_id) or {}
        ticket_id = (
            getattr(ticket, "id", None)
            or (ticket.get("id") if isinstance(ticket, dict) else None)
            or saved.get("ticket_id", "T042")
        )
        slug = (
            getattr(ticket, "slug", None)
            or getattr(ticket, "title", None)
            or (ticket.get("slug") or ticket.get("title") if isinstance(ticket, dict) else None)
            or saved.get("slug", "defer-clean-slate")
        )
        spec_val = (
            spec
            or getattr(ticket, "spec_slug", None)
            or getattr(ticket, "spec_path", None)
            or (ticket.get("spec") or ticket.get("spec_path") if isinstance(ticket, dict) else None)
            or saved.get("spec", "05-presence-mode-and-discord")
        )
        started_val = started_at or saved.get("started_at", "")
        if not started_val:
            started_val = datetime.now(timezone.utc).strftime("%H:%M UTC")

        last_updated = datetime.now(timezone.utc).strftime("%H:%M UTC")

        embed = build_status_card_embed(
            ticket_id=str(ticket_id),
            slug=str(slug),
            spec=str(spec_val),
            status=status,
            attempt=attempt,
            tokens_current=tokens_current,
            started_at=started_val,
            last_updated=last_updated,
        )

        await self._gateway.edit_message(thread_id, message_id, "", embed=embed)

        updated_state = {
            "ticket_id": str(ticket_id),
            "slug": str(slug),
            "spec": str(spec_val),
            "started_at": started_val,
            "status": status,
            "attempt": attempt,
            "tokens_current": tokens_current,
            "last_updated": last_updated,
        }
        self._status_cards[thread_id] = updated_state
        self._status_cards[message_id] = updated_state

    async def start_live_digest(
        self,
        thread_id: str,
        initial_content: str = "",
    ) -> str:
        """Post the initial plain-text message for a rolling Live Digest."""
        msg_id = await self._gateway.post_message(thread_id, initial_content)
        state = LiveDigestState(
            thread_id=thread_id,
            message_id=msg_id,
            buffer=initial_content,
            last_edit_time=0.0,
            flush_task=None,
            done=False,
        )
        self._live_digests[thread_id] = state
        self._live_digests[msg_id] = state
        self._active_live_digest_thread_id = thread_id
        return msg_id

    async def update_live_digest(
        self,
        content_chunk: str = "",
        thread_id: str | None = None,
    ) -> None:
        """Append to rolling 500-char window and edit message subject to rate floor."""
        target_thread = thread_id or self._active_live_digest_thread_id
        if not target_thread or target_thread not in self._live_digests:
            return
        state = self._live_digests[target_thread]
        if state.done:
            return

        state.buffer += content_chunk
        if len(state.buffer) > LIVE_DIGEST_WINDOW_SIZE:
            state.buffer = state.buffer[-LIVE_DIGEST_WINDOW_SIZE:]

        loop = asyncio.get_running_loop()
        now = loop.time()
        floor = self.live_digest_rate_limit_floor

        if now - state.last_edit_time >= floor:
            if state.flush_task is not None and not state.flush_task.done():
                state.flush_task.cancel()
                state.flush_task = None
            await self._gateway.edit_message(state.thread_id, state.message_id, state.buffer)
            state.last_edit_time = loop.time()
        else:
            if state.flush_task is None or state.flush_task.done():
                delay = (state.last_edit_time + floor) - now
                state.flush_task = asyncio.create_task(
                    self._delayed_flush(state, max(0.0, delay))
                )

    async def _delayed_flush(self, state: LiveDigestState, delay: float) -> None:
        """Wait for rate limit delay then flush latest accumulated buffer."""
        try:
            await asyncio.sleep(delay)
            if not state.done:
                await self._gateway.edit_message(
                    state.thread_id, state.message_id, state.buffer
                )
                loop = asyncio.get_running_loop()
                state.last_edit_time = loop.time()
        except asyncio.CancelledError:
            pass
        finally:
            state.flush_task = None

    async def finish_live_digest(
        self,
        thread_id: str | None = None,
    ) -> None:
        """Fire a final edit appending '\\n[done]' and stop further digest edits."""
        target_thread = thread_id or self._active_live_digest_thread_id
        if not target_thread or target_thread not in self._live_digests:
            return
        state = self._live_digests[target_thread]
        state.done = True

        if state.flush_task is not None and not state.flush_task.done():
            state.flush_task.cancel()
            try:
                await state.flush_task
            except asyncio.CancelledError:
                pass
            state.flush_task = None

        final_content = f"{state.buffer}\n[done]"
        await self._gateway.edit_message(state.thread_id, state.message_id, final_content)
        loop = asyncio.get_running_loop()
        state.last_edit_time = loop.time()

