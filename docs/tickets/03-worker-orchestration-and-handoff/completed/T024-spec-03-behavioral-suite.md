# T024 — Spec 03 behavioral suite and placeholder refresh
Status: completed
Completed: 2026-09-16T14:18:48Z
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add `tests/specs/test_spec_03_worker.py` exercising Spec 03's user stories end-to-end over scripted `FakeCommandRunner` streams and real temporary filesystems: prompt contract (execution skill pointer, Spec Excerpt, global gotchas, ready-signal instruction, commit prohibition, conditional `/security-review`), telemetry and WARN-once, 135k handoff with freshness + fresh session, 150k ceiling kill, nudge and crash-retry, escalation confirm/decline, emergency synthesis, chain cap, session log artifacts, and session-id sanitization.
- Refresh the now-stale placeholder in `runner/application/queue_orchestrator.py` ("Worker execution will arrive in Spec 03.") to point at Spec 04, updating `tests/unit/test_cli.py` assertions if they reference the message.
- Jump-start:
  - Files to touch: `tests/specs/test_spec_03_worker.py`, `runner/application/queue_orchestrator.py` (placeholder strings around lines 266 and 464), `tests/unit/test_cli.py`.
  - Seams: public surfaces of `WorkerSupervisor`, `HandoffCoordinator`, `PromptBuilder`, `BudgetMonitor`, `RuntimePaths` — no private internals.
  - Anchor patterns: `tests/specs/test_spec_02_queue.py` structure (real temp trees, `asyncio.run`, header docstring listing covered user stories).
  - Verification: `pytest tests/specs/test_spec_03_worker.py tests/unit/test_cli.py`.

### Acceptance Criteria
- Every Spec 03 user story (US1–15) has at least one behavioral assertion in the suite; no test spawns a live OpenCode binary or sleeps on real 900s/300s timeouts (inject clocks and thresholds).
- The suite drives at least one full A→handoff→B→READY chain and one escalation with synthesis through real files on disk, asserting the `.agent/` artifacts byte-for-byte where practical.
- The CLI placeholder message no longer promises Spec 03 work and the CLI tests are green.

### Gotchas
- Behavioral tests hit disk (repo convention): build `.agent/` trees under `tmp_dir`, mind CRLF when asserting raw log bytes.
- Keep the suite runtime bounded — a full scripted chain must finish in seconds.
- Do not test queue commits here: Spec 04's adapter wires the supervisor to the Gatekeeper and commit path; this suite stops at `WorkerRunResult`.
