"""Application service coordinating runner state transitions and durable persistence."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from runner.domain.state import RunnerState, StateStatus, TokenState
from runner.ports.state_store import StateStore
from runner.ports.terminal_display import TerminalDisplay


class StateCoordinator:
    """Coordinates RunnerState transitions and atomic disk persistence via StateStore."""

    def __init__(
        self,
        state_store: StateStore,
        initial_state: RunnerState | None = None,
        branch: str = "agent/ticket-runner",
        selected_model: str | None = None,
        presence_mode: str = "nearby",
        clock: Callable[[], float] | None = None,
        terminal_display: TerminalDisplay | None = None,
    ) -> None:
        self._state_store = state_store
        self._current_state: RunnerState | None = initial_state
        self._branch = branch
        self._selected_model = selected_model
        self._presence_mode = presence_mode
        self._clock = clock
        self._terminal_display = terminal_display

    @property
    def current_state(self) -> RunnerState | None:
        """Return the in-memory cached RunnerState, or None if uninitialized."""
        return self._current_state

    @property
    def state_store(self) -> StateStore:
        """Return the underlying StateStore port adapter."""
        return self._state_store

    def load_state(self) -> RunnerState | None:
        """Read and parse the persisted state document.

        Returns:
            The parsed RunnerState, or None if the state file does not exist.

        Raises:
            StateFormatError: If the state document is malformed or invalid schema.
        """
        doc = self._state_store.read()
        if doc is None:
            return None
        state = RunnerState.from_dict(doc)
        self._current_state = state
        return state

    def save_state(self, state: RunnerState) -> None:
        """Persist RunnerState to disk, merging with existing document to retain unmanaged keys.

        Preserves:
        - Any unmanaged keys from external tools or future specs.
        - `selected_model` written by ModelSelectionInteractor if `state.selected_model` is None.
        """
        existing: dict[str, Any] = {}
        try:
            raw = self._state_store.read()
            if isinstance(raw, dict):
                existing = dict(raw)
        except Exception:
            existing = {}

        state_dict = state.to_dict()

        # Retain selected_model from existing if not explicitly set on state
        if state_dict.get("selected_model") is None and existing.get("selected_model") is not None:
            state_dict["selected_model"] = existing["selected_model"]
            if state.selected_model is None:
                state = replace(state, selected_model=existing["selected_model"])

        # Merge: existing unmanaged keys round-trip, state fields take precedence
        merged = dict(existing)
        merged.update(state_dict)

        self._state_store.write(merged)
        self._current_state = state
        if self._terminal_display is not None:
            try:
                self._terminal_display.update_state(state, 0)
            except Exception:
                pass

    def get_or_create_state(self) -> RunnerState:
        """Return current state, loading from disk or initializing a default idle state."""
        if self._current_state is not None:
            return self._current_state

        try:
            loaded = self.load_state()
            if loaded is not None:
                return loaded
        except Exception:
            pass

        # Check if existing document in store has selected_model or branch
        model = self._selected_model
        branch = self._branch
        try:
            raw = self._state_store.read()
            if isinstance(raw, dict):
                if model is None and raw.get("selected_model") is not None:
                    model = str(raw["selected_model"])
                if raw.get("branch"):
                    branch = str(raw["branch"])
        except Exception:
            pass

        state = RunnerState.idle(
            branch=branch,
            selected_model=model,
            presence_mode=self._presence_mode,
        )
        self._current_state = state
        return state

    # --- Dispatcher Transitions ---

    def transition_to_working(
        self,
        ticket_id: str,
        session_id: str | None = None,
        verification_attempts: int = 0,
    ) -> RunnerState:
        """Transition current state to WORKING and persist atomically."""
        current = self.get_or_create_state()
        new_state = current.to_working(
            ticket_id=ticket_id,
            session_id=session_id,
            verification_attempts=verification_attempts,
        )
        self.save_state(new_state)
        return new_state

    def transition_to_gatekeeper(
        self,
        verification_attempts: int | None = None,
    ) -> RunnerState:
        """Transition current state to GATEKEEPER and persist atomically."""
        current = self.get_or_create_state()
        new_state = current.to_gatekeeper(verification_attempts=verification_attempts)
        self.save_state(new_state)
        return new_state

    def transition_to_idle(self) -> RunnerState:
        """Transition current state to IDLE and persist atomically."""
        current = self.get_or_create_state()
        new_state = current.to_idle()
        self.save_state(new_state)
        return new_state

    def transition_to_pause_requested(self) -> RunnerState:
        """Transition current state to PAUSE_REQUESTED and persist atomically."""
        current = self.get_or_create_state()
        new_state = current.to_pause_requested()
        self.save_state(new_state)
        return new_state

    def request_pause(self) -> RunnerState:
        """Request runner to pause execution after the current ticket completes verification."""
        return self.transition_to_pause_requested()

    def transition_to_waiting_for_user(self) -> RunnerState:
        """Transition current state to WAITING_FOR_USER and persist atomically."""
        current = self.get_or_create_state()
        new_state = current.to_waiting_for_user()
        self.save_state(new_state)
        return new_state

    def transition_to_circuit_breaker_tripped(self) -> RunnerState:
        """Transition current state to CIRCUIT_BREAKER_TRIPPED and persist atomically."""
        current = self.get_or_create_state()
        new_state = current.to_circuit_breaker_tripped()
        self.save_state(new_state)
        return new_state

    def record_tokens(
        self,
        current: int,
        warning_sent: bool | None = None,
    ) -> RunnerState:
        """Update token consumption telemetry and persist atomically."""
        state = self.get_or_create_state()
        new_state = state.record_tokens(current=current, warning_sent=warning_sent)
        self.save_state(new_state)
        return new_state

    def set_presence_mode(self, mode: str) -> RunnerState:
        """Update presence mode and persist atomically."""
        state = self.get_or_create_state()
        new_state = state.set_presence_mode(mode=mode)
        self.save_state(new_state)
        return new_state

    def set_tui_open(self, session_id: str | None = None) -> RunnerState:
        """Set TUI open flag and persist atomically."""
        state = self.get_or_create_state()
        new_state = state.set_tui_open(session_id=session_id)
        self.save_state(new_state)
        return new_state

    def clear_tui(self) -> RunnerState:
        """Clear TUI open flag and persist atomically."""
        state = self.get_or_create_state()
        new_state = state.clear_tui()
        self.save_state(new_state)
        return new_state

    def record_checkpoint(self, checkpoint_path: str | Path | None) -> RunnerState:
        """Update last checkpoint path and persist atomically."""
        state = self.get_or_create_state()
        new_state = state.set_checkpoint(checkpoint_path)
        self.save_state(new_state)
        return new_state

    def record_session_id(self, session_id: str) -> RunnerState:
        """Update opencode session ID and persist atomically."""
        state = self.get_or_create_state()
        if state.opencode_session_id == session_id:
            return state
        new_state = replace(state, opencode_session_id=session_id)
        self.save_state(new_state)
        return new_state
