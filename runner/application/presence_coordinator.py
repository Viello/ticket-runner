"""Presence coordinator managing human presence mode transitions (T058, T085)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    from runner.application.state_coordinator import StateCoordinator
    from runner.ports.discord_logger import DiscordLogger
    from runner.ports.terminal_display import TerminalDisplay, UiEventSink

# Type alias for the replaceable timer factory seam.
# Signature: (delay_seconds, async_callback) -> asyncio.Task
TimerFactory = Callable[
    [float, Callable[[], Coroutine[Any, Any, None]]],
    Coroutine[Any, Any, "asyncio.Task[None]"],
]


async def _default_timer_factory(
    delay_seconds: float,
    callback: Callable[[], Coroutine[Any, Any, None]],
) -> asyncio.Task[None]:
    """Production timer factory using asyncio.create_task + asyncio.sleep."""

    async def _run() -> None:
        await asyncio.sleep(delay_seconds)
        await callback()

    return asyncio.create_task(_run())


class PresenceCoordinator:
    """Coordinates presence mode transitions between 'nearby' and 'away'."""

    def __init__(
        self,
        state_coordinator: StateCoordinator | None = None,
        terminal_display: TerminalDisplay | None = None,
        ui_event_sink: UiEventSink | None = None,
        idle_escalation_minutes: float = 3.0,
    ) -> None:
        self._state_coordinator = state_coordinator
        self._terminal_display = terminal_display
        self._ui_event_sink = ui_event_sink
        self._fallback_mode: str = "nearby"
        self._escalation_task: asyncio.Task[None] | None = None
        self._idle_escalation_minutes = float(idle_escalation_minutes)

    @property
    def current_mode(self) -> str:
        """Return the current active presence mode."""
        if self._state_coordinator is not None:
            return self._state_coordinator.get_or_create_state().presence_mode
        return self._fallback_mode

    def set_mode(self, mode: str) -> str:
        """Explicitly assign presence mode ('nearby' or 'away').

        Persists the updated mode via StateCoordinator and refreshes UI.

        Returns:
            The newly active presence mode string.
        """
        self._fallback_mode = mode

        if self._state_coordinator is not None:
            new_state = self._state_coordinator.set_presence_mode(mode)
            if self._terminal_display is not None:
                queue_remaining = getattr(self._terminal_display, "_queue_remaining", 0)
                try:
                    self._terminal_display.update_state(new_state, queue_remaining)
                except Exception:
                    pass
        elif self._terminal_display is not None:
            try:
                self._terminal_display.refresh()
            except Exception:
                pass

        if self._ui_event_sink is not None:
            try:
                self._ui_event_sink.emit("runner", f"Presence mode set to {mode}")
            except Exception:
                pass
        elif self._terminal_display is not None:
            try:
                self._terminal_display.emit("runner", f"Presence mode set to {mode}")
            except Exception:
                pass

        return mode

    def toggle_mode(self) -> str:
        """Toggle presence mode between 'nearby' and 'away'.

        Persists the updated mode via StateCoordinator, refreshes terminal display
        header row, and logs the change to the telemetry sink.

        Returns:
            The newly active presence mode string ('nearby' or 'away').
        """
        old_mode = self.current_mode
        new_mode = "away" if old_mode == "nearby" else "nearby"
        return self.set_mode(new_mode)

    async def schedule_escalation(
        self,
        ticket_id: str,
        thread_id: str,
        discord_logger: DiscordLogger,
        *,
        delay_seconds: float | None = None,
        timer_factory: TimerFactory | None = None,
    ) -> None:
        """Start (or replace) a cancellable idle escalation timer.

        On expiry the coordinator transitions to 'away' and posts:
        1. A plain-text ``<@notify_user_id>`` mention in *thread_id*.
        2. A yellow embed (colour ``0xFEE75C``) with title ``❓ Worker Question``.

        Calling this a second time cancels the pending timer before creating a
        new one (no timer stacking).

        Args:
            ticket_id: Active ticket identifier (for logging context).
            thread_id: Discord thread snowflake ID.
            discord_logger: DiscordLogger instance used to post the notification.
            delay_seconds: Seconds before escalation fires. If ``None``, defaults
                to ``idle_escalation_minutes * 60`` from config (fallback: 180s).
            timer_factory: Replaceable factory for timer creation (testing seam).
        """
        # Cancel any existing escalation task first (no stacking)
        self.cancel_escalation()

        if delay_seconds is None:
            delay_seconds = self._idle_escalation_minutes * 60.0

        factory = timer_factory or _default_timer_factory

        async def _on_escalation() -> None:
            self.set_mode("away")

            # Post plain-text mention first, then yellow embed
            notify_user_id = getattr(discord_logger, "notify_user_id", None) or ""
            if notify_user_id:
                mention_text = f"<@{notify_user_id}>"
            else:
                mention_text = "⚠️ Idle escalation"

            await discord_logger.log(
                "question_signal",
                mention_text,
                thread_id,
                "away",
                severity="critical",
            )

        self._escalation_task = await factory(delay_seconds, _on_escalation)

    def cancel_escalation(self) -> None:
        """Cancel the pending escalation timer if active.

        After cancellation, no Discord posts will fire from the cancelled timer.
        """
        if self._escalation_task is not None:
            self._escalation_task.cancel()
            self._escalation_task = None
