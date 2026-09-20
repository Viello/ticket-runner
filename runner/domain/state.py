"""RunnerState domain entity, StateStatus enum, and TokenState."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from runner.domain.exceptions import StateFormatError


def _now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_iso_timestamp(value: object, field_name: str) -> str:
    """Validate that a value is a non-empty ISO-8601 timestamp string."""
    if not isinstance(value, str) or not value.strip():
        raise StateFormatError(
            f"Field '{field_name}' must be an ISO-8601 timestamp string, got: {value!r}"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception as exc:
        raise StateFormatError(
            f"Field '{field_name}' must be a valid ISO-8601 timestamp, got: {value!r}"
        ) from exc
    return value


class StateStatus(str, Enum):
    """Execution status for the Runner orchestrator."""

    IDLE = "IDLE"
    WORKING = "WORKING"
    GATEKEEPER = "GATEKEEPER"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    CIRCUIT_BREAKER_TRIPPED = "CIRCUIT_BREAKER_TRIPPED"


VALID_PRESENCE_MODES = ("nearby", "away")

REQUIRED_STATE_FIELDS = (
    "active_ticket_id",
    "status",
    "opencode_session_id",
    "selected_model",
    "presence_mode",
    "verification_attempts",
    "tokens",
    "branch",
    "started_at",
    "last_checkpoint",
    "last_updated",
)


@dataclass(frozen=True)
class TokenState:
    """Nested token tracking state within RunnerState."""

    current: int = 0
    warning_sent: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.current, bool) or not isinstance(self.current, int) or self.current < 0:
            raise StateFormatError(
                f"Token count 'current' must be a non-negative integer, got: {self.current!r}"
            )
        if not isinstance(self.warning_sent, bool):
            raise StateFormatError(
                f"Token flag 'warning_sent' must be a boolean, got: {self.warning_sent!r}"
            )

    def __getitem__(self, item: str) -> Any:
        if item == "current":
            return self.current
        if item == "warning_sent":
            return self.warning_sent
        raise KeyError(item)

    def to_dict(self) -> dict[str, Any]:
        """Serialize token state to a dictionary."""
        return {"current": self.current, "warning_sent": self.warning_sent}

    @classmethod
    def from_dict(cls, data: object) -> TokenState:
        """Parse token state from dictionary payload."""
        if not isinstance(data, Mapping):
            raise StateFormatError(f"'tokens' must be an object, got: {type(data).__name__}")
        if "current" not in data:
            raise StateFormatError("Missing required field 'current' in tokens")
        if "warning_sent" not in data:
            raise StateFormatError("Missing required field 'warning_sent' in tokens")
        return cls(current=data["current"], warning_sent=data["warning_sent"])


@dataclass(frozen=True)
class RunnerState:
    """Authoritative domain entity modeling Runner execution state (Spec 06)."""

    active_ticket_id: str | None
    status: StateStatus
    opencode_session_id: str | None
    selected_model: str | None
    presence_mode: str
    verification_attempts: int
    tokens: TokenState
    branch: str
    started_at: str
    last_checkpoint: str | None
    tui_open: bool = False
    tui_session_id: str | None = None
    last_updated: str = ""

    def __post_init__(self) -> None:
        if not self.last_updated:
            object.__setattr__(self, "last_updated", _now_iso())

        # Coerce status
        if isinstance(self.status, str) and not isinstance(self.status, StateStatus):
            try:
                object.__setattr__(self, "status", StateStatus(self.status))
            except ValueError:
                valid_statuses = ", ".join(s.value for s in StateStatus)
                raise StateFormatError(
                    f"Invalid status '{self.status}'. Must be one of: {valid_statuses}"
                )
        elif not isinstance(self.status, StateStatus):
            raise StateFormatError(f"Field 'status' must be StateStatus, got: {self.status!r}")

        # Validate active_ticket_id
        if self.active_ticket_id is not None and not isinstance(self.active_ticket_id, str):
            raise StateFormatError(
                f"Field 'active_ticket_id' must be a string or null, got: {self.active_ticket_id!r}"
            )

        # Validate opencode_session_id
        if self.opencode_session_id is not None and not isinstance(self.opencode_session_id, str):
            raise StateFormatError(
                f"Field 'opencode_session_id' must be a string or null, got: {self.opencode_session_id!r}"
            )

        # Validate selected_model
        if self.selected_model is not None and not isinstance(self.selected_model, str):
            raise StateFormatError(
                f"Field 'selected_model' must be a string or null, got: {self.selected_model!r}"
            )

        # Validate presence_mode
        if not isinstance(self.presence_mode, str) or self.presence_mode not in VALID_PRESENCE_MODES:
            raise StateFormatError(
                f"Field 'presence_mode' must be 'nearby' or 'away', got: {self.presence_mode!r}"
            )

        # Validate verification_attempts
        if (
            isinstance(self.verification_attempts, bool)
            or not isinstance(self.verification_attempts, int)
            or self.verification_attempts < 0
        ):
            raise StateFormatError(
                f"Field 'verification_attempts' must be an integer >= 0, got: {self.verification_attempts!r}"
            )

        # Coerce tokens
        if isinstance(self.tokens, Mapping) and not isinstance(self.tokens, TokenState):
            object.__setattr__(self, "tokens", TokenState.from_dict(self.tokens))
        elif not isinstance(self.tokens, TokenState):
            raise StateFormatError(f"Field 'tokens' must be TokenState, got: {type(self.tokens).__name__}")

        # Validate branch
        if not isinstance(self.branch, str) or not self.branch.strip():
            raise StateFormatError(f"Field 'branch' must be a non-empty string, got: {self.branch!r}")

        # Validate timestamps
        _validate_iso_timestamp(self.started_at, "started_at")
        updated = self.last_updated if self.last_updated else _now_iso()
        _validate_iso_timestamp(updated, "last_updated")
        if not self.last_updated:
            object.__setattr__(self, "last_updated", updated)

        # Validate last_checkpoint
        if self.last_checkpoint is not None and not isinstance(self.last_checkpoint, str):
            raise StateFormatError(
                f"Field 'last_checkpoint' must be a string or null, got: {self.last_checkpoint!r}"
            )

        # Validate tui fields
        if not isinstance(self.tui_open, bool):
            raise StateFormatError(f"Field 'tui_open' must be a boolean, got: {self.tui_open!r}")
        if self.tui_session_id is not None and not isinstance(self.tui_session_id, str):
            raise StateFormatError(
                f"Field 'tui_session_id' must be a string or null, got: {self.tui_session_id!r}"
            )

    @classmethod
    def idle(
        cls,
        branch: str = "agent/ticket-runner",
        selected_model: str | None = None,
        presence_mode: str = "nearby",
        started_at: str | None = None,
    ) -> RunnerState:
        """Construct an initial clean idle state."""
        now = _now_iso()
        return cls(
            active_ticket_id=None,
            status=StateStatus.IDLE,
            opencode_session_id=None,
            selected_model=selected_model,
            presence_mode=presence_mode,
            verification_attempts=0,
            tokens=TokenState(),
            branch=branch,
            started_at=started_at or now,
            last_checkpoint=None,
            tui_open=False,
            tui_session_id=None,
            last_updated=now,
        )

    @classmethod
    def from_dict(cls, data: object) -> RunnerState:
        """Parse RunnerState from dictionary payload."""
        if not isinstance(data, Mapping):
            raise StateFormatError(f"Expected state document to be a mapping, got: {type(data).__name__}")

        for field in REQUIRED_STATE_FIELDS:
            if field not in data:
                raise StateFormatError(f"Missing required field '{field}' in state document")

        _validate_iso_timestamp(data["started_at"], "started_at")
        _validate_iso_timestamp(data["last_updated"], "last_updated")

        tui_open = data.get("tui_open", False)
        tui_session_id = data.get("tui_session_id", None)

        return cls(
            active_ticket_id=data["active_ticket_id"],  # type: ignore[arg-type]
            status=data["status"],  # type: ignore[arg-type]
            opencode_session_id=data["opencode_session_id"],  # type: ignore[arg-type]
            selected_model=data["selected_model"],  # type: ignore[arg-type]
            presence_mode=data["presence_mode"],  # type: ignore[arg-type]
            verification_attempts=data["verification_attempts"],  # type: ignore[arg-type]
            tokens=data["tokens"],  # type: ignore[arg-type]
            branch=data["branch"],  # type: ignore[arg-type]
            started_at=data["started_at"],  # type: ignore[arg-type]
            last_checkpoint=data["last_checkpoint"],  # type: ignore[arg-type]
            tui_open=tui_open,  # type: ignore[arg-type]
            tui_session_id=tui_session_id,  # type: ignore[arg-type]
            last_updated=data["last_updated"],  # type: ignore[arg-type]
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to full 13-field dictionary payload."""
        return {
            "active_ticket_id": self.active_ticket_id,
            "status": self.status.value,
            "opencode_session_id": self.opencode_session_id,
            "selected_model": self.selected_model,
            "presence_mode": self.presence_mode,
            "verification_attempts": self.verification_attempts,
            "tokens": self.tokens.to_dict(),
            "branch": self.branch,
            "started_at": self.started_at,
            "last_checkpoint": self.last_checkpoint,
            "tui_open": self.tui_open,
            "tui_session_id": self.tui_session_id,
            "last_updated": self.last_updated,
        }

    # --- Immutable Transition Helper Methods ---

    def to_working(
        self,
        ticket_id: str,
        session_id: str | None = None,
        verification_attempts: int = 0,
    ) -> RunnerState:
        """Return a new RunnerState transitioned to WORKING status."""
        if not isinstance(ticket_id, str) or not ticket_id.strip():
            raise StateFormatError(f"Field 'ticket_id' must be a non-empty string, got: {ticket_id!r}")

        resolved_session = session_id if session_id is not None else (
            self.opencode_session_id if self.active_ticket_id == ticket_id else None
        )

        return replace(
            self,
            status=StateStatus.WORKING,
            active_ticket_id=ticket_id,
            opencode_session_id=resolved_session,
            verification_attempts=verification_attempts,
            last_updated=_now_iso(),
        )

    def to_gatekeeper(self, verification_attempts: int | None = None) -> RunnerState:
        """Return a new RunnerState transitioned to GATEKEEPER status."""
        if self.active_ticket_id is None:
            raise StateFormatError("Cannot transition to GATEKEEPER without active ticket")

        attempts = (
            verification_attempts
            if verification_attempts is not None
            else self.verification_attempts
        )

        return replace(
            self,
            status=StateStatus.GATEKEEPER,
            verification_attempts=attempts,
            last_updated=_now_iso(),
        )

    def to_idle(self) -> RunnerState:
        """Return a new RunnerState transitioned to IDLE status."""
        return replace(
            self,
            status=StateStatus.IDLE,
            active_ticket_id=None,
            opencode_session_id=None,
            verification_attempts=0,
            tokens=TokenState(current=0, warning_sent=False),
            last_checkpoint=None,
            tui_open=False,
            tui_session_id=None,
            last_updated=_now_iso(),
        )

    def to_pause_requested(self) -> RunnerState:
        """Return a new RunnerState transitioned to PAUSE_REQUESTED status."""
        return replace(
            self,
            status=StateStatus.PAUSE_REQUESTED,
            last_updated=_now_iso(),
        )

    def to_waiting_for_user(self) -> RunnerState:
        """Return a new RunnerState transitioned to WAITING_FOR_USER status."""
        return replace(
            self,
            status=StateStatus.WAITING_FOR_USER,
            last_updated=_now_iso(),
        )

    def to_circuit_breaker_tripped(self) -> RunnerState:
        """Return a new RunnerState transitioned to CIRCUIT_BREAKER_TRIPPED status."""
        return replace(
            self,
            status=StateStatus.CIRCUIT_BREAKER_TRIPPED,
            last_updated=_now_iso(),
        )

    def record_tokens(self, current: int, warning_sent: bool | None = None) -> RunnerState:
        """Return a new RunnerState with updated token telemetry."""
        ws = warning_sent if warning_sent is not None else self.tokens.warning_sent
        new_tokens = TokenState(current=current, warning_sent=ws)
        return replace(
            self,
            tokens=new_tokens,
            last_updated=_now_iso(),
        )

    def set_presence_mode(self, mode: str) -> RunnerState:
        """Return a new RunnerState with updated presence mode."""
        if mode not in VALID_PRESENCE_MODES:
            raise StateFormatError(
                f"Field 'presence_mode' must be 'nearby' or 'away', got: {mode!r}"
            )
        return replace(
            self,
            presence_mode=mode,
            last_updated=_now_iso(),
        )

    def set_tui_open(self, session_id: str | None = None) -> RunnerState:
        """Return a new RunnerState with TUI window open flag set."""
        resolved_session = session_id or self.opencode_session_id
        return replace(
            self,
            tui_open=True,
            tui_session_id=resolved_session,
            last_updated=_now_iso(),
        )

    def clear_tui(self) -> RunnerState:
        """Return a new RunnerState with TUI window closed and flags cleared."""
        return replace(
            self,
            tui_open=False,
            tui_session_id=None,
            last_updated=_now_iso(),
        )

    def set_checkpoint(self, path: str | Path | None) -> RunnerState:
        """Return a new RunnerState with recorded checkpoint path."""
        p_str = str(path) if path is not None else None
        return replace(
            self,
            last_checkpoint=p_str,
            last_updated=_now_iso(),
        )
