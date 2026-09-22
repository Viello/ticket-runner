"""StatusEvent value object and RunState enum for orchestrator status reporting (T067)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RunState(str, Enum):
    """Execution state of the runner for status reporting."""

    RUNNING = "running"
    VERIFYING = "verifying"
    ESCALATING = "escalating"
    IDLE = "idle"
    DONE = "done"


@dataclass(frozen=True)
class StatusEvent:
    """Value object representing an orchestrator status event.

    Fields:
        ticket_id: Identifier of the ticket currently being processed.
        run_state: High-level runner state (running, verifying, escalating, idle, done).
        attempt: Current verification attempt number (1-based, or 0 if not yet started).
        max_attempts: Maximum allowed verification attempts before circuit breaker.
        token_count: Current token usage / occupancy count.
        token_budget: Maximum token budget ceiling.
        last_step_summary: Narration text of the last completed step, or None.
        last_step_at: ISO-8601 timestamp string of the last step or event.
        last_event: String label identifying the event (e.g. STEP_FINISHED, ATTEMPT_STARTED).
    """

    ticket_id: str
    run_state: RunState
    attempt: int
    max_attempts: int
    token_count: int
    token_budget: int
    last_step_summary: str | None
    last_step_at: str
    last_event: str

    def __post_init__(self) -> None:
        if not isinstance(self.run_state, RunState):
            object.__setattr__(self, "run_state", RunState(self.run_state))

    def to_dict(self) -> dict[str, Any]:
        """Serialize status event to a dictionary matching .agent/status.json schema."""
        data = asdict(self)
        data["run_state"] = self.run_state.value
        return data
