# T068 — Step-summary observability
Status: pending
Spec: docs/specs/10-stuck-detection-and-observability.md
Blocked by: T067
Reasoning: low

### Requirements
- Hook into `WorkerSupervisor`'s `step_finish` event processing to extract the assistant message text (the model's narration of what it just did) and publish it as a `STEP_FINISHED` `StatusEvent` via `StatusPublisher` (T067).
- In **nearby mode**, print each step summary to the terminal as a single truncated line (≤ 120 chars):
  ```
  [T063 | step 7 | 42k tokens] Edited runner/verification.py — added silence window loop
  ```
- In **away mode**, do not print to terminal; the `StatusPublisher` write is still performed (Discord adapter or future TUI polls `status.json`).
- **Heartbeat**: if 30 seconds elapse without a `step_finish` event (the Worker is still running but hasn't narrated a step), print a heartbeat line in nearby mode:
  ```
  [T063 | attempt 2/3 | 42k tokens | idle…]
  ```
  The heartbeat timer resets on each received step event. It must not fire when the Worker has already exited.
- The step-summary hook and heartbeat must not interfere with the existing token budget monitoring or stall detection in `WorkerSupervisor`.

Jump-start:
- `WorkerSupervisor` (or equivalent in `runner/application/`): find where `step_finish` events are already processed (token telemetry, handoff threshold checks). Add the summary extraction callback in the same location — same pattern, a new concern added to an existing hook point.
- Assistant message text: inspect the `step_finish` event structure (a `part` dict with type and text fields); extract the `text` field from the assistant part if present, truncate to 120 chars.
- Presence mode: `config.presence.default_mode` — check for `"nearby"` to gate terminal output.
- Heartbeat: use `asyncio.create_task` with a periodic sleep loop; cancel the task on Worker exit. See existing periodic tasks in the supervisor for the pattern.
- `StatusPublisher`: inject via `WorkerSupervisor.__init__` alongside other injectable collaborators.
- Tests: `tests/unit/application/test_worker_supervisor.py` — add scenarios using `FakeProcessHandle` that yields step events; assert step summary printed in nearby mode and absent in away mode; assert heartbeat fires after 30 s of silence (use injected clock).
- Verify with: `python -m pytest tests/unit/application/test_worker_supervisor.py -x`

### Acceptance Criteria
- A `step_finish` event with assistant text updates `status.json` via `StatusPublisher` with `last_step_summary` and `last_step_at`.
- In nearby mode, the step summary is printed to terminal (≤ 120 chars).
- In away mode, nothing is printed but `status.json` is still updated.
- The heartbeat line is printed after 30 s of silence in nearby mode.
- The heartbeat does not fire after the Worker exits.
- Existing token budget and stall detection behaviour is unchanged.
- `python -m pytest tests/unit/application/test_worker_supervisor.py -x` exits 0.

### Smoke Scenarios
**Scenario: step summary lines appear in nearby mode**
- Setup: Set `presence.default_mode: nearby` in `config.yaml`. Run the Runner against a ticket that takes several Worker steps to complete (any real in-progress ticket).
- Steps:
  1. Watch the terminal during Worker execution.
- Expected: After each model step, a summary line appears truncated to ≤ 120 characters in the format `[<ticket_id> | step N | Xk tokens] <narration>`. No line exceeds 120 characters. Step count increments monotonically.

**Scenario: heartbeat fires after 30 seconds of Worker silence**
- Setup: Set `presence.default_mode: nearby`. Use a ticket whose test suite takes longer than 30 seconds to run (a slow integration suite, or temporarily lower the heartbeat threshold in config if one exists).
- Steps:
  1. Observe the terminal when no step event arrives within 30 seconds.
- Expected: A heartbeat line appears in the format `[<ticket_id> | attempt N/M | Xk tokens | idle…]`. It does not appear after the Worker has exited.

**Scenario: no terminal output in away mode**
- Setup: Set `presence.default_mode: away` in `config.yaml`. Run the Runner through a full ticket execution.
- Steps:
  1. Watch the terminal for step summary or heartbeat lines during execution.
  2. After the ticket completes, inspect `.agent/status.json`.
- Expected: No step summary or heartbeat lines appear on the terminal. `.agent/status.json` contains `last_step_summary` and `last_step_at` fields updated after each step.

### Gotchas
- `step_finish` assistant text may be absent (tool-use steps, or providers that omit narration). Guard with `part.get("text") or ""` before truncating — never raise on a missing key.
- The heartbeat `asyncio.Task` must be cancelled in a `finally` block on Worker exit; an unfinished background task will keep the event loop alive and block graceful shutdown.
- Truncation to 120 chars must happen before printing *and* before writing to `status.json` — a 10,000-character narration in the status file would make Discord message formatting unwieldy when the Discord adapter is later wired.
