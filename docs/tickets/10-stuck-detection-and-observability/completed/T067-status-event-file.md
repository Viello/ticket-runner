# T067 — Durable status event file
Status: completed
Completed: 2026-09-21T05:33:00Z
Spec: docs/specs/10-stuck-detection-and-observability.md
Blocked by: T063
Reasoning: low

### Requirements
- Define a `StatusPublisher` port (interface / abstract base class) with a single method `publish(event: StatusEvent) → None`.
- Define a `StatusEvent` value object with fields: `ticket_id`, `run_state` (enum: `running`, `verifying`, `escalating`, `idle`, `done`), `attempt`, `max_attempts`, `token_count`, `token_budget`, `last_step_summary`, `last_step_at` (ISO timestamp string), `last_event` (str label).
- Implement `JsonFileStatusPublisher` adapter that writes `.agent/status.json` atomically using the existing `atomic_write_text` helper. The file must always contain valid JSON even if a previous write was interrupted.
- Wire `JsonFileStatusPublisher` into `build_container()` as the default `StatusPublisher`. The path `.agent/status.json` must be derived from `RuntimePaths` (consistent with other `.agent/` paths).
- Call `publish(ATTEMPT_STARTED)` when `VerificationLoop` begins an attempt.
- Call `publish(ATTEMPT_ENDED)` when an attempt completes (pass or fail).
- Call `publish(ESCALATION_EMITTED)` when T066's escalation fires.
- Call `publish(CIRCUIT_BREAKER_TRIPPED)` when the circuit breaker trips.
- The `StatusPublisher` port is injectable via `build_container` overrides so tests can use an in-memory stub.

Jump-start:
- Port interface: `runner/ports/status_publisher.py` (follow the existing port pattern — look at `InterventionGateway`, `SignalStore`, or `GotchasStore` for the pattern).
- Adapter: `runner/adapters/json_status_publisher.py`.
- `RuntimePaths`: `runner/domain/runtime_paths.py` — add `status_file: Path` property pointing to `.agent/status.json`.
- `atomic_write_text`: `runner/adapters/markdown/atomic_write.py` — already used by signal and gotchas adapters.
- Container: `runner/container.py` — register `JsonFileStatusPublisher` and inject it where needed.
- Tests: `tests/unit/adapters/test_json_status_publisher.py` — write a `STEP_FINISHED` event and assert JSON shape; assert atomic write leaves no `.tmp` file on failure.
- Verify with: `python -m pytest tests/unit/adapters/test_json_status_publisher.py -x`

### Acceptance Criteria
- Publishing a `STEP_FINISHED` event writes `.agent/status.json` with the correct JSON fields and values.
- Publishing overwrites the previous status file atomically (no partial JSON visible to a concurrent reader).
- A simulated mid-write failure leaves no `.tmp` sidecar file.
- `build_container()` wires `JsonFileStatusPublisher` as the default; tests that pass an in-memory stub receive it.
- All existing container and integration tests still pass.
- `python -m pytest tests/unit/adapters/test_json_status_publisher.py -x` exits 0.

### Smoke Scenarios
All scenarios are covered by automated tests. No manual steps required.

### Gotchas
- `.agent/status.json` lives under `.agent/` which is git-ignored runtime state — confirm `.gitignore` already covers `*.json` under `.agent/`, or add `status.json` explicitly.
- The `RuntimePaths` value object must not create the `.agent/` directory eagerly (see gotchas: "Pure Path Object Instantiation Without Disk Side-Effects"); keep `status_file` as a pure `Path` property and let `JsonFileStatusPublisher` call `ensure_parent_dir()` on first write.
- `last_step_summary` may be None if no step has completed yet; serialize as `null` in JSON, not as an absent key, so consumers can rely on a stable schema.
