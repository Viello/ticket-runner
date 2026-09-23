"""DiscordThreadManager application service managing thread-per-ticket lifecycle (T084)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from runner.adapters.discord.logger import (
    COLOR_GREEN,
    DiscordLoggerImpl,
    build_status_card_embed,
)
from runner.domain.exceptions import DiscordGatewayError
from runner.ports.discord_gateway import DiscordGateway
from runner.ports.discord_logger import DiscordLogger

__all__ = ["COLOR_GREEN", "DiscordThreadManager"]

_logger = logging.getLogger(__name__)


class DiscordThreadManager:
    """Application service managing thread-per-ticket Discord lifecycle.

    Owns thread creation on ticket start, Status Card pinning, Live Digest
    initialization, commit notices, and thread archival on ticket pass.
    """

    def __init__(
        self,
        gateway: DiscordGateway,
        logger: DiscordLogger | None = None,
        discord_enabled: bool = True,
    ) -> None:
        self._gateway = gateway
        self._logger: DiscordLogger = (
            logger if logger is not None else DiscordLoggerImpl(gateway)
        )
        self.discord_enabled = discord_enabled
        self._threads: dict[str, dict[str, Any]] = {}

    def _resolve_thread_name(self, ticket_id: str, slug: str) -> str:
        """Format thread name as exactly {ticket_id}-{slug}."""
        if not slug:
            return str(ticket_id)
        if slug.startswith(f"{ticket_id}-"):
            return str(slug)
        return f"{ticket_id}-{slug}"

    async def open_ticket_thread(
        self,
        ticket: Any,
        channel_id: str,
        *,
        starter_message: str = "",
        status: str = "🟡 Running",
        attempt: int | str = 1,
        tokens_current: int = 0,
        started_at: str = "",
    ) -> tuple[str, str]:
        """Open a thread for the active ticket and initialize Status Card and Live Digest.

        1. Posts the Status Card starter embed in channel_id via gateway.create_thread.
        2. Pins the Status Card immediately after thread creation.
        3. Starts the rolling Live Digest in the created thread.
        4. Returns (thread_id, status_card_message_id).
        When discord_enabled is False, performs no calls and returns ("", "").
        """
        if not self.discord_enabled:
            return ("", "")

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

        thread_name = self._resolve_thread_name(str(ticket_id), str(slug))
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

        # 1. Create thread from starter Status Card embed in channel_id
        thread_id, starter_msg_id = await self._gateway.create_thread(
            channel_id,
            thread_name,
            starter_message,
            embed=embed,
        )

        # 2. Pin Status Card immediately
        try:
            await self._gateway.pin_message(thread_id, starter_msg_id)
        except DiscordGatewayError as exc:
            _logger.warning("Failed to pin Status Card in %s: %s", thread_id, exc)

        # 3. Start Live Digest
        await self._logger.start_live_digest(thread_id)

        # Sync card state to logger cache if present
        card_state = {
            "ticket_id": str(ticket_id),
            "slug": str(slug),
            "spec": str(spec),
            "started_at": started_at,
            "status": status,
            "attempt": attempt,
            "tokens_current": tokens_current,
        }
        if hasattr(self._logger, "_status_cards"):
            self._logger._status_cards[thread_id] = card_state
            self._logger._status_cards[starter_msg_id] = card_state

        self._threads[thread_id] = {
            "ticket": ticket,
            "starter_msg_id": starter_msg_id,
            "channel_id": channel_id,
            "card_state": card_state,
        }
        self._threads[starter_msg_id] = self._threads[thread_id]

        return (thread_id, starter_msg_id)

    async def close_ticket_thread(
        self,
        thread_id: str,
        status_card_message_id: str,
        commit_summary: str,
    ) -> None:
        """Close ticket thread upon commit approval.

        1. Posts commit summary embed (green, title '✅ Committed').
        2. Updates Status Card to '✅ Committed' phase.
        3. Archives thread via gateway.archive_thread(thread_id).
        """
        if not self.discord_enabled:
            return

        commit_embed = {
            "title": "✅ Committed",
            "description": commit_summary,
            "color": COLOR_GREEN,
        }

        # Finish live digest if not already finished
        await self.finish_live_digest(thread_id)

        # 1. Post commit summary embed
        if hasattr(self._logger, "post_embed"):
            await self._logger.post_embed(thread_id, commit_embed)
        else:
            await self._gateway.post_message(thread_id, "", embed=commit_embed)

        # 2. Update Status Card to '✅ Committed'
        await self.update_status_card(
            thread_id,
            status_card_message_id,
            status="✅ Committed",
        )

        # 3. Archive and lock thread; handle already-locked/archived gracefully
        try:
            await self._gateway.archive_thread(thread_id)
        except DiscordGatewayError as exc:
            _logger.warning("Failed to archive thread %s: %s", thread_id, exc)

    async def update_status_card(
        self,
        thread_id: str,
        message_id: str,
        **fields: Any,
    ) -> None:
        """Delegate Status Card in-place updates to logger."""
        if not self.discord_enabled:
            return
        await self._logger.update_status_card(thread_id, message_id, **fields)

    async def update_live_digest(
        self,
        content_chunk: str = "",
        thread_id: str | None = None,
    ) -> None:
        """Forward live digest chunk update to logger."""
        if not self.discord_enabled:
            return
        if hasattr(self._logger, "update_live_digest"):
            await self._logger.update_live_digest(content_chunk, thread_id=thread_id)

    async def finish_live_digest(
        self,
        thread_id: str | None = None,
    ) -> None:
        """Forward live digest finish completion to logger."""
        if not self.discord_enabled:
            return
        if hasattr(self._logger, "finish_live_digest"):
            await self._logger.finish_live_digest(thread_id=thread_id)
