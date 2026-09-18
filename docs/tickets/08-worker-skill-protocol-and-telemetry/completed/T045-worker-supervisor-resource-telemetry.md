# T045 — Worker supervisor resource telemetry
Status: completed
Completed: 2026-09-18T03:00:00Z
Spec: docs/specs/08-worker-skill-protocol-and-telemetry.md
Blocked by: T044

### Requirements
- Update `runner/application/worker_supervisor.py` to track all project skills and `AGENTS.md` resources accessed during a Session Run.
- As event stream lines are read, evaluate `extract_resource_access` on each event and raw line; when a recognized resource is detected, accumulate it into the active session's resource set and log an info line:
  `logger.info(f"[{ticket_id}] Worker accessed resource: {resource_name}")`.
- Expose `resources_accessed: frozenset[str]` on `SessionRunResult`, allowing downstream orchestrators and processors to inspect resource compliance.
- Jump-start:
  - Files to touch: `runner/application/worker_supervisor.py`, `tests/unit/application/test_worker_supervisor.py`.
  - Seams: `WorkerSupervisor.run_session()`, `SessionRunResult`.
  - Anchor patterns: Token budget observation loop in `worker_supervisor.py`.
  - Verification: `python -m pytest tests/unit/application/test_worker_supervisor.py`.

### Acceptance Criteria
- `SessionRunResult` includes `resources_accessed: frozenset[str]`.
- Streaming `tool_use` events for skills (`"implement"`, `"code-review"`, `"security-review"`, etc.) and `"AGENTS.md"` correctly populate `resources_accessed`.
- Multiple accesses to the same resource are deduplicated cleanly in `frozenset`.
- Telemetry accumulation runs reliably without adding observable latency to the streaming loop.
- Full `test_worker_supervisor.py` suite passes.

### Gotchas
- An exception in resource extraction must never abort the Session Run; catch and log extraction anomalies defensively so the Worker process supervision remains uninterrupted.
