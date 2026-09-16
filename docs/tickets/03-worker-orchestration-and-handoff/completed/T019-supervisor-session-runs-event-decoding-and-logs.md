# T019 — Worker supervisor A: session runs, event decoding, and session logs
Status: completed
Completed: 2026-09-16T13:16:00Z
Security: required
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add `runner/application/worker_supervisor.py` (supervision mechanics) and `runner/adapters/opencode/opencode_worker.py` (raw JSON line → domain event, tolerant of unknown types and unparseable lines).
- Execute one Session Run: spawn `opencode run --format json --auto "<prompt>"` through the T016 spawn handle, adding `--session <id>` only when resuming an existing Worker Session; learn the session id from the first event's top-level `sessionID`; decode events live; feed `TokenUsage` from every `step_finish` part into the T018 `BudgetMonitor`; surface the WARN action through an injectable `notify(notice)` callable (default: plain stderr line with ticket context). No handoff/ceiling kills here — T020 adds termination reasons.
- Session logging: append the raw stdout lines to `.agent/logs/{ticket_id}_session_{session_id}.jsonl` (one file per Worker Session, appended across resumed runs) and stderr to the sibling sidecar from T015. Sanitize the stream-provided `session_id` against `^ses_[A-Za-z0-9]+$` before it ever touches a filename; on a bad id, skip log-file creation and surface a diagnostic instead of writing at a caller-influenced path.
- Check ready-signal presence after exit via the T015 runtime paths — file existence only; do not parse or watch it (Spec 04 owns schema and watching).
- Return the initial run result: session id, exit code, latest occupancy, ready-signal presence, trimmed stderr tail, and log paths. T020 finalizes reasons and watchdog fields.
- Security: required — subprocess invocation, untrusted stream parsing, and filename construction from stream data. Explicitly verify: no shell interpolation in argv; malformed/oversized JSON lines cannot crash the supervisor or execute anything; log paths cannot escape `.agent/logs/`; unknown event types are skipped rather than trusted.
- Jump-start:
  - Files to touch: `runner/application/worker_supervisor.py`, `runner/adapters/opencode/` (new package `__init__.py` + `opencode_worker.py`), `runner/domain/runtime_paths.py`, `tests/unit/application/test_worker_supervisor.py`.
  - Seams: T016 `CommandRunner.spawn`, T018 `BudgetMonitor`/`TokenUsage`, T015 `RuntimePaths`.
  - Anchor patterns: `QueueOrchestrator` injection style for collaborators; `tests/fakes/fake_command_runner.py` scripted streams from T016; existing `asyncio.run` test convention.
  - Verification: `pytest tests/unit/application/test_worker_supervisor.py`.

### Acceptance Criteria
- A scripted stream (`step_start` → `text` → `step_finish` at 120k) yields exactly one WARN notice through the injected recorder and leaves occupancy equal to the last `step_finish` value.
- The JSONL file's content matches the scripted stdout lines (line endings tolerated); a second run on the same session appends rather than truncating; the stderr sidecar captures stderr.
- Unknown event types and an unparseable line are recorded and skipped; the run completes and returns the correct exit code.
- Ready-signal presence flips based on a real file created in a temp `.agent/signals/` tree; a session id failing the allowlist produces no log file and a diagnostic.

### Gotchas
- JSONL lines arrive with `\r\n` on Windows; compare with `newline=""` semantics per gotchas.md.
- OpenCode blocks at startup if stdin is a pipe — T016's handle must pass `DEVNULL`; if the supervisor spawns through any other path, keep that invariant.
- `text` parts for reasoning only appear with `--thinking`; do not depend on them, and do not depend on `message.updated`-style events — the CLI emits exactly six event types (verified against v1.18.x source).
- Runner must never parse stdout for state transitions beyond telemetry (ADR 0004).
