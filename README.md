# Ticket Runner

A local Python orchestrator that coordinates OpenCode to execute sequential development tickets autonomously with strict gatekeeping, context handoffs, and remote Discord/CLI interaction.

---

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [How to Use](#how-to-use)
  - [CLI Commands](#cli-commands)
  - [Terminal UI & Hotkeys](#terminal-ui--hotkeys)
  - [Presence Modes: Nearby vs. Away](#presence-modes-nearby-vs-away)
- [How It Works](#how-it-works)
  - [Execution State Machine](#execution-state-machine)
  - [Gatekeeper & Circuit Breaker](#gatekeeper--circuit-breaker)
  - [Context Handoffs & Token Budgets](#context-handoffs--token-budgets)
  - [Git Safety & Push Guardrails](#git-safety--push-guardrails)
- [Ticket Queue Workflow](#ticket-queue-workflow)
  - [Ticket File Format](#ticket-file-format)
  - [Queue Dynamics & Lockfile](#queue-dynamics--lockfile)
- [Configuration Reference (`config.yaml`)](#configuration-reference-configyaml)
- [Project Documentation & Specifications](#project-documentation--specifications)

---

## Overview

Large language model agents are powerful at implementing scoped coding tasks, but left unconstrained across long runs they can hallucinate completion, exhaust context windows, or push unverified changes upstream.

**Ticket Runner** solves this by acting as a strict, local orchestrator:
1. **One Ticket at a Time:** Executes work sequentially from an ordered queue under `docs/tickets/`.
2. **Independent Verification (Gatekeeper):** Never trusts the agent's self-report; automatically runs configured test suites and builds before accepting work.
3. **Context Preservation:** Monitors token consumption in real time, triggering structured context handoffs to fresh sessions before degradation occurs.
4. **Presence Modes:** Displays a rich interactive terminal dashboard while you are at your desk (**Nearby Mode**), and escalates unanswered prompts to **Discord** threads when you walk away (**Away Mode**).
5. **Git Guardrails:** Works strictly on a dedicated `agent/ticket-runner` branch with an installed pre-push hook that prevents automated work from pushing to remote repositories.

---

## Key Features

- **Sequential Execution Loop:** Processes tickets one-by-one; relocates finished tickets to a `completed/` archive upon Gatekeeper pass.
- **Pre-Flight Doctor:** Validates OpenCode availability, git working tree cleanliness, configuration syntax, and hook installation before any code runs.
- **Discord Thread-per-Ticket:** In Away mode, opens a dedicated Discord thread per ticket to stream milestone alerts and collect interactive prompt answers directly from your mobile device.
- **Circuit Breaker:** Halts automatic retry loops after 3 consecutive failed verification attempts and escalates to a human decision (`[R]etry`, `[S]kip`, `[A]bort`).
- **Clean Architecture:** Strict inward-pointing boundaries with zero I/O in the core domain, abstract ports for all dependencies, and test doubles for deterministic verification.

---

## Prerequisites

- **Operating System:** Windows 10/11 (PowerShell environment) or Linux/macOS with a POSIX-compliant shell.
- **Python:** Version **3.11** or higher.
- **OpenCode CLI:** Installed and authenticated in your system PATH (`opencode`).
- **Git:** Git 2.30+ installed.
- **Discord Account (Optional):** Required only if enabling remote Away Mode notifications via Discord bot.

---

## Installation & Setup

### 1. Clone the Repository
```powershell
git clone https://github.com/your-org/ticket-runner.git
cd ticket-runner
```

### 2. Create and Activate a Virtual Environment
```powershell
# On Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# On Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```
*(Dependencies include `pyyaml`, `rich`, `discord.py`, and `pytest` for testing).*

### 4. Create Your Configuration
Copy the starter template:
```powershell
Copy-Item config.example.yaml config.yaml
```

Customize `config.yaml` to match your test commands and project settings. See the [Configuration Reference](#configuration-reference-configyaml) below for details.

### 5. Set Environment Variables (If Using Discord)
If Discord integration is enabled in `config.yaml`, set the bot token environment variable (never store raw tokens in `config.yaml`):
```powershell
# PowerShell
$env:DISCORD_BOT_TOKEN = "your_actual_discord_bot_token"

# Bash / Zsh
export DISCORD_BOT_TOKEN="your_actual_discord_bot_token"
```

---

## How to Use

### CLI Commands

Ticket Runner provides an entry-point CLI (`ticket_runner.py`):

```powershell
# Run pre-flight health checks to verify your environment
python ticket_runner.py doctor

# Start the runner and begin processing the queue
python ticket_runner.py start

# Display the active ticket, token usage, and presence status
python ticket_runner.py status

# Pause the active runner and release the queue lock for edits
python ticket_runner.py pause
```

### Terminal UI & Hotkeys

When started in **Nearby Mode**, Ticket Runner displays a rich split terminal dashboard:

```text
╔════════════════════════════════════════════════════════════════════╗
║ TICKET RUNNER — NEARBY MODE                                        ║
║ Active Ticket: T001 — Fix admin loading state                      ║
║ State: WORKING  |  Tokens: [████░░░░░░] 48,200 / 135,000           ║
║ Hotkeys: [p] Pause  [m] Toggle Away  [q] Quit                      ║
╚════════════════════════════════════════════════════════════════════╝
[14:22:01] Worker reading src/admin/Table.tsx
[14:22:15] Worker modified src/admin/Table.tsx
[14:22:30] Emitted signal: .agent/signals/T001_ready.json
[14:22:31] Gatekeeper executing test suite: pytest
```

Interactive hotkeys are non-blocking:
- `[p]` — **Pause**: Immediately requests pause and releases `docs/tickets/.queue.lock` so you can add, edit, or reorder tickets.
- `[m]` — **Toggle Mode**: Manually switches between `Nearby` and `Away` presence modes.
- `[q]` — **Quit**: Gracefully terminates child worker processes, persists state to `.agent/state.json`, and shuts down.

### Presence Modes: Nearby vs. Away

- **Nearby Mode (Default):** Silences remote Discord pings while you are active at the terminal. Prompts and questions appear directly in your local terminal.
- **Away Mode:** Activated either manually via `[m]` or automatically after 3 minutes of idle inactivity on an unanswered prompt. In Away mode, questions and milestone notifications route directly to ticket-specific Discord threads.

---

## How It Works

### Execution State Machine

Only **one** ticket is executed at a time. The loop follows strict transitions:

```text
       [START]
          ↓
       DOCTOR (Pre-flight checks: git, CLI binaries, config, hooks)
          ↓
       PENDING (Select top alphanumeric pending ticket)
          ↓
    WORKING & PLANNING (opencode run --format json --session <id>)
       ├── Token usage >= 135k → Checkpoint handoff → Resume in fresh session
       ├── Worker needs input  → Terminal prompt / Discord thread
       └── Pause requested     → Release lock & wait
          ↓
   READY SIGNAL (.agent/signals/{ticket_id}_ready.json)
          ↓
      GATEKEEPER (Runs independent test_cmd & build_cmd)
       ├── PASS → Commit (<type>(<scope>): <Title>) → Archive ticket → Next ticket
       └── FAIL (Attempts < 3) → Feed errors to Worker → Retry WORKING
                (Attempts = 3) → CIRCUIT BREAKER TRIPPED → Escalate ([R]etry/[S]kip/[A]bort)
```

### Gatekeeper & Circuit Breaker

- **Independent Verification:** The OpenCode Worker cannot mark tickets as completed. Only the Gatekeeper can accept a ticket by running your configured `test_cmd` and `build_cmd`.
- **Circuit Breaker:** If a ticket fails Gatekeeper verification 3 times consecutively, the Circuit Breaker trips, alerting you via terminal or Discord to choose:
  - `[R]etry`: Give the worker another cycle with guidance.
  - `[S]kip`: Move the ticket to a deferred state and proceed to the next ticket.
  - `[A]bort`: Safely shut down the runner.

### Context Handoffs & Token Budgets

To prevent model hallucination caused by context saturation, Ticket Runner monitors token usage during OpenCode streaming:
- **120,000 tokens:** Warning emitted to dashboard/Discord.
- **135,000 tokens:** Automated Context Handoff triggered. The Worker executes `.agents/skills/handoff/SKILL.md` to persist progress to `.agent/checkpoints/{ticket_id}/handoff.md`. The runner then resumes in a fresh OpenCode session with the checkpoint as context.
- **150,000 tokens:** Hard ceiling forcing immediate session rollover.

### Spec Context Excerpt Injection (ADR 0011)

To ground the Worker in overarching architectural goals without exhausting context windows:
- Each ticket is linked to its parent spec (via an explicit `Spec:` header or inferred from `docs/specs/<spec-slug>.md`).
- The Runner extracts the `## Problem Statement` and `## Solution` sections (~300 tokens) and inlines them directly into the Worker's initial prompt as a **Spec Excerpt**.
- The prompt includes a path link to the full spec file so the Worker can inspect deeper user stories or acceptance criteria on demand using its file reading tools.

### Git Safety & Push Guardrails

- All automated work occurs on `agent/ticket-runner`.
- The Runner commits verified code using conventional commit messages with subsystem scope and bulleted changes, never including ticket numbers (e.g., `feat(admin): Fix admin loading state`).
- An installed pre-push hook (`.git/hooks/pre-push`) rejects all pushes from the agent branch to remote origins, guaranteeing zero unintended upstream pushes.

---

## Ticket Queue Workflow

Tickets live under `docs/tickets/<spec-slug>/` as individual markdown files.

```text
docs/tickets/
├── .queue.lock                       # Lockfile held during execution
├── gotchas.md                        # Global Gotchas accumulated across runs
└── 01-doctor-and-git-ops/            # Grouped by functional spec
    ├── T001-project-packaging.md     # Active pending ticket
    ├── T002-pre-push-hook.md         # Active pending ticket
    └── completed/                    # Verified & committed tickets
        └── T000-setup.md
```

### Ticket File Format

Each ticket defines requirements, acceptance criteria, and gotchas:

```markdown
# T001 — Fix admin loading state
Status: pending
Spec: docs/specs/01-admin-panel.md

### Requirements
- Add loading state to verified datasets table.
- Prevent duplicate loading indicators on refetch.
- Preserve existing pagination and sorting behavior.

### Acceptance Criteria
- Loading spinner displays during async fetch.
- No layout shift or double scrollbars.
- Existing CRUD operations remain green.

### Gotchas
- Table component uses virtualized rendering; loading state must wrap the table body.
```

### Queue Dynamics & Lockfile

- **Alphanumeric Ordering:** Tickets are evaluated in alphanumeric order (`T001`, `T002`, ...).
- **Lockfile & Live Editing:** When running, the Runner holds `.queue.lock`. Pressing `[p]` (Pause) releases the lock, allowing you to edit requirements, add new tickets, or reprioritize the queue before resuming.
- **Completed Relocation:** When a ticket passes Gatekeeper checks and is committed, the Runner updates the ticket header (`Status: completed`, `Commit: <sha>`, `Completed: <timestamp>`) and moves the file to `docs/tickets/<spec-slug>/completed/`.

---

## Configuration Reference (`config.yaml`)

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `project.name` | `string` | `"ticket-runner"` | Identifier for the project. |
| `project.branch` | `string` | `"agent/ticket-runner"` | Isolated working branch for agent operations. |
| `project.base_branch` | `string` | `"main"` | Base branch from which the agent branch is created. |
| `worker.execution_skill` | `string` | `".agents/skills/implement/SKILL.md"` | Path to the worker implementation discipline skill. |
| `verification.test_cmd` | `string` | `"pytest"` | Independent verification test command executed by Gatekeeper. |
| `verification.build_cmd` | `string` | `""` | Optional build command executed before tests. |
| `verification.max_retries` | `int` | `3` | Maximum verification retries before tripping the Circuit Breaker. |
| `verification.timeout_seconds`| `int` | `300` | Timeout for test and build command executions. |
| `tokens.warn` | `int` | `120000` | Token threshold for warning notification. |
| `tokens.handoff` | `int` | `135000` | Token threshold for checkpointing and context handoff. |
| `tokens.ceiling` | `int` | `150000` | Hard token limit forcing immediate session rollover. |
| `presence.default_mode` | `string` | `"nearby"` | Default mode (`nearby` or `away`). |
| `presence.idle_escalation_minutes` | `int` | `3` | Minutes of idle inactivity before prompt escalates to Discord. |
| `discord.enabled` | `bool` | `true` | Enable or disable Discord bot notifications. |
| `discord.token_env` | `string` | `"DISCORD_BOT_TOKEN"` | Name of environment variable holding the Discord bot token. |
| `discord.channel_id` | `string` | `""` | Discord channel ID where ticket threads are posted. |
| `lifecycle.queue_completion` | `string` | `"standby"` | Behavior when queue empties (`standby` to watch for new tickets, or `terminate` to exit). |
| `git.auto_push` | `bool` | `false` | Always `false`. Never push automated work upstream. |
| `git.commit_prefix` | `string` | `"feat"` | Commit message convention prefix (e.g. `feat(scope): Title`). |
| `git.enforce_pre_push_hook` | `bool` | `true` | Ensure `.git/hooks/pre-push` guardrail is installed. |

---

## Project Documentation & Specifications

For deeper architectural and design details, consult the following documentation:

- [ARCHITECTURE.md](ARCHITECTURE.md) — Concentric Clean Architecture layers, ports, adapters, and module responsibilities.
- [ticket-runner-plan.md](ticket-runner-plan.md) — Comprehensive design specification and requirements.
- [CONTEXT.md](CONTEXT.md) — Domain vocabulary, concepts, and canonical terminology.
- [AGENTS.md](AGENTS.md) — Operating rules, invariants, and agent pair-programming instructions.
- [docs/specs/](docs/specs/) — Functional specifications covering Doctor & Git Ops, Queue & Tickets, Worker Orchestration, Signal Protocols, Presence & Discord, and State Persistence & UI.
- [docs/adr/](docs/adr/) — Architectural Decision Records.
