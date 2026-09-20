"""Presence coordinator managing human presence mode transitions (T058)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runner.application.state_coordinator import StateCoordinator
    from runner.ports.terminal_display import TerminalDisplay, UiEventSink


class PresenceCoordinator:
    """Coordinates presence mode transitions between 'nearby' and 'away'."""

    def __init__(
        self,
        state_coordinator: StateCoordinator | None = None,
        terminal_display: TerminalDisplay | None = None,
        ui_event_sink: UiEventSink | None = None,
    ) -> None:
        self._state_coordinator = state_coordinator
        self._terminal_display = terminal_display
        self._ui_event_sink = ui_event_sink
        self._fallback_mode: str = "nearby"

    @property
    def current_mode(self) -> str:
        """Return the current active presence mode."""
        if self._state_coordinator is not None:
            return self._state_coordinator.get_or_create_state().presence_mode
        return self._fallback_mode

    def toggle_mode(self) -> str:
        """Toggle presence mode between 'nearby' and 'away'.

        Persists the updated mode via StateCoordinator, refreshes terminal display
        header row, and logs the change to the telemetry sink.

        Returns:
            The newly active presence mode string ('nearby' or 'away').
        """
        old_mode = self.current_mode
        new_mode = "away" if old_mode == "nearby" else "nearby"
        self._fallback_mode = new_mode

        if self._state_coordinator is not None:
            new_state = self._state_coordinator.set_presence_mode(new_mode)
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
                self._ui_event_sink.emit("runner", f"Presence mode changed to {new_mode}")
            except Exception:
                pass
        elif self._terminal_display is not None:
            try:
                self._terminal_display.emit("runner", f"Presence mode changed to {new_mode}")
            except Exception:
                pass

        return new_mode
