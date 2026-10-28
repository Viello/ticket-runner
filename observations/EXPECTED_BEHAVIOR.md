# Ground-Truth Behavioral Oracle: `ticket-runner` Live HITL Run (`T101` → `T102`)

- **Artifact Path**: `D:\Repos\agent-skills\observations\EXPECTED_BEHAVIOR.md`
- **Orchestrator Repository (`Runner`)**: `D:\Projects` (HEAD `480da04` on branch `agent/ticket-runner`)
- **Target Project Repository**: `D:\Repos\agent-skills` (baseline HEAD `6912328` on branch `agent/ticket-runner`)
- **Execution Command**:
  ```powershell
  Set-Location D:\Repos\agent-skills
  python D:\Projects\ticket_runner.py start --local-only
  ```
- **Active Configuration (`D:\Repos\agent-skills\ticket-runner.yaml`)**:
  - `worker.provider`: `"antigravity"`
  - `worker.execution_skill`: `".agents/skills/implement/SKILL.md"`
  - `model.default`: `"gemini-3.8-flash-high"`
  - `queue.tickets_dir`: `"docs/tickets"`
  - `verification.approval_mode`: `"human"` (Human-in-the-Loop / HITL)
  - `verification.max_attempts`: `3` (`bug_escalation_at`: `1` default)
  - `verification.timeout_seconds`: `300`, `silence_window_seconds`: `60`
  - `token_budget`: `warn: 120000`, `handoff: 135000`, `ceiling: 150000`

This document is the **machine-verifiable ground-truth specification** for an overseeing or debugging agent monitoring the live Human-in-the-Loop (`--local-only`) run of `T101` → `T102`. Any deviation from the invariants, schemas, CLI flags, state transitions, or post-commit git trees specified below constitutes an anomaly requiring immediate triage against Section 4.

---

## 1. Environment & Pre-Flight (`Doctor`) Invariants

### 1.1 Repository & Branch Invariants
1. **Target Project (`D:\Repos\agent-skills`)**:
   - Current working directory (`CWD`) for `ticket_runner.py` MUST be `D:\Repos\agent-skills`. All runtime paths (`.agent/`, `docs/tickets/`, `.agents/skills/`) resolve relative to `D:\Repos\agent-skills` via `RuntimePaths.from_root(project_root)` (`D:\Projects\runner\domain\runtime_paths.py:42-93`).
   - Git branch MUST be `agent/ticket-runner` (`git rev-parse --abbrev-ref HEAD` == `"agent/ticket-runner"`).
   - Baseline commit before `T101` MUST be `6912328` (`git rev-parse --short HEAD` == `"6912328"`, `"Merge branch 'main' into agent/ticket-runner"`).
   - Working tree MUST be clean prior to `ticket_runner.py doctor --local-only` (`git status --porcelain` returns empty output `""`).
2. **Orchestrator Repository (`D:\Projects`)**:
   - Git branch MUST be `agent/ticket-runner` (HEAD `480da04` or newer).
   - Never invoke `ticket_runner.py` with `D:\Projects` as `CWD` when running the `agent-skills` queue.

> [!WARNING]
> **Pre-Run Dirty-State & Zombie Lock Sanitization Check**:
> If a prior aborted `T101` run left paused `python` (`ticket_runner.py`) or `agy` processes running, `docs/tickets/.queue.lock` will be byte-locked (`msvcrt.LK_NBLCK`) and the working tree will be dirty (e.g., `T101` prematurely moved to `completed/`, `docs/tickets/gotchas.md` modified, or untracked `*/agents/openai.yaml` files present). Before starting a clean run, verify and sanitize:
> 1. Ensure no orphan `ticket_runner.py` or `agy` processes targeting `D:\Repos\agent-skills` are alive (`Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'ticket_runner|agy' }`).
> 2. Reset tracked files (`git checkout -- .`), remove untracked `*/agents/` and `docs/tickets/01-runner-live-test-bootstrap/completed/` artifacts (`git clean -fd docs/tickets */agents`), and remove stale `.agent/state.json`, `.agent/status.json`, `.agent/signals/*`, `.agent/questions/*`, and `docs/tickets/.queue.lock`.

### 1.2 Pre-Push Hook Guardrail (`D:\Repos\agent-skills\.git\hooks\pre-push`)
- Managed by `PrePushHookInstaller` (`D:\Projects\runner\adapters\git\pre_push_hook.py`) reading `D:\Projects\scripts\pre-push.sh`.
- `D:\Repos\agent-skills\.git\hooks\pre-push` MUST exist and contain the exact block markers `# BEGIN TICKET RUNNER GUARDRAIL` and `# END TICKET RUNNER GUARDRAIL`:
  ```sh
  # BEGIN TICKET RUNNER GUARDRAIL
  current_branch=$(git symbolic-ref --short HEAD 2>/dev/null)
  if [ "$current_branch" = "agent/ticket-runner" ]; then
      echo "ERROR: Direct git push is blocked on agent/ticket-runner branch." >&2
      exit 1
  fi
  # END TICKET RUNNER GUARDRAIL
  ```
- Any `git push` executed while on `agent/ticket-runner` MUST fail immediately with exit code `1` and stderr `"ERROR: Direct git push is blocked on agent/ticket-runner branch."`.

### 1.3 All 11 `doctor --local-only` Checks (`D:\Projects\runner\application\doctor.py:1088-1100`)
Running `python D:\Projects\ticket_runner.py doctor --local-only` inside `D:\Repos\agent-skills` MUST exit with code `0` (`report.passed == True`) and pass all 11 checks in exact sequence:

| # | Check Name | Expected Status | Exact Verification Oracle (`runner/application/doctor.py`) |
|---|---|---|---|
| 1 | `worker_binary` | `PASS` | `Antigravity CLI binary 'agy' verified on PATH.` (or via `AGENT_ANTIGRAVITY_BIN` env override; `doctor.py:667-703`). |
| 2 | `git` | `PASS` | `Working tree clean on branch 'agent/ticket-runner'.` (`git rev-parse --abbrev-ref HEAD` == `"agent/ticket-runner"` and `git status --porcelain` is empty; `doctor.py:725-777`). |
| 3 | `queue` | `PASS` | `Found 2 pending ticket(s) in queue.` (`T101` and `T102` under `docs/tickets/01-runner-live-test-bootstrap/`; `doctor.py:779-825`). |
| 4 | `config` | `PASS` | `Configuration valid: loaded via two-tier resolution for 'D:\Repos\agent-skills'.` (`ticket-runner.yaml` parses cleanly via `Config.load`; `doctor.py:827-863`). |
| 5 | `model` | `PASS` | `Model configuration verified with 1 model(s) available.` (`model.default: "gemini-3.8-flash-high"`; skips `opencode models` probing because `worker.provider == "antigravity"`; `doctor.py:865-916`). |
| 6 | `session_terminal` | `PASS` | `Session terminal host 'wt.exe' verified on PATH.` (`session_terminal.host: "wt"`; `doctor.py:918-958`). |
| 7 | `verification_commands` | `PASS` | `Verification commands resolve to executables on PATH.` (`verification.test_cmd` leading executable `python` resolves on `PATH`; `doctor.py:960-1002`). |
| 8 | `pre_push_hook` | `PASS` | `Pre-push hook guardrail is active and verified.` (`.git/hooks/pre-push` contains guardrail block; `doctor.py:1004-1019`). |
| 9 | `agents_md` | `PASS` | `Operating rules file verified at 'AGENTS.md'.` (`D:\Repos\agent-skills\AGENTS.md` exists and is non-empty; `doctor.py:1021-1037`). |
| 10 | `skills` | `PASS` | `All 3 required skill files verified on disk.` (`.agents/skills/implement/SKILL.md`, `.agents/skills/code-review/SKILL.md`, `.agents/skills/diagnosing-bugs/SKILL.md` exist and are non-empty; `doctor.py:1039-1064`). |
| 11 | `discord` | `PASS` | `Discord verification bypassed (--local-only mode).` (`local_only=True` bypasses `DISCORD_BOT_TOKEN` check; `doctor.py:1066-1086`). |

### 1.4 Pre-`T101` Target Repository Baseline (`D:\Repos\agent-skills`)
1. **Top-Level Skill Directories (`*/SKILL.md`)**: `45` canonical skill directories at repository root.
2. **Recursive `openai.yaml` Count**: **Exactly `37`** prior to `T101`:
   - PowerShell check: `(Get-ChildItem -Path D:\Repos\agent-skills -Recurse -Filter openai.yaml).Count` MUST equal `37`.
   - Python glob check (`verification.test_cmd`): `glob.glob('*/agents/openai.yaml')` MUST match `37` files and output `validated 37 openai.yaml files`.
   - Why recursive count == top-level count (`37`): `.agents/skills/` contains 5 provisioned skills (`implement`, `code-review`, `diagnosing-bugs`, `handoff`, `security-review`), and **none** of those 5 directories contain an `agents/openai.yaml` file (`(Get-ChildItem -Path D:\Repos\agent-skills\.agents -Recurse -Filter openai.yaml).Count == 0`).
3. **8 Top-Level Skills Lacking `agents/openai.yaml` Pre-`T101`**:
   - Without `disable-model-invocation: true` in `SKILL.md` (4 skills): `clean-architecture`, `security-review`, `software-architecture`, `status`.
   - With `disable-model-invocation: true` in `SKILL.md` (4 skills): `create-verification-skill`, `live-qa`, `maintain-verification-skill`, `smoke-fail`.
4. **Gitignore Invariants (`D:\Repos\agent-skills\.gitignore`)**:
   - `.gitignore` MUST contain the following entries so runtime telemetry, provisioned skills, and observation logs never pollute `git status --porcelain` or `git add .`:
     ```gitignore
     .agent/
     docs/tickets/.queue.lock
     .agents/
     observations/
     ```

---

## 2. Stage-by-Stage State Machine & Filesystem Telemetry Contract

### 2.1 Stage Lifecycle Overview

```mermaid
flowchart LR
    DOC["1. DOCTOR"] --> PEND["2. PENDING (Select & Lock)"]
    PEND --> WORK["3. WORKING (AntigravityWorker)"]
    WORK --> SIG["4. READY SIGNAL (.agent/signals/)"]
    SIG --> GK["5. GATEKEEPER (Verify & Triage)"]
    GK -->|Pass| HITL["6. HUMAN GATE (Evidence Card)"]
    GK -->|Fail < 3| WORK
    GK -->|Fail == 3| CB["CIRCUIT BREAKER (Exit 2)"]
    HITL -->|Approve [y]| COM["7. COMMIT & ARCHIVE"]
    HITL -->|Reject [n]| WORK
```

| Stage | `.agent/state.json` `status` | `.agent/status.json` `run_state` | `.agent/status.json` `last_event` | `docs/tickets/.queue.lock` |
|---|---|---|---|---|
| **1. `DOCTOR`** | Unchanged / Not yet initialized (`IDLE`) | Unchanged / Not yet initialized | N/A | Unlocked |
| **2. `PENDING`** | `IDLE` → `WORKING` | `running` | `ATTEMPT_STARTED` | **Acquired** (`msvcrt.LK_NBLCK`) |
| **3. `WORKING`** | `WORKING` | `running` | `ATTEMPT_STARTED` / `STEP_FINISHED`* | Held |
| **4. `READY SIGNAL`** | `WORKING` (process exits / `KILLED_SIGNAL`) | `running` | `ATTEMPT_STARTED` / `STEP_FINISHED`* | Held |
| **5. `GATEKEEPER`** | `GATEKEEPER` | `verifying` → `running` (or `escalating` / `idle`) | `ATTEMPT_ENDED` / `ESCALATION_EMITTED` / `CIRCUIT_BREAKER_TRIPPED` | Held |
| **6. `HUMAN GATE`** | `GATEKEEPER` (blocked in `request_approval`) | `running` (after green `ATTEMPT_ENDED`) | `ATTEMPT_ENDED` | Held |
| **7. `COMMIT & ARCHIVE`** | `IDLE` (`active_ticket_id: null`) | `done` (when queue empty) | `ATTEMPT_ENDED` | **Released** on `run_next()` exit |

*\*See Anomaly #8 in Section 4 regarding `STEP_FINISHED` and `tokens.current` under `AntigravityWorker`.*

---

### 2.2 Locking Contract (`docs/tickets/.queue.lock`)
- **Implementation**: `QueueFileLock` (`D:\Projects\runner\adapters\markdown\file_lock.py:16-59`), invoked via `with self._queue_lock:` inside `QueueOrchestrator.run_next()` (`D:\Projects\runner\application\queue_orchestrator.py:554`).
- **Mechanism**: Opens `D:\Repos\agent-skills\docs\tickets\.queue.lock` in `"a+b"` mode, writes `b" "` if file size is `0`, seeks to byte `0`, and acquires an exclusive non-blocking OS byte lock via `msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)`.
- **Contention Behavior**: If another process holds the byte lock on `docs/tickets/.queue.lock`, `acquire()` raises `QueueLockError("Queue lock is already held: ...")` and `ticket_runner.py` aborts immediately without mutating queue state.
- **Release**: `msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)` + `file_obj.close()` executes in `__exit__` at the end of each `run_next()` ticket cycle (including on pause, user abort, or unhandled exception). Note that `docs/tickets/.queue.lock` remains on disk as a 1-byte gitignored file after unlock; lock state is determined by OS file-descriptor byte locking, not file existence.

---

### 2.3 Runtime State & Status Telemetry Schemas

#### A. `.agent/state.json` (`RunnerState` — `D:\Projects\runner\domain\state.py:54-169`)
Persisted atomically via temp-file replace by `JsonStateStore` (`D:\Projects\runner\adapters\json\state_store.py`) and coordinated by `StateCoordinator` (`D:\Projects\runner\application\state_coordinator.py`). Must contain all **13 top-level keys**:
```json
{
  "active_ticket_id": "T101",
  "status": "WORKING",
  "opencode_session_id": "50fec97e-d48a-42ab-a0cf-d0511557534f",
  "selected_model": "gemini-3.8-flash-high",
  "presence_mode": "nearby",
  "verification_attempts": 0,
  "tokens": {
    "current": 0,
    "warning_sent": false
  },
  "branch": "agent/ticket-runner",
  "started_at": "2026-10-25T12:12:41.000000+00:00",
  "last_checkpoint": null,
  "tui_open": false,
  "tui_session_id": null,
  "last_updated": "2026-10-25T12:12:44.000000+00:00"
}
```
- **Allowed `status` values** (`StateStatus` enum in `runner/domain/state.py:21-28`):
  - `"IDLE"`, `"WORKING"`, `"GATEKEEPER"`, `"WAITING_FOR_USER"`, `"PAUSE_REQUESTED"`, `"CIRCUIT_BREAKER_TRIPPED"`.
- **Session ID (`opencode_session_id`)**: Despite the historical field name, when `worker.provider == "antigravity"`, this field stores the **UUID v4 `conversation_id`** emitted by `agy`'s `init` event (e.g. `"50fec97e-d48a-42ab-a0cf-d0511557534f"`), recorded via `WorkerSupervisor` (`runner/application/worker_supervisor.py:689-692`).
- **Token Occupancy (`tokens.current`)**:
  - **Specification Requirement**: Must reflect `total_tokens` (> `0`) after worker turns once `BudgetMonitor.observe()` records `TokenUsage`.
  - **Known Code Discrepancy (Watchlist Item #8)**: In `D:\Projects\runner\application\worker_supervisor.py:715`, `self._budget_monitor.observe(event.token_usage)` and `self._state_coordinator.record_tokens(...)` are gated behind `if event.type == "step_finish":` (the OpenCode event name), whereas `AntigravityWorker.decode_event` (`runner/adapters/antigravity/antigravity_worker.py:273-324`) emits `event.type` in `{"init", "step_update", "result"}`. Unless `worker_supervisor.py:715` is patched to include `"step_update"` / `"result"`, `tokens.current` in `.agent/state.json` and `token_count` in `.agent/status.json` remain `0` even when `.agent/logs/<ticket_id>_session_<uuid>.jsonl` reports non-zero `usage.total_tokens`. The overseeing agent MUST verify non-zero token usage directly inside `.agent/logs/<ticket_id>_session_<uuid>.jsonl` and flag `tokens.current == 0` in `.agent/state.json` against Watchlist Item #8.

#### B. `.agent/status.json` (`StatusEvent` — `D:\Projects\runner\domain\status_event.py:13-85`)
Published by `StatusPublisher` (`D:\Projects\runner\adapters\json\status_publisher.py`). Must contain all **9 top-level keys**:
```json
{
  "ticket_id": "T101",
  "run_state": "running",
  "attempt": 1,
  "max_attempts": 3,
  "token_count": 0,
  "token_budget": 150000,
  "last_step_summary": "Attempt 1 started",
  "last_step_at": "2026-10-25T12:12:41.000000+00:00",
  "last_event": "ATTEMPT_STARTED"
}
```
- **Allowed `run_state` values** (`VALID_RUN_STATES`): `"running"`, `"verifying"`, `"escalating"`, `"idle"`, `"done"`.
- **Allowed `last_event` values** (`VALID_LAST_EVENTS`): `"STEP_FINISHED"`, `"ATTEMPT_STARTED"`, `"ATTEMPT_ENDED"`, `"ESCALATION_EMITTED"`, `"CIRCUIT_BREAKER_TRIPPED"`.

---

### 2.4 Worker Invocation Contract (`AntigravityWorker`)
Implemented in `D:\Projects\runner\adapters\antigravity\antigravity_worker.py`.

1. **Exact CLI Command Vector (`build_antigravity_run_command`, lines `99-156`)**:
   - **Fresh Session (`session_id=None`)**:
     ```text
     agy -p "<prompt>" --output-format stream-json --model gemini-3.8-flash --effort medium --print-timeout 0
     ```
   - **Resumed Session (`session_id="<conversation_uuid>"`)**:
     ```text
     agy -p "<prompt>" --output-format stream-json --conversation <conversation_uuid> --model gemini-3.8-flash --effort medium --print-timeout 0
     ```
2. **Mandatory Flags**:
   - `-p "<prompt>"`: Non-interactive headless prompt execution.
   - `--output-format stream-json`: Emits NDJSON envelopes (`init`, `step_update`, `result`) on stdout.
   - `--print-timeout 0` (`DEFAULT_PRINT_TIMEOUT = "0"`, line `33`): Disables Antigravity CLI's built-in print timeout so `WorkerSupervisor` controls lifecycle timeouts (`BOUNDED_RUN_TIMEOUT_SECONDS = 300.0`, `STALL_SILENCE_SECONDS = 900.0`).
3. **Model & Effort Suffix Normalization Invariant (`lines 34, 138-149`)**:
   - `KNOWN_EFFORT_SUFFIXES = ("-high", "-medium", "-low", "-xhigh", "-max")`.
   - `ticket-runner.yaml` configures `model.default: "gemini-3.8-flash-high"`, while `T101` and `T102` frontmatter specify `Reasoning: medium` (`variant = "medium"`).
   - Passing `--model gemini-3.8-flash-high` alongside `--effort medium` causes `agy` to abort immediately with `--model gemini-3.8-flash-high conflicts with --effort=medium`.
   - Therefore, when `variant` is non-empty and `model_id` ends with any suffix in `KNOWN_EFFORT_SUFFIXES`, `build_antigravity_run_command` MUST strip the suffix from `effective_model`:
     - `--model gemini-3.8-flash`
     - `--effort medium`
4. **Prompt Construction (`PromptBuilder.build_prompt`, `D:\Projects\runner\application\prompt_builder.py:72-239`)**:
   - Injects `<role>`, `<target_ticket>` (`ID`, `Title`, `Status`, `Dependencies`, `Body`), `<execution_discipline>` (`Read and follow the implementation skill at .agents/skills/implement/SKILL.md`), `<project_invariants>` (extracted from `D:\Repos\agent-skills\AGENTS.md`), `<known_gotchas>` (`docs/tickets/gotchas.md`), `<checkpoint>` (if `.agent/checkpoints/<ticket_id>/handoff.md` exists), `<retry_context>` (bounded failure excerpt on attempts > 1), and `<communication_protocol>`.

---

### 2.5 Session Logs Contract (`.agent/logs/<ticket_id>_session_<conversation_uuid>.jsonl`)
Managed by `WorkerSupervisor._init_logging` and `_rename_log_if_needed` (`D:\Projects\runner\application\worker_supervisor.py:617-652`):
1. **Initial Creation**: Opened as `.agent/logs/<ticket_id>_session_pending.jsonl` and `.agent/logs/<ticket_id>_session_pending.stderr.log`.
2. **Dynamic Rename on `init` Envelope**: Immediately upon decoding the first event carrying `session_id` (`conversation_id`), both files are renamed on disk to:
   - `.agent/logs/<ticket_id>_session_<conversation_uuid>.jsonl`
   - `.agent/logs/<ticket_id>_session_<conversation_uuid>.stderr.log`
3. **Closed 3-Event NDJSON Schema (`KNOWN_EVENT_TYPES = {"init", "step_update", "result"}`, `antigravity_worker.py:31`)**:
   - **Line 1 (`init`)**:
     ```json
     {"event": "init", "conversation_id": "<uuid>", "init": {"agent": "", "cwd": "D:\\Repos\\agent-skills", "model": "gemini-3.8-flash", "prompt": "..."}}
     ```
   - **Intermediate Lines (`step_update`)**:
     ```json
     {"event": "step_update", "step_update": {"conversation_id": "<uuid>", "step_index": 3, "state": "DONE", "step_type": "tool", "timestamp": "...", "tool_calls": [...], "usage": {"cache_read_tokens": 11520, "input_tokens": 5895, "model": "MODEL_PLACEHOLDER_M47", "output_tokens": 236, "thinking_tokens": 157, "total_tokens": 17808}}}
     ```
   - **Terminal Line (`result`)** (present when `agy` exits normally before signal kill timer expires):
     ```json
     {"event": "result", "result": {"conversation_id": "<uuid>", "response": "...", "status": "SUCCESS", "usage": {"cache_read_tokens": ..., "input_tokens": ..., "output_tokens": ..., "thinking_tokens": ..., "total_tokens": ...}}}
     ```
4. **Zero-Usage Anomaly Detection (`_detect_empty_success_result`, `antigravity_worker.py:216-247`)**:
   - If a `"result"` envelope reports `"status": "SUCCESS"` with an empty `"response": ""` AND missing/zero `usage` (`total_tokens == 0`, `input_tokens == 0`, `output_tokens == 0`), `decode_event` MUST flag `WorkerEvent.anomaly`:
     `"Antigravity result event reported SUCCESS with empty response and zero token usage."`
   - `WorkerSupervisor` (`worker_supervisor.py:709-713`) immediately terminates the run with `RunTerminationReason.FAILED` and `exit_code = 1`.

---

### 2.6 Completion Signal Contract (`.agent/signals/<ticket_id>_ready.json`)
Validated by `ReadySignal.parse` (`D:\Projects\runner\domain\signal.py:242-319`) and read via `JsonSignalRepository` (`D:\Projects\runner\adapters\json\signal_repository.py`).

1. **Pre-Run Purge**: Before spawning the Worker on each attempt, `GatekeeperTicketProcessor._process_ticket` (`D:\Projects\runner\application\ticket_processor.py:130-131`) deletes any stale `.agent/signals/<ticket_id>_ready.json` and `.agent/questions/<ticket_id>.json`.
2. **Exact File Path**: `D:\Repos\agent-skills\.agent\signals\T101_ready.json` (and `T102_ready.json`).
3. **Exact JSON Schema (`runner/domain/signal.py:268-318` & `prompt_builder.py:201-215`)**:
   ```json
   {
     "ticket_id": "T101",
     "status": "ready_for_verification",
     "modified_files": [
       "clean-architecture/agents/openai.yaml",
       "create-verification-skill/agents/openai.yaml",
       "live-qa/agents/openai.yaml",
       "maintain-verification-skill/agents/openai.yaml",
       "security-review/agents/openai.yaml",
       "smoke-fail/agents/openai.yaml",
       "software-architecture/agents/openai.yaml",
       "status/agents/openai.yaml"
     ],
     "self_review_notes": "Created 8 missing agents/openai.yaml files matching SKILL.md metadata and policy constraints.",
     "new_gotchas": [],
     "timestamp": "2026-10-25T12:30:00Z",
     "scope": "skills"
   }
   ```
   - **`ticket_id`** (`str`, required): Must exactly equal the active ticket ID (`"T101"` or `"T102"`). Mismatch raises `SignalCorruptedError`.
   - **`status`** (`str`, required): **MUST be `"ready_for_verification"`** (`SignalStatus.READY_FOR_VERIFICATION`, `signal.py:26`).
     > [!CAUTION]
     > Writing `"status": "ready"` (as loosely paraphrased in `orchestrate-runner.md` / `observations/T101.md`) is **INVALID** and causes `ReadySignal.parse` (`signal.py:282-284`) to raise `SignalFormatError: Ready signal field 'status' must be 'ready_for_verification', got: 'ready'`, which fails Gatekeeper verification and triggers a false `FLAKY` escalation!
   - **`modified_files`** (`list[str]`, required): Non-null list of relative file paths modified or created by the Worker.
   - **`self_review_notes`** (`str`, required): Non-null string summarizing pre-signal `/code-review` checks.
   - **`new_gotchas`** (`list[str]`, required): List of strings (usually `[]`).
   - **`timestamp`** (`str`, required): Valid ISO-8601 timestamp (`datetime.fromisoformat(ts.replace("Z", "+00:00"))`).
   - **`scope`** (`str | None`, optional): Lowercase conventional-commit scope matching `^[a-z][a-z0-9-]*$` (`SCOPE_PATTERN` in `signal.py:21`) and NOT matching `^T\d+$` (`TICKET_ID_PATTERN`). If omitted or invalid, `QueueOrchestrator._resolve_scope` falls back to `"queue"`.
4. **Signal Detection & Grace Window (`worker_supervisor.py:553-561`)**:
   - When `.agent/signals/<ticket_id>_ready.json` appears while `agy` is still running, `WorkerSupervisor` starts a `SIGNAL_GRACE_SECONDS = 10.0` timer. If `agy` exits within 10s, termination reason is `EXITED`; if still running after 10s, `WorkerSupervisor` kills the process tree with `KILLED_SIGNAL`, which maps to `WorkerRunStatus.READY` (`handoff_coordinator.py:570-571`).
5. **Signal Consumption**: `VerificationLoop.run` (`gatekeeper.py:1060-1062`) reads `.agent/signals/<ticket_id>_ready.json` and immediately deletes it via `self._signal_repository.consume_ready(ticket_id)`.
6. **Strict Worker Git & Queue Prohibitions**:
   - The Worker MUST NEVER execute `git commit`, `git push`, `git branch`, or `git checkout`.
   - The Worker MUST NEVER move or edit the ticket markdown file under `docs/tickets/` (nor stamp `Status: completed`).
   - The Worker MUST NEVER directly edit `docs/tickets/gotchas.md` (gotchas are passed via `new_gotchas` in `<ticket_id>_ready.json` and appended by `QueueOrchestrator` after human approval).

---

### 2.7 Gatekeeper & Token-Preserving Verification Contract
Implemented in `D:\Projects\runner\application\gatekeeper.py` and `D:\Projects\runner\application\evidence_triage.py`.

1. **Command Execution (`GatekeeperCommandExecutor.verify`, `gatekeeper.py:341-400`)**:
   - State transitions to `status: "GATEKEEPER"` in `.agent/state.json` and `run_state: "verifying"` in `.agent/status.json`.
   - **Step 1 (`verification.build_cmd`)**: Configured as `""` in `ticket-runner.yaml` → skipped (`CommandResult(command="", returncode=0, skipped=True)`).
   - **Step 2 (`verification.test_cmd`)**: Executed via `cmd.exe /d /s /c <command>` on Windows (`_build_shell_command`, `gatekeeper.py:203-209`) with `cwd="D:\\Repos\\agent-skills"`, `timeout_seconds=300`, `silence_window_seconds=60`:
     ```powershell
     cmd.exe /d /s /c python -c "import glob,yaml; fs=glob.glob('*/agents/openai.yaml'); [yaml.safe_load(open(f,encoding='utf-8')) for f in fs]; print('validated %d openai.yaml files' % len(fs))"
     ```
   - Expected stdout on `T101` and `T102`: `validated 45 openai.yaml files` and `returncode == 0`.
2. **Pre-Verification Ready-Signal Warnings (`_check_ready_warnings`, `gatekeeper.py:1143-1166`)**:
   - Checks `git status --porcelain` via `WorkingTreeInspector`. If `modified_files` in `<ticket_id>_ready.json` is empty while the working tree has changes, logs a warning (`"Ready signal declared no modified_files while working tree has changes: ..."`).
   - Scans `self_review_notes` for unresolved tokens (`\bTODO\b`, `\bFIXME\b`, `\buntested\b`, `\bskipped\b`).
3. **Evidence Persistence & Bounded Triage (`EvidenceTriage`, `D:\Projects\runner\application\evidence_triage.py`)**:
   - **Out-of-Band Evidence Directory**: `.agent/evidence/<ticket_id>/` (`RuntimePaths.ticket_evidence_dir`).
   - **Bounded Excerpt Limits (`evidence_triage.py:16-17`)**:
     - `MAX_EXCERPT_LINES = 30`
     - `MAX_EXCERPT_CHARS = 1000`
   - When `EvidenceTriage.extract(ticket_id, status, log_path)` runs, it extracts failure lines matching `(FAIL|ERROR|AssertionError|Traceback|Exception|E   )` (or the tail of the log), caps the excerpt at **<= 30 lines and <= 1,000 characters**, and persists `.agent/evidence/<ticket_id>/summary.json`:
     ```json
     {
       "ticket_id": "T101",
       "status": "failed",
       "excerpt": "...",
       "evidence_paths": ["D:\\Repos\\agent-skills\\.agent\\evidence\\T101\\..."]
     }
     ```
   - **Note on Standard `test_cmd` Execution**: `GatekeeperCommandExecutor.verify` (`gatekeeper.py:249-339`) buffers stdout/stderr in a 100-line in-memory deque (`TAIL_LINE_LIMIT = 100`) and writes `.agent/logs/<ticket_id>_diagnostic.md` (`MAX_DIAGNOSTIC_LINES = 100`) when an escalation or circuit-breaker trip occurs. If no external behavioral harness writes files into `.agent/evidence/<ticket_id>/`, `VerificationLoop._handle_approval` (`gatekeeper.py:1116-1120`) passes `evidence_paths=()` to `EvidenceCard`, which `TerminalApprovalAdapter.render_card` renders as `• .agent/evidence/<ticket_id>/`.
4. **Failure Retry & Circuit Breaker (`VerificationLoop._handle_failure`, `gatekeeper.py:1194-1265`)**:
   - On failure (`attempt < max_attempts`), `state_coordinator.increment_attempts()` increments `verification_attempts` (`1` → `2` → `3`).
   - **Escalation Check (`_check_escalation`, `gatekeeper.py:1267-1340`)**:
     - Note that `VerificationConfig.bug_escalation_at` defaults to `1` (`runner/domain/config.py:55`). Consequently, on any first verification failure (`attempt >= 1`), `FailureAnalyser.classify` (`runner/domain/failure_analyser.py`) classifies the failure (`FLAKY`, `REGRESSION`, `ENV_CONFIG`, or `CODE_BUG`), writes `.agent/logs/<ticket_id>_diagnostic.md`, sets `.agent/state.json` `status: "WAITING_FOR_USER"` and `.agent/status.json` `run_state: "escalating"`, `last_event: "ESCALATION_EMITTED"`, and prompts `[r] Retry with hint  [s] Skip ticket  [p] Pause queue  [a] Abort`.
   - **Circuit Breaker Trip (`attempt >= 3`)**:
     - After `3` failed attempts (`verification.max_attempts: 3`), Gatekeeper writes `.agent/logs/<ticket_id>_diagnostic.md`, transitions `.agent/state.json` to `status: "CIRCUIT_BREAKER_TRIPPED"`, publishes `.agent/status.json` with `run_state: "idle"` and `last_event: "CIRCUIT_BREAKER_TRIPPED"`, prompts intervention, and `ticket_runner.py` exits with code **`2`** (`runner/application/queue_orchestrator.py:710`).

---

### 2.8 Token Budgets & Context Handoffs Contract
Configured in `ticket-runner.yaml` (`token_budget`) and coordinated by `BudgetMonitor` (`D:\Projects\runner\application\budget_monitor.py`), `WorkerSupervisor` (`worker_supervisor.py:720-773`), and `HandoffCoordinator` (`D:\Projects\runner\application\handoff_coordinator.py`):

| Threshold | Token Count | Action & Telemetry Oracle |
|---|---|---|
| **`warn`** | `120,000` | `BudgetDecision.WARN`: `state_coordinator.record_tokens(occupancy, warning_sent=True)` sets `tokens.warning_sent = true` in `.agent/state.json`. Worker continues running. |
| **`handoff`** | `135,000` | `BudgetDecision.HANDOFF`: `WorkerSupervisor` kills active worker with `RunTerminationReason.KILLED_HANDOFF`. `HandoffCoordinator._execute_handoff` resumes the same `conversation_id` (`bounded_timeout=True`, 300s timeout) with the handoff prompt instructing the Worker to execute `.agents/skills/handoff/SKILL.md` and write `.agent/checkpoints/<ticket_id>/handoff.md`. |
| **`ceiling`** | `150,000` | `BudgetDecision.CEILING`: `WorkerSupervisor` immediately terminates the worker with `RunTerminationReason.KILLED_CEILING`. If a fresh `.agent/checkpoints/<ticket_id>/handoff.md` exists, resets session (`session_id = None`); otherwise writes a synthetic checkpoint (`format_synthetic_checkpoint`, containing `"synthesized — no Worker handoff"`) and prompts operator confirmation (`Continue recovery into fresh session? [Y/n]:`). |

- **Checkpoint Freshness Validation (`HandoffCoordinator._validate_checkpoint`, `handoff_coordinator.py:451-462`)**:
  - `.agent/checkpoints/<ticket_id>/handoff.md` must exist, be non-empty, and have `mtime >= cycle_started_at - 2.0` (`CLOCK_SLACK_SECONDS = 2.0`).
  - Maximum consecutive handoffs without a ReadySignal: `MAX_CONSECUTIVE_HANDOFFS = 5` (`handoff_coordinator.py:29`).
- **Expected Token Usage for `T101` & `T102`**:
  - Single-turn completion of `T101` or `T102` should consume roughly `15,000–60,000` total tokens (well below `warn: 120,000`). Hitting `135,000` or `150,000` on `T101` or `T102` indicates runaway file-reading or a retry loop.

---

### 2.9 Interactive UI & HITL Approval Gate Contract

#### A. `paused_display` Mutual Exclusion Guard (`D:\Projects\runner\ports\terminal_display.py:70-79`)
Whenever `RichTerminalDisplay` (`D:\Projects\runner\adapters\ui\rich_display.py`) is active, reading from stdin/console without stopping the Rich `Live` renderer causes swallowed keystrokes and garbled prompts. The `paused_display(display)` context manager MUST wrap every interactive console read across all three adapters wired in `D:\Projects\runner\container.py:239-290`:
1. **`TerminalInterventionGateway._read_line`** (`D:\Projects\runner\adapters\ui\terminal_prompts.py:67-71`): Wraps `self._input_fn(prompt)` inside `with paused_display(self._display):` for Worker questions (`ask_question`), circuit-breaker interventions (`request_intervention`), and failure escalations (`prompt_escalation`).
2. **`HandoffCoordinator.default_recovery_confirmation`** (`D:\Projects\runner\application\handoff_coordinator.py:49-65`): Wraps `input_fn("Continue recovery into fresh session? [Y/n]: ")` inside `with paused_display(display):`.
3. **`TerminalApprovalAdapter.request_approval`** (`D:\Projects\runner\adapters\ui\terminal_approval.py:66-107`): Wraps `render_card(card)` and key capture (`_read_key` / `msvcrt.getwch()`) inside `with paused_display(self._display):`, ensuring `display.stop()` runs before rendering the Evidence Card and `display.start()` runs in `finally:`.

#### B. Human-in-the-Loop Evidence Card (`TerminalApprovalAdapter`, `terminal_approval.py:46-107`)
After `GatekeeperCommandExecutor.verify` passes (`report.passed == True`) and `verification.approval_mode == "human"`:
1. Execution MUST halt before any git commit or ticket file relocation and render the Rich Panel titled `"Verification Approval — <ticket_id>"`:
   ```text
   ╭─────────────────────── Verification Approval — T101 ───────────────────────╮
   │ Ticket: T101 — Add Codex interface metadata to skills lacking it           │
   │ Status: PASSED                                                             │
   │                                                                            │
   │ Checks:                                                                    │
   │   • test: PASS — validated 45 openai.yaml files                            │
   │                                                                            │
   │ Evidence:                                                                  │
   │   • .agent/evidence/T101/                                                  │
   │                                                                            │
   │ Diff Summary:                                                              │
   │   <N> file(s) modified                                                     │
   │                                                                            │
   │ [y] Approve & Commit   [n] Reject (with reason)   [d] Launch /diagnosing-bugs │
   ╰────────────────────────────────────────────────────────────────────────────╯
   ```
2. **Operator Key Bindings**:
   - **`[y]` (`ApprovalDecision.APPROVE`)**: Returns `ApprovalResult(decision=ApprovalDecision.APPROVE)`. `VerificationLoop.run` returns `VerificationLoopOutcome(passed=True, attempts=1, ready_signal=ready_signal)`.
   - **`[n]` (`ApprovalDecision.REJECT`)**: Prompts `"Rejection reason: "`, wraps the rejection in a synthetic `VerificationReport(passed=False)` with `"Human rejected verification: <reason>"`, and loops back to the Worker (consuming an attempt).
   - **`[d]` (`ApprovalDecision.DIAGNOSE`)**: Prints `"Launch /diagnosing-bugs in your session to inspect evidence, then re-run."` and returns `VerificationLoopOutcome(passed=False, diagnosis_requested=True)` (halting without committing).

#### C. Post-Approval Atomic Commit & Archive (`QueueOrchestrator.run_next`, `queue_orchestrator.py:614-634`)
Immediately upon receiving `ApprovalDecision.APPROVE` (`outcome.approved == True`), `QueueOrchestrator.run_next` executes three operations in strict order:
1. **Finalize & Relocate Ticket (`DirectoryTicketStore.finalize_completed`, `D:\Projects\runner\adapters\markdown\ticket_store.py:135-146, 250-303`)**:
   - Reads `docs/tickets/01-runner-live-test-bootstrap/<ticket_filename>.md`.
   - Rewrites YAML frontmatter in-place:
     - `Status: pending` → `Status: completed`
     - Inserts or updates `Completed: YYYY-MM-DDTHH:MM:SSZ` (UTC ISO-8601 timestamp).
     - **Never** writes a commit SHA into ticket frontmatter (ADR 0012).
   - Ensures `docs/tickets/01-runner-live-test-bootstrap/completed/.gitkeep` exists.
   - Moves the ticket file to `docs/tickets/01-runner-live-test-bootstrap/completed/<ticket_filename>.md`.
2. **Append Gotchas (`GotchasStore.append`, `queue_orchestrator.py:616-617`)**:
   - If `outcome.new_gotchas` is non-empty, appends new bullets to `docs/tickets/gotchas.md`. (If `outcome.new_gotchas == []`, `docs/tickets/gotchas.md` is untouched).
3. **Author Single Conventional Commit (`GitOperations.commit_ticket`, `D:\Projects\runner\application\git_operations.py:149-189`)**:
   - Runs `git add .` followed by `git commit -m <message>`.
   - **Commit Header Format**: `<prefix>(<scope>): <clean_title>`
     - `<prefix>`: Resolved by `_resolve_commit_prefix(ticket)` (`queue_orchestrator.py:678-690`). Because neither `T101` nor `T102` sets `Type:` in frontmatter and their titles do not start with `fix`/`docs`/`chore`, `<prefix>` defaults to **`feat`** (unless `Type:` is present).
     - `<scope>`: Resolved by `_resolve_scope(ticket, outcome.scope)` (`queue_orchestrator.py:665-676`). Uses `ReadySignal.scope` if provided and valid (e.g., `"skills"` or `"docs"`), otherwise defaults to **`"queue"`**. Never a ticket number (`T101`/`T102`).
     - `<clean_title>`: `ticket.title` stripped of any `T\d{3,4}` tokens.
   - **Commit Body Format**: Blank line followed by hyphen-bulleted imperative lines (`- Update <file>`) generated from `outcome.modified_files` (with any `T\d{3,4}` stripped from filenames; e.g. `T101-add-codex-...` becomes `- Update -add-codex-...` if included in `modified_files`). No trailing periods on bullet lines, and no `T101` or `T102` anywhere in commit title or body.

---

## 3. Ticket-Specific Acceptance Oracles (`T101` & `T102`)

### 3.1 `T101`: Add Codex interface metadata to skills lacking it
- **Source Ticket Path (Pre-Completion)**: `D:\Repos\agent-skills\docs\tickets\01-runner-live-test-bootstrap\T101-add-codex-interface-metadata-to-skills-lacking-it.md`
- **Archived Ticket Path (Post-Completion)**: `D:\Repos\agent-skills\docs\tickets\01-runner-live-test-bootstrap\completed\T101-add-codex-interface-metadata-to-skills-lacking-it.md`
- **Frontmatter Config**: `Priority: high`, `Status: pending` → `completed`, `Dependencies: none`, `Reasoning: medium`.

#### Expected File Modifications (Exactly 8 New `<skill>/agents/openai.yaml` Files)
Each file MUST contain `interface:` with `display_name`, `short_description`, and `default_prompt` (all double-quoted strings derived from `<skill>/SKILL.md`). Furthermore, the 4 skills whose `SKILL.md` frontmatter contains `disable-model-invocation: true` MUST include `policy:\n  allow_implicit_invocation: false`, and the 4 skills without `disable-model-invocation: true` MUST omit `policy:`:

| # | Created File Path (Relative to `D:\Repos\agent-skills`) | `SKILL.md` `disable-model-invocation` | Required Top-Level YAML Keys | `policy.allow_implicit_invocation` |
|---|---|---|---|---|
| 1 | `clean-architecture/agents/openai.yaml` | Not set (`false`) | `interface:` only | **Must NOT be present** |
| 2 | `security-review/agents/openai.yaml` | Not set (`false`) | `interface:` only | **Must NOT be present** |
| 3 | `software-architecture/agents/openai.yaml` | Not set (`false`) | `interface:` only | **Must NOT be present** |
| 4 | `status/agents/openai.yaml` | Not set (`false`) | `interface:` only | **Must NOT be present** |
| 5 | `create-verification-skill/agents/openai.yaml` | `true` | `interface:` + `policy:` | **`false`** (boolean, unquoted) |
| 6 | `live-qa/agents/openai.yaml` | `true` | `interface:` + `policy:` | **`false`** (boolean, unquoted) |
| 7 | `maintain-verification-skill/agents/openai.yaml` | `true` | `interface:` + `policy:` | **`false`** (boolean, unquoted) |
| 8 | `smoke-fail/agents/openai.yaml` | `true` | `interface:` + `policy:` | **`false`** (boolean, unquoted) |

#### `T101` Verification & Post-Commit Git Tree Oracles
1. **Count Oracle**:
   - `glob.glob('*/agents/openai.yaml')` count increases from `37` → **`45`**.
   - Recursive `(Get-ChildItem -Path D:\Repos\agent-skills -Recurse -Filter openai.yaml).Count` increases from `37` → **`45`** (because `.agents/skills/` has `0` `openai.yaml` files).
2. **Gatekeeper `test_cmd` Output**:
   - Exact stdout: `validated 45 openai.yaml files`
   - Exit code: `0`
3. **Post-Commit Git Tree (`git show --stat HEAD` after `T101` approval)**:
   - Exactly **1 new commit** on `agent/ticket-runner` above `6912328`.
   - Commit title matches `^feat\([a-z][a-z0-9-]*\): Add Codex interface metadata to skills lacking it$` (with scope `"queue"` or Worker-supplied scope like `"skills"`).
   - Commit contains:
     - 8 newly created `<skill>/agents/openai.yaml` files.
     - Relocation (rename + frontmatter update `Status: completed`, `Completed: <timestamp>`) of `docs/tickets/01-runner-live-test-bootstrap/T101-add-codex-interface-metadata-to-skills-lacking-it.md` → `docs/tickets/01-runner-live-test-bootstrap/completed/T101-add-codex-interface-metadata-to-skills-lacking-it.md`.
     - Creation of `docs/tickets/01-runner-live-test-bootstrap/completed/.gitkeep` (if not already present).
     - Optional update to `docs/tickets/gotchas.md` ONLY if `ReadySignal.new_gotchas` was non-empty.
   - Zero existing `*/SKILL.md` files or pre-existing 37 `*/agents/openai.yaml` files modified.
   - `git status --porcelain` is completely empty (`""`) after commit.

---

### 3.2 `T102`: Document `agents/openai.yaml` in skill anatomy and contributing guide
- **Source Ticket Path (Pre-Completion)**: `D:\Repos\agent-skills\docs\tickets\01-runner-live-test-bootstrap\T102-document-agents-openai-yaml-in-skill-anatomy.md`
- **Archived Ticket Path (Post-Completion)**: `D:\Repos\agent-skills\docs\tickets\01-runner-live-test-bootstrap\completed\T102-document-agents-openai-yaml-in-skill-anatomy.md`
- **Frontmatter Config**: `Priority: medium`, `Status: pending` → `completed`, `Dependencies: T101`, `Reasoning: medium`.
- **Dependency Unblocking**: `DirectoryTicketStore.select_next_pending` (`D:\Projects\runner\adapters\markdown\ticket_store.py:114-129`) resolves `T101` as satisfied once `T101` has `Status: completed` inside `docs/tickets/01-runner-live-test-bootstrap/completed/`.

#### Expected File Modifications (`D:\Repos\agent-skills\README.md` Only)
1. **Change 1 — "Skill Directory Anatomy" Tree Block (`README.md` around lines `155-169`)**:
   - The former terminal entry `└── references/` MUST change its prefix connector from `└──` to `├──`, and a new `└── agents/` directory with nested `    └── openai.yaml` leaf MUST be appended using Unicode box-drawing characters (`├──`, `└──`, `│`), **never** ASCII `|--` or `` `-- ``:
     ```text
     <skill-name>/
     ├── SKILL.md              # Required — frontmatter + instructions
     ├── scripts/              # Optional — helper scripts and utilities
     ├── examples/             # Optional — reference implementations
     ├── resources/            # Optional — templates and assets
     ├── references/           # Optional — detailed docs loaded on demand
     └── agents/               # Codex / OpenAI agent interface metadata
         └── openai.yaml       # Display name, short description, default prompt, policy
     ```
2. **Change 2 — "Contributing" Checklist (`README.md` around lines `171-180`)**:
   - Adds a bullet (`- `) requiring `agents/openai.yaml` (covering `interface.display_name`, `interface.short_description`, `interface.default_prompt`, and `policy.allow_implicit_invocation: false` when `disable-model-invocation: true`), including the explicit carve-out phrase `"unless it is a documented exception"`.
3. **Preservation Invariant**:
   - The existing `"45 canonical skills"` count and all catalogue tables in `README.md` MUST remain intact.

#### `T102` Verification & Post-Commit Git Tree Oracles
1. **Gatekeeper `test_cmd` Output**:
   - Exact stdout: `validated 45 openai.yaml files`
   - Exit code: `0`
2. **Post-Commit Git Tree (`git show --stat HEAD` after `T102` approval)**:
   - Exactly **1 new commit** on `agent/ticket-runner` above the `T101` commit (`git rev-list --count 6912328..HEAD` == **`2`**).
   - Commit title matches `^feat\([a-z][a-z0-9-]*\): Document agents/openai\.yaml in skill anatomy and contributing guide$`.
   - Commit modifies only `README.md` and relocates `docs/tickets/01-runner-live-test-bootstrap/T102-document-agents-openai-yaml-in-skill-anatomy.md` → `docs/tickets/01-runner-live-test-bootstrap/completed/T102-document-agents-openai-yaml-in-skill-anatomy.md` (plus `docs/tickets/gotchas.md` only if `new_gotchas` was non-empty).
3. **Post-Queue Completion State**:
   - `docs/tickets/01-runner-live-test-bootstrap/` has **0** `.md` files remaining at top level; both `T101-*.md` and `T102-*.md` reside in `docs/tickets/01-runner-live-test-bootstrap/completed/` with `Status: completed` and `Completed: <ISO-8601 UTC timestamp>`.
   - `.agent/state.json` has `"active_ticket_id": null` and `"status": "IDLE"`.
   - `.agent/status.json` has `"run_state": "done"`.
   - `ticket_runner.py start --local-only` prints `"All tickets completed."` and exits with code **`0`**.

---

## 4. Anomaly & Regression Watchlist ("What Must NOT Happen")

The overseeing/debugging agent MUST continuously evaluate the live run against the 10 failure modes below. Items **1–7** are the canonical baseline regressions; Items **8–10** are live architectural defects discovered during code and log inspection of `D:\Projects\runner\` and `D:\Repos\agent-skills\.agent\`.

| # | Anomaly / Failure Mode | Observable Symptom / Detection Oracle | Root-Cause Module & Seam in `D:\Projects\runner\` | Required Triage / Remediation Action |
|---|---|---|---|---|
| **1** | **Silent / Truncated Worker Turn (Blocker F Regression)** | Worker subprocess exits in ~5s without emitting a `result` envelope or `.agent/signals/<ticket_id>_ready.json`; or `.agent/logs/<ticket_id>_session_*.jsonl` is missing/truncated after `init`. | `runner/adapters/antigravity/antigravity_worker.py:33,150-154` (`DEFAULT_PRINT_TIMEOUT = "0"` in `build_antigravity_run_command`) & `runner/application/worker_supervisor.py:514-567` | Verify `--print-timeout 0` is present in the spawned `agy` command line and check `.agent/logs/<ticket_id>_session_<uuid>.stderr.log` for CLI panics or auth/quota errors. |
| **2** | **Zero-Usage `SUCCESS` Turn** | `.agent/logs/<ticket_id>_session_<uuid>.jsonl` terminal `result` line has `"status": "SUCCESS"`, `"response": ""`, and zero/missing `usage` (`total_tokens == 0`). | `runner/adapters/antigravity/antigravity_worker.py:216-247` (`_detect_empty_success_result`) & `runner/application/worker_supervisor.py:709-713` | Confirm `decode_event` sets `WorkerEvent.anomaly` (`"Antigravity result event reported SUCCESS with empty response and zero token usage."`) and `WorkerSupervisor` marks the run `FAILED` rather than silently treating it as a clean exit. |
| **3** | **`agy` CLI Flag Conflict (`--model` vs `--effort`)** | `agy` exits immediately with non-zero code; `.stderr.log` contains `--model gemini-3.8-flash-high conflicts with --effort=medium`. | `runner/adapters/antigravity/antigravity_worker.py:34,138-149` (`KNOWN_EFFORT_SUFFIXES` stripping in `build_antigravity_run_command`) | Ensure `build_antigravity_run_command` strips `-high` from `model_id` whenever `variant` is set, passing `--model gemini-3.8-flash --effort medium`. |
| **4** | **Swallowed Terminal Prompts / Live Display Deadlock** | Runner enters `WAITING_FOR_USER` (escalation/question/recovery) or `GATEKEEPER` HITL approval (`[y]/[n]/[d]`), but `RichTerminalDisplay` stays active and eats keystrokes or overwrites the prompt. | `runner/ports/terminal_display.py:70-79` (`paused_display`), `runner/adapters/ui/terminal_prompts.py:67-71`, `runner/adapters/ui/terminal_approval.py:69-107`, `runner/application/handoff_coordinator.py:49-65`, `runner/container.py:239-290` | Verify `display` (`RichTerminalDisplay`) is injected into `TerminalInterventionGateway`, `TerminalApprovalAdapter`, and `default_recovery_confirmation` in `container.py`, and that all stdin reads execute inside `with paused_display(display):`. |
| **5** | **Synthesized Empty Handoff / Flaky Escalation Loop** | `.agent/checkpoints/<ticket_id>/handoff.md` contains `"synthesized — no Worker handoff"`, or `.agent/logs/<ticket_id>_diagnostic.md` reports `⚠ FLAKY detected — unknown` with `Tokens Consumed: 0 / 150,000`. | `runner/application/handoff_coordinator.py:68-86,294-334` (`format_synthetic_checkpoint`), `runner/application/gatekeeper.py:1058-1075,1267-1340` (`_check_escalation`), `runner/domain/failure_analyser.py:346-362` | Inspect why `VerificationLoop.run` failed before running `test_cmd`: either `agy` exited without writing `<ticket_id>_ready.json` (`RunTerminationReason.EXITED` → `WorkerRunStatus.CRASHED`), or `<ticket_id>_ready.json` failed `ReadySignal.parse` (see Anomaly #9). |
| **6** | **Unauthorized Worker Git or Queue File Actions** | Worker runs `git commit` or `git push` directly, edits files outside ticket scope, edits `docs/tickets/gotchas.md` directly, or moves `docs/tickets/.../T101*.md` to `completed/` itself. | `runner/application/prompt_builder.py:164-224` (`<communication_protocol>`), `runner/adapters/markdown/ticket_store.py:250-303` (`finalize_completed`), `runner/application/queue_orchestrator.py:614-634` | **Critical**: In recorded session `1405d342`, the Worker manually moved `T101` to `completed/`, stamped `Status: completed`, and edited `docs/tickets/gotchas.md` before writing `T101_ready.json`. If the Worker moves the ticket file itself, `DirectoryTicketStore.finalize_completed` will crash with `TicketFormatError: Ticket file not found` after human `[y]` approval! Revert any Worker-performed ticket relocation or `gotchas.md` edit before approving at the Human Gate. |
| **7** | **Unbounded Evidence Injection** | On verification failure retry (`attempt > 1`), `<retry_context>` in the Worker prompt exceeds `30` lines or `1,000` characters of raw test/harness stdout. | `runner/application/evidence_triage.py:16-17,28-97` (`MAX_EXCERPT_LINES = 30`, `MAX_EXCERPT_CHARS = 1000`) & `runner/application/gatekeeper.py:1244-1265` | Route failure outputs through `EvidenceTriage.extract()` and pass only `summary.excerpt` (`<= 30 lines`, `<= 1,000 chars`) into `VerificationLoop` retry context. |
| **8** | **Zero Token Telemetry in `.agent/state.json` & `.agent/status.json` Under `AntigravityWorker`** | `.agent/logs/<ticket_id>_session_<uuid>.jsonl` shows `step_update.usage.total_tokens > 0` and `result.usage.total_tokens > 0`, but `.agent/state.json` `tokens.current` and `.agent/status.json` `token_count` remain `0` throughout the run. | `runner/application/worker_supervisor.py:693,715` vs `runner/adapters/antigravity/antigravity_worker.py:31,273-324` | `WorkerSupervisor.run` (`worker_supervisor.py:715`) checks `if event.type == "step_finish":` (OpenCode's event type), whereas `AntigravityWorker.decode_event` emits `event.type` in `{"init", "step_update", "result"}`. Consequently, `BudgetMonitor.observe()` and `StateCoordinator.record_tokens()` are never invoked for Antigravity events, and `worker_supervisor.py:693` (`event.type in ("tool_call", "tool_use")`) misses Antigravity tool steps (`event.type == "step_update"` with `step_type == "tool"`). |
| **9** | **`ReadySignal` Status Enum Mismatch (`"ready"` vs `"ready_for_verification"`)** | Worker writes `.agent/signals/<ticket_id>_ready.json` with `"status": "ready"`, causing `VerificationLoop` to reject the signal with `SignalFormatError: Ready signal field 'status' must be 'ready_for_verification', got: 'ready'` and trigger a false `FLAKY` escalation. | `runner/domain/signal.py:26,282-284` (`SignalStatus.READY_FOR_VERIFICATION`) vs target repo docs `D:\Repos\agent-skills\docs\specs\orchestrate-runner.md` / `observations/T101.md` | If the Worker reads target-repo docs or skills that say `"status": "ready"`, `ReadySignal.parse` will fail. Verify `.agent/signals/<ticket_id>_ready.json` uses `"status": "ready_for_verification"` and contains all 6 required keys (`ticket_id`, `status`, `modified_files`, `self_review_notes`, `new_gotchas`, `timestamp`). |
| **10** | **Premature `KILLED_SIGNAL` Before Final `result` Envelope** | Worker writes `.agent/signals/<ticket_id>_ready.json` and then performs extra post-signal tool calls taking > `10.0s` (`SIGNAL_GRACE_SECONDS`), causing `WorkerSupervisor` to kill `agy` before `agy` flushes its final `result` JSONL line. | `runner/application/worker_supervisor.py:37,553-561` (`SIGNAL_GRACE_SECONDS = 10.0`, `RunTerminationReason.KILLED_SIGNAL`) | Writing `.agent/signals/<ticket_id>_ready.json` MUST be the Worker's final tool call. Note that `HandoffCoordinator` (`handoff_coordinator.py:570-571`) maps `KILLED_SIGNAL` to `WorkerRunStatus.READY`, so Gatekeeper still proceeds if `<ticket_id>_ready.json` is valid, though the session `.jsonl` log will lack a closing `result` line. |
