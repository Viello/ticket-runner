"""In-memory FakeDiscordLogger test double for DiscordLogger port (T082)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from runner.ports.discord_logger import DiscordLogger

__all__ = ["DiscordLogCall", "FakeDiscordLogger"]

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


@dataclass
class DiscordLogCall:
    """Record of a single log invocation on FakeDiscordLogger."""

    event_type: str
    payload: str
    thread_id: str
    presence_mode: str
    severity: str
    suppressed: bool
    embed: dict[str, Any] | None = None
    message_ids: list[str] = field(default_factory=list)


class FakeDiscordLogger(DiscordLogger):
    """In-memory test double conforming to DiscordLogger."""

    def __init__(self) -> None:
        self.calls: list[DiscordLogCall] = []
        self.embed_calls: list[tuple[str, dict[str, Any]]] = []
        self._next_id: int = 1

    def _generate_id(self) -> str:
        new_id = str(self._next_id)
        self._next_id += 1
        return new_id

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
        """Record structured event, resolve severity and suppression, bypass chunking."""
        resolved_severity = self.resolve_severity(event_type, severity)
        suppressed = self.is_suppressed(resolved_severity, presence_mode)

        message_ids: list[str] = []
        if not suppressed:
            message_ids.append(self._generate_id())

        call = DiscordLogCall(
            event_type=event_type,
            payload=payload,
            thread_id=thread_id,
            presence_mode=presence_mode,
            severity=resolved_severity,
            suppressed=suppressed,
            message_ids=list(message_ids),
        )
        self.calls.append(call)
        return message_ids

    async def post_embed(
        self,
        thread_id: str,
        embed_dict: dict[str, Any],
    ) -> list[str]:
        """Record embed post, bypass chunking."""
        self.embed_calls.append((thread_id, dict(embed_dict)))
        msg_id = self._generate_id()
        call = DiscordLogCall(
            event_type="embed",
            payload=embed_dict.get("description", ""),
            thread_id=thread_id,
            presence_mode="any",
            severity="critical",
            suppressed=False,
            embed=dict(embed_dict),
            message_ids=[msg_id],
        )
        self.calls.append(call)
        return [msg_id]

    @property
    def suppressed_calls(self) -> list[DiscordLogCall]:
        """Return all calls that were suppressed by presence mode."""
        return [c for c in self.calls if c.suppressed]

    @property
    def dispatched_calls(self) -> list[DiscordLogCall]:
        """Return all calls that were not suppressed."""
        return [c for c in self.calls if not c.suppressed]

    @property
    def last_call(self) -> DiscordLogCall | None:
        """Return the most recent call, or None."""
        return self.calls[-1] if self.calls else None

    def clear(self) -> None:
        """Clear all recorded calls."""
        self.calls.clear()
        self.embed_calls.clear()
