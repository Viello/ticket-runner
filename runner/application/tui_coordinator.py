"""TUI session pause-and-open protocol coordinator and modal state machine (T059)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from runner.adapters.ui.tui_launcher import TuiLauncher, is_detaching_terminal

if TYPE_CHECKING:
    from runner.application.state_coordinator import StateCoordinator
    from runner.application.worker_supervisor import WorkerSupervisor
    from runner.ports.command_runner import ProcessHandle
    from runner.ports.terminal_display import TerminalDisplay, UiEventSink

RESUME_BANNER: str = "Resuming after user inspection via TUI. Continue from where you left off."


class ModalState(str, Enum):
    """Modal state machine for TUI interactive session confirmation and lifecycle."""

    NORMAL = "NORMAL"
    CONFIRM_PENDING = "CONFIRM_PENDING"
    TUI_QUEUED = "TUI_QUEUED"
    TUI_OPEN = "TUI_OPEN"


class TuiCoordinator:
    """Coordinates two-key confirmation, dashboard freezing, external terminal lifecycle, and resumption."""

    def __init__(
        self,
        terminal_display: TerminalDisplay | None = None,
        launcher: TuiLauncher | None = None,
        state_coordinator: StateCoordinator | None = None,
        terminal_host: str = "wt.exe",
        supervisor: WorkerSupervisor | None = None,
        is_session_active: Callable[[], bool] | None = None,
        run_worker_fn: Callable[..., Awaitable[Any]] | None = None,
        ui_event_sink: UiEventSink | None = None,
        cwd: Path | None = None,
        resume_prompt: str = RESUME_BANNER,
    ) -> None:
        self._terminal_display = terminal_display
        self._launcher = launcher or TuiLauncher()
        self._state_coordinator = state_coordinator
        self._terminal_host = terminal_host
        self._supervisor = supervisor
        self._is_session_active = is_session_active
        self._run_worker_fn = run_worker_fn
        self._ui_event_sink = ui_event_sink
        self._cwd = cwd
        self._resume_prompt = resume_prompt

        self._modal_state: ModalState = ModalState.NORMAL
        self._resume_event: asyncio.Event = asyncio.Event()
        self._active_process: ProcessHandle | None = None

    @property
    def modal_state(self) -> ModalState:
        """Current modal state machine state."""
        return self._modal_state

    @property
    def is_confirm_pending(self) -> bool:
        """True when waiting for [y]/[n] confirmation."""
        return self._modal_state == ModalState.CONFIRM_PENDING

    @property
    def is_queued(self) -> bool:
        """True when TUI open intent is queued waiting for signal boundary."""
        return self._modal_state == ModalState.TUI_QUEUED

    @property
    def is_tui_open(self) -> bool:
        """True when external interactive TUI window is currently running."""
        return self._modal_state == ModalState.TUI_OPEN

    @property
    def terminal_host(self) -> str:
        """Configured terminal host binary."""
        return self._terminal_host

    @terminal_host.setter
    def terminal_host(self, host: str) -> None:
        self._terminal_host = host

    def handle_key_o(self) -> bool:
        """Handle 'o' hotkey press: enter confirm-pending state if in normal state."""
        if self._modal_state == ModalState.NORMAL:
            self._modal_state = ModalState.CONFIRM_PENDING
            if self._terminal_display is not None:
                self._terminal_display.set_legend_state("confirm_pending")
            if self._ui_event_sink is not None:
                self._ui_event_sink.emit("runner", "Open TUI? [y] confirm / [n] cancel")
            return True
        return False

    def handle_key_n(self) -> bool:
        """Handle 'n' hotkey press: cancel confirmation modal and restore normal state."""
        if self._modal_state == ModalState.CONFIRM_PENDING:
            self._modal_state = ModalState.NORMAL
            if self._terminal_display is not None:
                self._terminal_display.set_legend_state("normal")
            if self._ui_event_sink is not None:
                self._ui_event_sink.emit("runner", "TUI open cancelled.")
            return True
        return False

    async def handle_key_y(self) -> bool:
        """Handle 'y' hotkey press: confirm TUI open; queue if mid-run, launch if at boundary."""
        if self._modal_state != ModalState.CONFIRM_PENDING:
            return False

        active = False
        if self._is_session_active is not None:
            active = self._is_session_active()
        elif self._supervisor is not None:
            active = self._supervisor.is_running

        if active:
            self._modal_state = ModalState.TUI_QUEUED
            if self._terminal_display is not None:
                self._terminal_display.set_legend_state("tui_queued")
            if self._ui_event_sink is not None:
                self._ui_event_sink.emit(
                    "runner", "TUI open queued — waiting for signal boundary."
                )
            return True
        else:
            await self.launch_tui()
            return True

    def handle_key_r(self) -> bool:
        """Handle 'r' hotkey press: trigger immediate resume while in TUI_OPEN state."""
        if self._modal_state == ModalState.TUI_OPEN:
            self._resume_event.set()
            return True
        return False

    async def launch_tui(self, session_id: str | None = None) -> Any:
        """Launch external TUI session, freeze dashboard, and await exit or resume."""
        resolved_session = session_id
        if resolved_session is None and self._state_coordinator is not None:
            state = self._state_coordinator.get_or_create_state()
            resolved_session = state.opencode_session_id

        if resolved_session is None:
            self._modal_state = ModalState.NORMAL
            if self._terminal_display is not None:
                self._terminal_display.set_legend_state("normal")
            if self._ui_event_sink is not None:
                self._ui_event_sink.emit(
                    "runner", "Cannot open TUI: no active session ID found in state."
                )
            return None

        self._modal_state = ModalState.TUI_OPEN
        self._resume_event.clear()

        # a. Persist tui_open: true and tui_session_id via StateCoordinator
        if self._state_coordinator is not None:
            self._state_coordinator.set_tui_open(session_id=resolved_session)

        # b. Freeze Live dashboard and render warning panel
        if self._terminal_display is not None:
            if hasattr(self._terminal_display, "show_warning_panel"):
                self._terminal_display.show_warning_panel()
            elif hasattr(self._terminal_display, "set_legend_state"):
                self._terminal_display.set_legend_state("tui_open")

        if self._ui_event_sink is not None:
            self._ui_event_sink.emit(
                "runner",
                f"Opening {self._terminal_host} opencode --session {resolved_session}",
            )

        # c. Spawn configured terminal host
        handle = await self._launcher.launch(
            host=self._terminal_host,
            session_id=resolved_session,
            cwd=self._cwd,
        )
        self._active_process = handle

        # d. Wait for exit or [r] resume
        detaching = is_detaching_terminal(self._terminal_host)
        if detaching:
            await self._resume_event.wait()
        else:
            wait_task = asyncio.create_task(handle.wait())
            resume_task = asyncio.create_task(self._resume_event.wait())
            done, pending = await asyncio.wait(
                [wait_task, resume_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        # 3. Resume managed execution
        return await self.resume(session_id=resolved_session)

    async def resume(self, session_id: str | None = None) -> Any:
        """Clear TUI state, restore dashboard layout, and start fresh Session Run with resume banner."""
        # a. Clear tui_open and tui_session_id in state.json
        if self._state_coordinator is not None:
            self._state_coordinator.clear_tui()

        # b. Restore normal Rich Live dashboard layout
        if self._terminal_display is not None:
            if hasattr(self._terminal_display, "restore_dashboard"):
                self._terminal_display.restore_dashboard()
            elif hasattr(self._terminal_display, "set_legend_state"):
                self._terminal_display.set_legend_state("normal")

        self._modal_state = ModalState.NORMAL
        self._active_process = None

        # c. Fresh Session Run on same session id with resume banner
        if self._ui_event_sink is not None:
            self._ui_event_sink.emit(
                "runner", "TUI closed. Starting fresh Session Run with resume banner."
            )
            self._ui_event_sink.emit("worker", self._resume_prompt)

        ticket_id = None
        if self._state_coordinator is not None:
            state = self._state_coordinator.get_or_create_state()
            ticket_id = state.active_ticket_id

        if self._run_worker_fn is not None:
            return await self._run_worker_fn(
                ticket=ticket_id or "UNKNOWN",
                prompt=self._resume_prompt,
                session_id=session_id,
            )
        elif self._supervisor is not None and ticket_id:
            return await self._supervisor.run(
                ticket=ticket_id,
                prompt=self._resume_prompt,
                session_id=session_id,
            )
        return None

    async def on_signal_boundary(
        self, session_id: str | None = None, ticket: str | None = None
    ) -> Any:
        """Hook invoked at signal boundary (e.g. between session runs)."""
        if self.is_queued:
            return await self.launch_tui(session_id=session_id)
        return None


__all__ = [
    "ModalState",
    "RESUME_BANNER",
    "TuiCoordinator",
]
