# T053 — RunnerState domain model, state transitions, and StateCoordinator
Status: completed
Completed: 2026-09-19T08:03:00Z
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: None
Reasoning: medium

### Requirements
- Define the `RunnerState` domain entity and `StateStatus` enum in `runner/domain/state.py` conforming to the 13-field schema in Spec 06:
  - `active_ticket_id`: string or null
  - `status`: `"IDLE"`, `"WORKING"`, `"GATEKEEPER"`, `"WAITING_FOR_USER"`, `"PAUSE_REQUESTED"`, `"CIRCUIT_BREAKER_TRIPPED"`
  - `opencode_session_id`: string or null
  - `selected_model`: string or null (retained from Spec 07 model selection)
  - `presence_mode`: `"nearby"` | `"away"`
  - `verification_attempts`: integer (>= 0)
  - `tokens`: object with `current` (integer >= 0) and `warning_sent` (boolean)
  - `branch`: string
  - `started_at`: ISO-8601 UTC timestamp string
  - `last_checkpoint`: path string or null
  - `tui_open`: boolean (default `false`)
  - `tui_session_id`: string or null (default `null`)
  - `last_updated`: ISO-8601 UTC timestamp string
- Provide immutable transition helper methods on `RunnerState` (`to_working`, `to_gatekeeper`, `to_idle`, `to_pause_requested`, `to_circuit_breaker_tripped`, `record_tokens`, `set_presence_mode`, `set_tui_open`, `clear_tui`) validating invariant boundaries and updating `last_updated`.
- Implement `StateCoordinator` application service in `runner/application/state_coordinator.py` backed by the `StateStore` port protocol:
  - `load_state() -> RunnerState | None`: reads and parses state document, returning `None` if file absent.
  - `save_state(state: RunnerState) -> None`: merges with existing persisted document (preserving unmanaged keys) and writes atomically.
  - Helper transition dispatchers to ensure atomic disk persistence on each state change.
- Wire `StateCoordinator` into `QueueOrchestrator` and `WorkerSupervisor` (and container composition root) to persist state transitions at ticket pickup, worker run, gatekeeper verification, pause, and completion.
- Jump-start:
  - Files to touch: `runner/domain/state.py`, `runner/domain/__init__.py`, `runner/application/state_coordinator.py`, `runner/application/__init__.py`, `runner/application/queue_orchestrator.py`, `runner/container.py`, `tests/unit/domain/test_state.py`, `tests/unit/application/test_state_coordinator.py`.
  - Seams: `runner/ports/state_store.py`, `runner/adapters/filesystem/json_state_store.py`.
  - Anchor patterns: compare with `runner/domain/signal.py` and `runner/adapters/filesystem/json_state_store.py`.
  - Verification: `python -m pytest tests/unit/domain/test_state.py tests/unit/application/test_state_coordinator.py tests/unit/application/test_queue_orchestrator.py`.

### Acceptance Criteria
- `RunnerState.from_dict` parses the full 13-field state schema and raises `StateFormatError` on missing required fields, invalid status strings, negative token counts, or invalid timestamps.
- Transition methods return updated `RunnerState` instances with fresh `last_updated` UTC ISO-8601 timestamps without mutating the original instance.
- `StateCoordinator.save_state` preserves external/unmanaged keys (such as `selected_model` written by startup model selection) when writing to disk.
- `QueueOrchestrator` updates `.agent/state.json` with `status: "WORKING"` when beginning a ticket, `status: "GATEKEEPER"` during verification, and `status: "IDLE"` when the queue is drained.
- Unit and integration tests verify complete round-trip serialization, invariant checks, and atomic filesystem persistence.
- Full suite green: `python -m pytest`.

### Gotchas
- Do not clobber `selected_model`: `ModelSelectionInteractor` in Spec 07 writes `selected_model` directly to `state.json` before `QueueOrchestrator` starts; `StateCoordinator` must read-merge-write.
- `tokens` is a nested object (`{"current": 0, "warning_sent": False}`), not a flat integer.
- Timestamps must always use `datetime.now(timezone.utc).isoformat()` for consistent cross-platform parsing.
