# Local Agentic Ticket Runner Plan

## 1. Goal

Build a **local Python ticket runner** that orchestrates OpenCode to execute tasks from a predefined `tickets.md` queue **strictly one ticket at a time**.

The user starts the runner on their PC, works locally at the terminal in **Nearby** mode (silencing remote alerts), and can walk away at any time. When the user is away, the runner detects idle prompts, escalates to **Away** mode, and routes questions and milestone notifications to **Discord**. The runner ensures complete working tree isolation, verifies all implementations through an independent Python gatekeeper, and commits each completed ticket sequentially.

---

## 2. Technology & Architecture

- **Orchestrator:** Python (asyncio runner managing subprocesses, file watchers, terminal UI, and Discord bot).
- **Coding Worker:** OpenCode CLI invoked as a managed subprocess (`opencode run --format json --session <id>`).
- **Communication:**
  - *Nearby Mode:* Interactive rich terminal dashboard with hotkeys (`[p]` pause, `[m]` mode toggle, `[q]` graceful quit).
  - *Away Mode:* In-process `discord.py` bot using a **Thread-per-Ticket** lifecycle under a designated channel.
- **Ticket Source:** `tickets.md` with active pending queue, global gotchas, and an auto-updated completed archive section at the bottom.
- **Execution Environment:** User's local PC (Windows PowerShell environment).
- **Handoff Mechanism:** Project-local handoff skill (`.agents/skills/handoff/SKILL.md`) checkpointing to `.agent/checkpoints/{ticket_id}/handoff.md`.
- **Gatekeeper:** Independent Python test/build execution with a 3-attempt circuit breaker before human escalation.
- **Git Strategy:** Dedicated `agent/ticket-runner` branch; Python stages and writes conventional commits; `.git/hooks/pre-push` blocks unauthorized pushes.

---

## 3. Ticket Queue (`tickets.md`)

`tickets.md` serves as the single source of truth for work items and cross-session knowledge.

### File Structure

```markdown
# Ticket Queue

## Global Gotchas & Lessons Learned
- Gotchas discovered across ticket runs are recorded here.
- Next tickets automatically ingest these lessons into their prompt context.

---

## T001 — Fix admin loading state
Status: pending

### Requirements
- Add loading state to verified datasets table.
- Prevent duplicate loading indicators on refetch.
- Preserve existing pagination and sorting behavior.

### Acceptance Criteria
- Loading spinner displays during async fetch.
- No layout shift or double scrollbars.
- Existing CRUD operations remain green.

### Gotchas
- Table component uses virtualized rendering; loading state must wrap the table body, not replace the container.

---

## T002 — Add dataset search filter
Status: pending
...

---

## Completed Tickets

## T000 — Project initialization
Status: completed
Completed: 2026-09-15 12:00:00
Commit: 8f31c2a
```

### Queue Dynamics & Non-Destructive Parser
- **Top-to-Bottom Execution:** The Runner picks the first ticket with `Status: pending`.
- **Live Re-Reading:** Before starting any new ticket, the Runner re-parses `tickets.md`. The user can insert, re-order, or adjust pending tickets and gotchas while the Runner is working on an earlier ticket.
- **Completed Relocation:** When a ticket passes Gatekeeper verification and is committed, the Runner updates its metadata (`Status: completed`, `Completed: <iso_time>`, `Commit: <sha>`) and moves the entire block to the `## Completed Tickets` section at the bottom, keeping the active queue clean.

---

## 4. Strict Sequential Execution & State Machine

Only one ticket is active at any time. The runner never starts ticket $N+1$ until ticket $N$ is verified and committed.

```text
       [START / RESUME]
              ↓
           DOCTOR (Pre-flight health checks)
              ↓
           PENDING (Select top pending ticket)
              ↓
           PLANNING & WORKING (opencode run --format json)
              ├── Token usage >= 135k → HANDOFF_REQUIRED → Checkpoint → Resume in Session B
              ├── Worker needs input  → WAITING_FOR_USER → Terminal / Discord prompt
              └── Worker requests pause → PAUSE_REQUESTED → Terminal / Discord alert
              ↓
       SIGNAL: .agent/signals/{ticket_id}_ready.json
              ↓
           GATEKEEPER (Independent Python test & build)
              ├── PASS → COMMIT → UPDATE TICKETS.MD → ARCHIVE THREAD → NEXT TICKET
              └── FAIL → Attempt < 3 → Send error log to Worker → Re-enter WORKING
                       → Attempt = 3 → CIRCUIT_BREAKER_TRIPPED → Escalate ([R]etry/[S]kip/[A]bort)
```

---

## 5. OpenCode Worker & Invocation Model

Python orchestrates OpenCode via CLI subprocesses with JSON event streaming:

```bash
opencode run --format json --session <session_id> --auto "<prompt>"
```

### Advantages of Subprocess JSON Streaming (ADR 0001)
1. **Precise Telemetry:** Captures every token metric, tool call (`read_file`, `edit_file`, `run_command`), and text chunk in real time.
2. **Crash Resilience:** Subprocesses have distinct lifecycles; if a session crashes or needs termination, no orphaned background HTTP daemon state remains.
3. **Deterministic Resumption:** Resuming an active ticket simply re-invokes `opencode run` with the existing `--session <session_id>`.

### Worker Prompt Context Injection
To avoid context bloat and history pollution, the Runner injects a strictly scoped prompt for each ticket:
1. **Ticket Slice:** Current ticket ID, title, requirements, acceptance criteria, and ticket-specific gotchas.
2. **Global Gotchas:** The current `## Global Gotchas & Lessons Learned` block from `tickets.md`.
3. **Execution Skill Pointer (ADR 0008):** Path to the configured execution skill (`config.yaml: worker.execution_skill`, defaulting to `.agents/skills/implement/SKILL.md`). The prompt instructs the Worker to adopt the discipline of this skill: work at pre-agreed seams using `/tdd`, and run typechecking and tests regularly.
4. **Operational Rules & Guardrails:**
   - Modify only files required for this ticket.
   - Run tests and builds locally during implementation to verify your own changes.
   - If clarification is needed, write `.agent/questions/{ticket_id}.json` and exit; do not guess.
   - **Do NOT commit:** Guardrail overrides any commit step in the execution skill; only the Runner Gatekeeper stages and commits.
   - **Pre-Signal Quality Review:** Run a `/code-review` self-check against the ticket requirements and capture findings in the `self_review_notes` field of `.agent/signals/{ticket_id}_ready.json`.
   - **Advisory Debugging:** `.agents/skills/diagnosing-bugs/SKILL.md` is available on disk if investigating hard test breaks or non-trivial errors.
   - When verified, write `.agent/signals/{ticket_id}_ready.json` and exit.
   - If context limit warning is received, run `.agents/skills/handoff/SKILL.md` to save `.agent/checkpoints/{ticket_id}/handoff.md`.


---

## 6. Context Management & Token Budgets

The runner supervises working memory using a 150,000-token budget:

```text
120,000 tokens → WARNING (Log notice; notify Discord thread if in Away mode)
135,000 tokens → AUTOMATIC HANDOFF TRIGGER
150,000 tokens → HARD CEILING (Subprocess terminated if handoff ignored)
```

Effective limit formula:
$$\text{effective\_limit} = \min(\text{configured\_runner\_limit}, \text{model\_context\_limit})$$

---

## 7. Context Handoff Protocol

When the 135k threshold is reached:
1. **Prompted Handoff:** The Runner issues a high-priority prompt to the active session:
   ```text
   Context budget threshold reached (135k tokens).
   Execute the handoff skill at .agents/skills/handoff/SKILL.md.
   Save the handoff document directly to .agent/checkpoints/{ticket_id}/handoff.md.
   Include modified files, architectural decisions, test status, and immediate next steps.
   Then exit.
   ```
2. **Session Rollover:** The Runner verifies that `.agent/checkpoints/{ticket_id}/handoff.md` was created, closes Session A, and generates Session B.
3. **Session B Resumption:**
   ```bash
   opencode run --format json --session <session_b_id> --auto \
     "Resume Ticket {ticket_id}. First read your previous handoff at .agent/checkpoints/{ticket_id}/handoff.md and inspect git status, then continue implementation."
   ```
4. **Zero User Disruption:** The handoff occurs transparently in the background without user intervention.

---

## 8. Isolation Layers: Preventing History & File Confusion

To prevent confusion when dozens of tickets and files have been processed in earlier runs:

1. **Working Tree Cleanliness:** Python verifies `git status --porcelain` is empty before starting any ticket, and commits all changes immediately after verification. Ticket $N+1$ always starts with a pristine working tree.
2. **Context Isolation:** The Runner never feeds entire historical logs or past checkpoints to OpenCode. OpenCode only sees the active ticket slice and current global gotchas.
3. **Thread Auto-Archiving:** Discord threads are automatically archived and locked upon ticket completion, keeping the active Discord channel focused on current work.
4. **Scoped Runtime Files:** Checkpoints, signals, questions, and logs are segregated by ticket ID (`.agent/checkpoints/T001/`, `.agent/signals/T001_ready.json`).

---

## 9. Signal Protocol (Worker-to-Runner Communication)

Rather than relying on brittle parsing of freeform LLM chat logs, the Runner listens for structured filesystem signals (ADR 0004).

### Ready for Gatekeeper Signal: `.agent/signals/{ticket_id}_ready.json`
```json
{
  "ticket_id": "T001",
  "status": "ready_for_verification",
  "modified_files": ["src/admin/Table.tsx", "src/admin/Table.test.tsx"],
  "self_review_notes": "Added loading spinner; all 14 unit tests passed locally.",
  "new_gotchas": [
    "Table refetch event fires twice if query key is not memoized."
  ],
  "timestamp": "2026-09-15T14:30:00Z"
}
```

### Clarification Question Signal: `.agent/questions/{ticket_id}.json`
```json
{
  "ticket_id": "T001",
  "question": "Should the verified datasets table display a skeleton placeholder or a centered spinner during fetch?",
  "type": "choice",
  "options": [
    "A: Skeleton placeholder rows",
    "B: Centered loading spinner"
  ],
  "status": "pending",
  "answer": null,
  "created_at": "2026-09-15T14:15:00Z"
}
```

When an answer is supplied (via terminal or Discord), the Runner writes `"status": "answered"` and `"answer": "A"`, then prompts OpenCode:
```bash
opencode run --format json --session <id> --auto "User answered: A: Skeleton placeholder rows. Proceed with implementation."
```

---

## 10. Hybrid Presence Modes (`nearby` vs `away`)

The Runner eliminates alert fatigue through a dual presence model (ADR 0003):

| Feature | Nearby Mode (At Desk) | Away Mode (Remote) |
| :--- | :--- | :--- |
| **Notification Target** | Local Terminal Console | Discord Channel & Threads |
| **Question Prompts** | Interactive Terminal CLI | Interactive Discord Thread Message |
| **Discord Notifications** | Silenced (Milestones only) | Full alerts (warnings, handoffs, questions) |
| **Idle Escalation** | Escalates to Away after 3m | N/A (Already in Away mode) |

### Mode Controls
- **CLI Startup:** `python ticket_runner.py start --mode nearby` (default) or `--mode away`.
- **Terminal Hotkeys:** Press `[m]` to toggle immediately between Nearby and Away.
- **Discord Commands:** Type `/mode away` or `/mode nearby` in Discord to switch remote state.
- **Inactivity Escalation:** If a question sits unanswered at the terminal for 3 minutes in Nearby mode, the Runner automatically switches to Away mode and notifies Discord with a high-priority ping.

---

## 11. Discord Integration

The Discord bot runs directly in-process using `discord.py` within the asyncio event loop.

### Thread-per-Ticket Lifecycle
1. **Thread Creation:** When `T001` starts, the bot posts in `#ticket-runner`:
   > 🚀 **Starting T001 — Fix admin loading state**
   and opens a thread `T001-fix-admin-loading-state`.
2. **Scoped Thread Stream:** Token warnings (120k), context handoff notices, and Gatekeeper diagnostic logs are posted directly inside the thread.
3. **Q&A Interaction:** When OpenCode writes a question signal, the bot posts the question and choices in the thread:
   > ❓ **T001 requires clarification:**
   > A: Skeleton placeholder rows
   > B: Centered loading spinner
   > *Reply with `A` or `B` to resume.*
4. **Resolution & Archiving:** Upon ticket completion, the bot posts the final commit SHA and summary, then archives and locks the thread.

---

## 12. Independent Gatekeeper Verification & Circuit Breaker

OpenCode cannot mark a ticket completed. The Python Runner acts as an authoritative Gatekeeper (ADR 0002).

### Verification Workflow
```text
Worker emits {ticket_id}_ready.json
                 ↓
Gatekeeper executes configured build_cmd (e.g. npm run build)
                 ↓
Gatekeeper executes configured test_cmd (e.g. npm test)
                 ↓
        Did all commands exit 0?
             /            \
          YES              NO
          /                  \
Pass Gatekeeper        Attempt < 3?
       ↓                /          \
Stage & Commit       YES            NO (Circuit Breaker Tripped)
Update tickets.md     ↓                      ↓
Proceed to next   Send error log       Pause Queue (PAUSE_REQUESTED)
                  to Worker session    Alert Terminal & Discord
                  Retry implementation Offer: [R]etry, [S]kip, [A]bort
```

### Circuit Breaker Actions
When Attempt 3 fails, the user can respond via Terminal or Discord:
- `[R]etry [hint]`: Reset the circuit breaker and pass an optional human hint to the agent.
- `[S]kip`: Stash/abandon uncommitted edits, record the failure in `tickets.md`, and advance to the next ticket.
- `[A]bort`: Gracefully shut down the runner to permit manual debugging on the PC.

---

## 13. Git Strategy & Safety Guardrails

Autonomous development requires strict git safety bounds:

### Dedicated Branch
All automated work occurs on `agent/ticket-runner`. The runner checks this branch out on startup (creating it from `main` or the current HEAD if it does not exist). `main` is never modified directly.

### Authoritative Python Commits
When Gatekeeper verification passes:
1. Python checks `git status --porcelain` to verify the modified files match expectations.
2. Python stages files: `git add .`
3. Python commits with a standardized message:
   ```text
   feat(T001): Fix admin loading state

   - Loading spinner displays during async fetch
   - Verified via Gatekeeper (tests: PASS, build: PASS)
   - Completed by OpenCode Worker
   ```
4. Commit SHA is extracted and written to `tickets.md` and `state.json`.

### Pre-Push Git Hook Guardrail (ADR 0005)
To physically prevent accidental `git push` operations by LLM tool calls:
- The Runner installs `.git/hooks/pre-push` during startup if not present:
  ```bash
  #!/bin/sh
  current_branch=$(git symbolic-ref --short HEAD 2>/dev/null)
  if [ "$current_branch" = "agent/ticket-runner" ]; then
    echo "ERROR: Direct git push is blocked on agent/ticket-runner branch." >&2
    exit 1
  fi
  exit 0
  ```

---

## 14. Pre-Flight Health Check ("Doctor")

When `python ticket_runner.py start` executes, it runs a pre-flight Doctor check before beginning queue operations:

1. **CLI Availability:** Verifies `opencode` binary exists and runs.
2. **Git Workspace Cleanliness:** Ensures git repository is initialized and the working tree is clean.
3. **Queue Validation:** Validates `tickets.md` exists and contains at least one pending ticket.
4. **Config Verification:** Validates `config.yaml` syntax and verification commands.
5. **Guardrail Hook:** Verifies `.git/hooks/pre-push` is installed and executable.
6. **Discord Connectivity:** If `discord.enabled: true`, verifies bot credentials and channel accessibility.

If any check fails, the Doctor prints clear diagnostic feedback and exits without modifying workspace state.

---

## 15. Persistent Runner State (`.agent/state.json`)

The Runner state is continuously persisted to survive unexpected reboots or power outages:

```json
{
  "active_ticket_id": "T001",
  "status": "WORKING",
  "opencode_session_id": "ses_01J8ABC123...",
  "presence_mode": "nearby",
  "verification_attempts": 0,
  "tokens": {
    "current": 64200,
    "warning_sent": false
  },
  "branch": "agent/ticket-runner",
  "started_at": "2026-09-15T14:00:00Z",
  "last_checkpoint": ".agent/checkpoints/T001/handoff.md",
  "last_updated": "2026-09-15T14:32:10Z"
}
```

### Crash Recovery Flow
1. On startup, Runner inspects `.agent/state.json`.
2. If an unfinished ticket was in `WORKING` or `PLANNING`:
   - Inspects `git status` for uncommitted edits.
   - Attempts to reconnect to `opencode_session_id`.
   - If the session is invalid or cannot be resumed, inspects the latest checkpoint in `.agent/checkpoints/{ticket_id}/` and resumes in a fresh session.

---

## 16. Queue Completion & Lifecycle

When all pending tickets in `tickets.md` are marked completed:
- The runner emits a completion notification to Discord and terminal:
  > 🎉 **Queue Completed! 12/12 tickets verified and committed.**
- Depending on the configured `queue_completion` setting:
  - **`standby` (Default):** The Runner remains running in an idle watch loop, monitoring `tickets.md` for newly appended pending tickets. If the user appends a ticket, the Runner resumes automatically.
  - **`terminate`:** The Runner prints a summary and cleanly exits the process.

---

## 17. Configuration Specification (`config.yaml`)

```yaml
project:
  name: "ticket-runner"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pytest"
  build_cmd: ""
  max_retries: 3
  timeout_seconds: 300

tokens:
  warn: 120000
  handoff: 135000
  ceiling: 150000

presence:
  default_mode: "nearby"       # nearby | away
  idle_escalation_minutes: 3   # escalate prompt to Discord if unprompted

discord:
  enabled: true
  token_env: "DISCORD_BOT_TOKEN"
  channel_id: ""               # Target channel ID for ticket threads

lifecycle:
  queue_completion: "standby"  # standby | terminate

git:
  auto_push: false
  commit_prefix: "feat"
  enforce_pre_push_hook: true
```

---

## 18. Project Directory Structure

The authoritative Clean Architecture directory tree is defined in [ARCHITECTURE.md](ARCHITECTURE.md) (and recorded in [ADR 0009: Clean Architecture and Concentric Layering for Runner File Structure](docs/adr/0009-clean-architecture-file-structuring.md)). All source code and test doubles strictly adhere to that layout.

---

## 19. Target User Experience

```text
$ python ticket_runner.py start

[Doctor] Verifying environment...
  ✓ opencode CLI found
  ✓ git repository clean on agent/ticket-runner
  ✓ pre-push hook active
  ✓ tickets.md parsed: 3 pending tickets
  ✓ Discord bot connected (standby in Nearby mode)

╔════════════════════════════════════════════════════════════════════╗
║ TICKET RUNNER — NEARBY MODE                                        ║
║ Active Ticket: T001 — Fix admin loading state                      ║
║ State: WORKING  |  Tokens: [████░░░░░░] 48,200 / 135,000           ║
║ Hotkeys: [p] Pause  [m] Toggle Away  [q] Quit                      ║
╚════════════════════════════════════════════════════════════════════╝

[Worker] Modifying src/admin/Table.tsx...
[Worker] Emitted signal: .agent/signals/T001_ready.json
[Gatekeeper] Running build_cmd: npm run build (PASS)
[Gatekeeper] Running test_cmd: npm test (PASS)
[Git] Committed feat(T001): Fix admin loading state (sha: 7a82c19)
[Queue] T001 moved to Completed Tickets in tickets.md

Starting T002...
[User steps away from PC]
[Runner] 3 minutes idle on question -> Switched to AWAY mode -> Pinged Discord thread
[User answers via Discord on phone] -> Resuming T002...
```