# Local Agentic Ticket Runner — Remaining Roadmap

> [!NOTE]
> **Status: Historical** — Specs 01 (Doctor & Git Ops), 02 (Queue & Tickets), and 03 (Worker Orchestration & Handoff) are fully implemented. Working code, unit tests, and `ARCHITECTURE.md` are the authoritative source of truth for those areas. The sections below cover the **remaining design intent for Specs 04–06** (Signal Protocol & Gatekeeper, Presence Mode & Discord, State Persistence & TUI). Consult `docs/specs/04-*.md`, `05-*.md`, and `06-*.md` for the formal decompositions.

---

## 1. Goal

Build a **local Python ticket runner** that orchestrates OpenCode to execute tasks from a predefined ticket queue **strictly one ticket at a time**.

The user starts the runner on their PC, works locally at the terminal in **Nearby** mode (silencing remote alerts), and can walk away at any time. When the user is away, the runner detects idle prompts, escalates to **Away** mode, and routes questions and milestone notifications to **Discord**. The runner ensures complete working tree isolation, verifies all implementations through an independent Python gatekeeper, and commits each completed ticket sequentially.

---

## 2. Technology & Architecture

- **Orchestrator:** Python (asyncio runner managing subprocesses, file watchers, terminal UI, and Discord bot).
- **Coding Worker:** OpenCode CLI invoked as a managed subprocess (`opencode run --format json --session <id>`).
- **Communication:**
  - *Nearby Mode:* Interactive rich terminal dashboard with hotkeys (`[p]` pause, `[m]` mode toggle, `[q]` graceful quit).
  - *Away Mode:* In-process `discord.py` bot using a **Thread-per-Ticket** lifecycle under a designated channel.
- **Ticket Source:** Directory-based queue under `docs/tickets/<spec-slug>/` with active pending tickets, completed archive subfolder, and `docs/tickets/gotchas.md`.
- **Execution Environment:** User's local PC (Windows PowerShell environment).
- **Handoff Mechanism:** Project-local handoff skill (`.agents/skills/handoff/SKILL.md`) checkpointing to `.agent/checkpoints/{ticket_id}/handoff.md`.
- **Gatekeeper:** Independent Python test/build execution with a 3-attempt circuit breaker before human escalation.
- **Git Strategy:** Dedicated `agent/ticket-runner` branch; Python stages and writes conventional commits; `.git/hooks/pre-push` blocks unauthorized pushes.

---

## 3. Strict Sequential Execution & State Machine

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
               ├── PASS → RELOCATE TICKET & GOTCHAS → ATOMIC COMMIT → ARCHIVE THREAD
               │         ├── Pending tickets remain → NEXT TICKET
               │         └── Queue exhausted → PROMPT CLEAN SLATE [Y/n] → ARCHIVE & CLEANUP COMMIT → STANDBY/EXIT
               └── FAIL → Attempt < 3 → Send error log to Worker → Re-enter WORKING
                        → Attempt = 3 → CIRCUIT_BREAKER_TRIPPED → Escalate ([R]etry/[S]kip/[A]bort)
```

---

## 4. Context Management & Token Budgets

The runner supervises working memory using a 150,000-token budget:

```text
120,000 tokens → WARNING (Log notice; notify Discord thread if in Away mode)
135,000 tokens → AUTOMATIC HANDOFF TRIGGER
150,000 tokens → HARD CEILING (Subprocess terminated if handoff ignored)
```

Effective limit formula:
$$\text{effective\_limit} = \min(\text{configured\_runner\_limit}, \text{model\_context\_limit})$$

---

## 5. Signal Protocol (Worker-to-Runner Communication) — Spec 04

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

## 6. Hybrid Presence Modes (`nearby` vs `away`) — Spec 05

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

## 7. Discord Integration — Spec 05

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

## 8. Independent Gatekeeper Verification & Circuit Breaker — Spec 04

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
- `[S]kip`: Stash/abandon uncommitted edits, record the failure in the ticket, and advance to the next ticket.
- `[A]bort`: Gracefully shut down the runner to permit manual debugging on the PC.

---

## 9. Persistent Runner State (`.agent/state.json`) — Spec 06

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

## 10. Queue Completion & Lifecycle — Spec 06

When all pending tickets in `docs/tickets/` are marked completed:
- The runner emits a completion notification to Discord and terminal:
  > 🎉 **Queue Completed! All tickets verified and committed.**
- Depending on the configured `queue_completion` setting:
  - **`standby` (Default):** The Runner remains running in an idle watch loop, monitoring `docs/tickets/` for newly added pending tickets. If the user adds a ticket, the Runner resumes automatically.
  - **`terminate`:** The Runner prints a summary and cleanly exits the process.

---

## 11. Configuration Specification (`config.yaml`)

```yaml
project:
  name: "ticket-runner"
  branch: "agent/ticket-runner"
  base_branch: "main"

model:
  default_reasoning: ""      # passed as --variant; flag is omitted when empty
  models:
    - id: "deepseek/deepseek-chat"
      label: "DeepSeek Chat"
    - id: "qwen/qwen-plus"
      label: "Qwen Plus"

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
  clean_slate: "interactive"   # interactive | always | never

git:
  auto_push: false
  commit_prefix: "feat"
  enforce_pre_push_hook: true
```

---

## 12. Project Directory Structure

The authoritative Clean Architecture directory tree is defined in [ARCHITECTURE.md](ARCHITECTURE.md) (and recorded in [ADR 0009: Clean Architecture and Concentric Layering for Runner File Structure](docs/adr/0009-clean-architecture-file-structuring.md)). All source code and test doubles strictly adhere to that layout.

---

## 13. Target User Experience

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
║ Active Ticket: T025 — Implement signal watcher                     ║
║ State: WORKING  |  Tokens: [████░░░░░░] 48,200 / 135,000           ║
║ Hotkeys: [p] Pause  [m] Toggle Away  [q] Quit                      ║
╚════════════════════════════════════════════════════════════════════╝

[Worker] Modifying runner/adapters/filesystem/signal_watcher.py...
[Worker] Emitted signal: .agent/signals/T025_ready.json
[Gatekeeper] Running build_cmd: (skipped)
[Gatekeeper] Running test_cmd: pytest (PASS)
[Git] Committed feat(adapters): Implement signal watcher
[Queue] T025 moved to completed/

Starting T026...
[User steps away from PC]
[Runner] 3 minutes idle on question -> Switched to AWAY mode -> Pinged Discord thread
[User answers via Discord on phone] -> Resuming T026...
```