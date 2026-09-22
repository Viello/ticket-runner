"""Discord adapter stub for remote notifications (T066, Spec 05)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DiscordAdapter:
    """Stub adapter for Discord remote notifications.

    Provides a no-op send() method logging a warning so the orchestrator can
    fire-and-forget escalation messages before Spec 05's full discord.py adapter
    is implemented. Never raises an exception.
    """

    def __init__(
        self,
        token_env: str = "DISCORD_BOT_TOKEN",
        channel_id: str = "",
    ) -> None:
        self._token_env = token_env
        self._channel_id = channel_id

    @property
    def token_env(self) -> str:
        """Environment variable holding the Discord bot token."""
        return self._token_env

    @property
    def channel_id(self) -> str:
        """Target Discord channel identifier."""
        return self._channel_id

    def send(self, message: str) -> None:
        """Send a notification message to the configured Discord channel (stub)."""
        logger.warning(
            "DiscordAdapter.send called on stub: %s",
            message[:120].replace("\n", " "),
        )
