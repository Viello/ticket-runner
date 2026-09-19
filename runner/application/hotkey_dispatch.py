"""Hotkey action dispatcher coordinating terminal hotkey events (T058)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from runner.application.worker_supervisor import RunTerminationReason

if TYPE_CHECKING:
    from runner.application.presence_coordinator import PresenceCoordinator
    from runner.application.queue_orchestrator import QueueOrchestrator
    from runner.application.state_coordinator import StateCoordinator
    from runner.application.worker_supervisor import WorkerSupervisor
    from runner.ports.terminal_display import TerminalDisplay, UiEventSink


class HotkeyDispatcher:
    """Dispatches keyboard hotkeys to orchestrator, presence, and supervisor actions."""

    def __init__(
        self,
        orchestrator: QueueOrchestrator | None = None,
        presence_coordinator: PresenceCoordinator | None = None,
        supervisor: WorkerSupervisor | None = None,
        stop_event: asyncio.Event | None = None,
        state_coordinator: StateCoordinator | None = None,
        ui_event_sink: UiEventSink | None = None,
        terminal_display: TerminalDisplay | None = None,
        on_shutdown: Callable[[], Any] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._presence_coordinator = presence_coordinator
        self._supervisor = supervisor
        self._stop_event = stop_event
        self._state_coordinator = state_coordinator
        self._ui_event_sink = ui_event_sink
        self._terminal_display = terminal_display
        self._on_shutdown = on_shutdown

        self._handlers: dict[str, Callable[[], Any]] = {
            "p": self.handle_pause,
            "m": self.handle_toggle_mode,
            "q": self.handle_quit,
        }

    def register_handler(self, key: str, handler: Callable[[], Any]) -> None:
        """Register or override an action handler for a hotkey."""
        self._handlers[key.lower()] = handler

    def handle_pause(self) -> None:
        """Handle 'p' hotkey: toggle paused / unpaused state on QueueOrchestrator."""
        if self._orchestrator is None:
            return

        if self._orchestrator.is_paused:
            self._orchestrator.resume()
        else:
            self._orchestrator.pause()

        if self._terminal_display is not None and self._state_coordinator is not None:
            try:
                state = self._state_coordinator.get_or_create_state()
                queue_remaining = getattr(self._terminal_display, "_queue_remaining", 0)
                self._terminal_display.update_state(state, queue_remaining)
            except Exception:
                pass

    def handle_toggle_mode(self) -> str | None:
        """Handle 'm' hotkey: toggle presence mode between nearby and away."""
        if self._presence_coordinator is not None:
            return self._presence_coordinator.toggle_mode()
        return None

    def handle_quit(self) -> None:
        """Handle 'q' hotkey: trigger graceful shutdown of subprocesses and runner."""
        if self._stop_event is not None and not self._stop_event.is_set():
            self._stop_event.set()

        if self._supervisor is not None:
            try:
                self._supervisor.request_kill(RunTerminationReason.KILLED_INTERRUPT)
            except Exception:
                pass

        if self._state_coordinator is not None:
            try:
                state = self._state_coordinator.get_or_create_state()
                self._state_coordinator.save_state(state)
            except Exception:
                pass

        if self._ui_event_sink is not None:
            try:
                self._ui_event_sink.emit("runner", "Quit requested by operator via hotkey [q]")
            except Exception:
                pass
        elif self._terminal_display is not None:
            try:
                self._terminal_display.emit("runner", "Quit requested by operator via hotkey [q]")
            except Exception:
                pass

        if self._on_shutdown is not None:
            try:
                res = self._on_shutdown()
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    def dispatch(self, key: str) -> Any:
        """Dispatch a single keypress string to its registered handler."""
        handler = self._handlers.get(key.lower())
        if handler is not None:
            return handler()
        return None

    def __call__(self, key: str) -> Any:
        """Callable protocol support to pass dispatcher directly as on_key callback."""
        return self.dispatch(key)
