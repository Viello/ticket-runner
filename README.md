# Ticket Runner

An external, multi-agent Python orchestrator that coordinates AI coding agents (OpenCode, Antigravity CLI) to execute sequential development tickets autonomously with strict gatekeeping, token-preserving verification, context handoffs, and remote Discord/CLI interaction.

---

## Table of Contents

- [Overview](#overview)
- [Triad Ecosystem Architecture](#triad-ecosystem-architecture)
- [8-Stage Development Workflow](#8-stage-development-workflow)
- [Architectural Roadmap](#architectural-roadmap)
- [Standalone LLM Config Prompt](#standalone-llm-config-prompt)
- [Key Features](#key-features)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [How to Use](#how-to-use)
  - [CLI Commands & Reference](#cli-commands--reference)
  - [Exit Codes](#exit-codes)
  - [Terminal UI & Hotkeys](#terminal-ui--hotkeys)
  - [Presence Modes: Nearby vs. Away](#presence-modes-nearby-vs-away)
- [How It Works](#how-it-works)
  - [Execution State Machine](#execution-state-machine)
  - [Pre-Flight Checks (Doctor)](#pre-flight-checks-doctor)
  - [Gatekeeper & Circuit Breaker](#gatekeeper--circuit-breaker)
  - [Context Handoffs & Token Budgets](#context-handoffs--token-budgets)
  - [Token-Preserving Verification Guardrails](#token-preserving-verification-guardrails)
  - [Dual-Mode Human-in-the-Loop Approval Gate](#dual-mode-human-in-the-loop-approval-gate)
  - [Spec Context Excerpt Injection](#spec-context-excerpt-injection)
  - [Git Safety & Push Guardrails](#git-safety--push-guardrails)
- [Ticket Queue Workflow](#ticket-queue-workflow)
  - [Ticket File Format](#ticket-file-format)
  - [Queue Dynamics & Lockfile](#queue-dynamics--lockfile)
  - [Spec-Closing Alignment Tickets](#spec-closing-alignment-tickets)
- [Configuration Reference](#configuration-reference)
  - [Two-Tier Configuration System](#two-tier-configuration-system)
  - [Global Configuration (~/.ticket-runner/config.yaml)](#global-configuration-ticket-runnerconfigyaml)
  - [Project Overlay Configuration (ticket-runner.yaml)](#project-overlay-configuration-ticket-runneryaml)
- [Project Documentation & Specifications](#project-documentation--specifications)

---

## Overview

Large language model coding agents are powerful at implementing scoped coding tasks, but left unconstrained across long runs they hallucinate completion, exhaust token context windows, cascade unverified changes, or push broken code upstream.

**Ticket Runner** solves this by acting as an external, multi-agent orchestrator:
1. **Target Project Decoupling:** Operates externally against any codebase via `--project-dir <path>`, leaving target repositories clean.
2. **One Ticket at a Time:** Executes work sequentially from an ordered queue under `docs/tickets/<spec-slug>/`.
3. **Independent Verification (Gatekeeper):** Never trusts agent self-reports; automatically executes configured test suites, builds, and behavioral verification harnesses before accepting work.
4. **Token-Preserving Guardrails:** Keeps heavy browser/CLI traces out of LLM prompts; persists full evidence to `.agent/evidence/<ticket_id>/` and feeds back only bounded triage excerpts (≤ 30 lines / 1,000 characters).
5. **Context Preservation:** Monitors token consumption in real time, triggering structured context handoffs to fresh sessions before context degradation occurs.
6. **Dual-Mode Presence:** Displays an interactive Rich terminal dashboard while you are at your desk (**Nearby Mode**), and escalates unanswered prompts to **Discord** threads when you step away (**Away Mode**).
7. **Human-in-the-Loop Approval:** In human gate mode, verification halts after green checks to present an Evidence Card via the active presence channel; commits strictly require explicit human sign-off.
8. **Git Guardrails:** Works strictly on a dedicated `agent/ticket-runner` branch with an installed pre-push hook that prevents automated work from pushing upstream.

---

## Triad Ecosystem Architecture

Ticket Runner operates within a decoupled three-repository ecosystem that separates reusable agent capabilities, the orchestration engine, and target application codebases:

```text
┌─────────────────────────────────────────────────────────┐
│                   Viello/agent-skills                   │
│               (Reusable Skills Catalog)                 │
│  - Reusable agent skills: implement, code-review, etc.  │
│  - Meta-skills: verify-<app> scaffolding & maintenance  │
└────────────────────────────┬────────────────────────────┘
                             │ ticket-runner skills sync / init
                             ▼
┌──────────────────────────────────────────┐             invokes             ┌──────────────────────────────────────────┐
│              Target Project              │ ◄────────────────────────────── │           Viello/ticket-runner           │
│          (--project-dir <path>)          │       orchestrates queue        │       (External Multi-Agent Runner)      │
│  - Target codebase, tests, & build files │                                 │  - CLI: start, doctor, init, skills sync │
│  - ticket-runner.yaml (overlay config)   │                                 │  - Clean Architecture runtime engine     │
│  - docs/tickets/ & docs/specs/           │                                 │  - ~/.ticket-runner/config.yaml (global) │
│  - .agent/ (runtime signals & evidence)  │                                 │  - AgentWorker port: OpenCode, AGY CLI   │
│  - .agents/skills/ (project skills)      │                                 │  - Dual presence: Rich TUI & Discord Bot │
└──────────────────────────────────────────┘                                 └──────────────────────────────────────────┘
```

### The Three Decoupled Pillars

1. **Reusable Skills Catalog (`Viello/agent-skills`)**:
   - Centralized repository of reusable, agent-agnostic development discipline handbooks (`implement`, `code-review`, `security-review`, `diagnosing-bugs`, `to-tickets`, `grilling`).
   - Distributable to any target project via `ticket-runner skills sync`.
2. **Standalone Orchestrator (`Viello/ticket-runner`)**:
   - External CLI binary installed globally or run from its own repository.
   - Houses the Clean Architecture core (domain, interactors, ports, and adapters).
   - Reads global machine preferences from `~/.ticket-runner/config.yaml` (Discord tokens, default models, ceiling limits).
   - Coordinates multi-agent providers (OpenCode, Antigravity CLI) through the unified `AgentWorker` port.
3. **Target Project (`<project-dir>`)**:
   - The application repository under active development.
   - Contains source code, test suites, and project overlay configuration (`ticket-runner.yaml`).
   - Houses the ticket queue (`docs/tickets/`), specifications (`docs/specs/`), project skills (`.agents/skills/`), and runtime state (`.agent/`).

---

## 8-Stage Development Workflow

Ticket Runner organizes software engineering into an 8-stage quality pipeline moving across planning, specification, execution, and verification:

```text
┌──────────────────────────────────┐
│  1. Planning & Alignment         │  Stress-test ideas & plans (/grill-me, /prototype)
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│  2. Formal Specification         │  Synthesize requirements into docs/specs/<spec-slug>.md (/to-spec)
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│  3. Ticket Decomposition         │  Decompose spec into queue: docs/tickets/<spec-slug>/T<NNN>-<slug>.md (/to-tickets)
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│  4. Implementation (TDD)         │  AgentWorker executes ticket test-first via worker.execution_skill
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│  5. Pre-Signal Review            │  Two-axis review (/code-review: coding standards & originating spec)
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│  6. Security Review              │  Security posture check (/security-review) when Security: required
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│  7. Gatekeeper Verification      │  Independent test_cmd, build_cmd, & Verification Harness
└─────────────────┬────────────────┘  Full evidence to .agent/evidence/ (bounded 30-line triage on fail)
                  ▼
┌──────────────────────────────────┐
│  8. Human Gate & Completion      │  Evidence Card on TUI/Discord -> Human Approval -> Atomic Commit
└──────────────────────────────────┘
```

### Stage Details

1. **Planning & Alignment**: Stress-test architectural proposals, API designs, and state models with `/grill-me` or interactive interview skills. Throwaway prototypes are explored using `/prototype` before committing to code.
2. **Formal Specification**: Synthesize aligned requirements into a structured specification file under `docs/specs/<spec-slug>.md` using `/to-spec`, defining the problem statement, architectural boundaries, and target solution.
3. **Ticket Decomposition & Queueing**: Decompose the specification into discrete, testable tickets under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` using `/to-tickets`. Every ticket defines requirements, acceptance criteria, smoke scenarios, and gotchas. Every queue concludes with a mandatory spec-closing alignment ticket.
4. **Implementation (TDD)**: The Runner launches an `AgentWorker` (OpenCode or Antigravity CLI) guided by `worker.execution_skill` (`.agents/skills/implement/SKILL.md`). The Worker implements the active ticket slice test-first across red-green cycles, but never commits directly.
5. **Pre-Signal Review**: Before signaling completion, the Worker conducts a two-axis review using `/code-review` to verify that code adheres to repository standards and accurately delivers the originating spec requirements.
6. **Security Review**: If flagged in ticket requirements or frontmatter (`Security: required`), the Worker invokes `/security-review` before signaling readiness to catch OWASP vulnerabilities, unsafe data handling, or credential exposure.
7. **Gatekeeper Verification**: Gatekeeper runs independent test and build commands, plus behavioral verification harnesses (Playwright, PTY CLI, HTTP). Full logs and media persist out-of-band to `.agent/evidence/<ticket_id>/`. On failure, the Runner feeds back a strictly bounded triage excerpt (≤ 30 lines / 1,000 characters) to preserve the model's context.
8. **Human Gate & Completion**: In Human-in-the-Loop mode, Gatekeeper halts after green checks to present an **Evidence Card** via the active presence channel (Rich terminal prompt in Nearby mode; Discord Status Card with `/approve` in Away mode). Upon human sign-off, Gatekeeper authors exactly one atomic conventional commit, relocates the ticket to `completed/`, and logs smoke scenarios to `.agent/smoke_log_<spec-slug>.md`.

---

## Architectural Roadmap

Ticket Runner's evolution from a project-local script into an enterprise-grade, multi-agent external framework follows four sequential specifications:

| Spec | Title | Status | Primary Focus |
| :--- | :--- | :--- | :--- |
| **Spec 10b** | **Living Documentation & Roadmap** | Completed | Reconcile root living documents (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`, `README.md`), lock in domain glossary, establish external path invariants, and define the roadmap. |
| **Spec 11** | **Decoupled Project Root & Multi-Agent** | Completed | Introduce `--project-dir <path>` CLI plumbing, abstract `AgentWorker` port (`runner/ports/agent_worker.py`), and multi-agent adapters for OpenCode and Antigravity CLI (`agy`). |
| **Spec 12** | **Project Scaffolding & Skills Distribution** | Planned | Implement two-tier configuration merging (`~/.ticket-runner/config.yaml` + `ticket-runner.yaml`), `ticket-runner init` heuristics, `ticket-runner init --ai-prompt`, and `ticket-runner skills sync`. |
| **Spec 13** | **Token-Guarded Verification & Human Gate** | Planned | Behavioral verification harness contracts (`verify-<app>`), out-of-band evidence capture, token-preserving triage extractor (`evidence_triage.py`), and dual-mode Evidence Card human approval gate. |

### Specification Highlights

- **Spec 10b (Living Documentation & Roadmap)**:
  - Establishes canonical domain vocabulary in [CONTEXT.md](CONTEXT.md) and strict synonym prohibitions.
  - Updates [ARCHITECTURE.md](ARCHITECTURE.md) to document Clean Architecture layers, ports, adapters, and verification subsystem layout.
  - Codifies external path resolution, token-budgeted verification guardrails, and human approval gates in [AGENTS.md](AGENTS.md).
- **Spec 11 (Decoupled Project Root & Multi-Agent Worker Port)**:
  - Adds `--project-dir <path>` (defaulting to `Path.cwd()`), allowing the runner to execute against any external repository.
  - Decouples `WorkerSupervisor` from OpenCode via the abstract `AgentWorker` protocol.
  - Implements concrete adapters for `OpenCodeWorker` and `AntigravityWorker`.
- **Spec 12 (Project Scaffolding, LLM-Friendly Config & Skills Distribution)**:
  - Scaffolds new target projects in seconds via interactive `ticket-runner init`.
  - Distributes and updates canonical agent discipline skills from `Viello/agent-skills` via `ticket-runner skills sync`.
  - Provides a standardized LLM Config Prompt (`ticket-runner init --ai-prompt`) allowing coding assistants to configure projects autonomously.
- **Spec 13 (Token-Guarded Verification Subsystem & Human-in-the-Loop Gate)**:
  - Provides `create-verification-skill` scaffolding for Playwright, CLI PTYs, and HTTP APIs with a 5-step lifecycle (`Launch` $\rightarrow$ `Doctor` $\rightarrow$ `Drive` $\rightarrow$ `Evidence` $\rightarrow$ `Cleanup`).
  - Guards LLM token contexts by enforcing out-of-band execution and bounded triage truncation (≤ 30 lines / 1,000 characters).
  - Unifies human sign-off across Terminal and Discord with interactive Evidence Cards before committing.

---

## Standalone LLM Config Prompt

Copy and paste the prompt below into any AI coding assistant (Cursor, OpenCode, Antigravity, Claude Code, ChatGPT) inside your project repository to automatically generate a tailored `ticket-runner.yaml` configuration file:

````markdown
# Task: Configure Ticket Runner for this Repository

You are an expert software engineer and DevOps architect. Inspect this repository and generate a valid, minimal `ticket-runner.yaml` configuration file at the repository root.

## Instructions
1. Inspect the repository root and project files to identify:
   - Primary language and runtime framework.
   - Package manager / build tool (`npm`, `pnpm`, `yarn`, `bun`, `poetry`, `pip`, `cargo`, `go`, etc.).
   - Test runner command (e.g. `pytest`, `npm test`, `cargo test`, `go test ./...`). Must run non-interactively.
   - Build or typecheck command if applicable (e.g. `npm run build`, `tsc --noEmit`, `cargo check`), or empty string `""` if not needed.
   - Default git base branch (`main` or `master`).
2. Write a minimal `ticket-runner.yaml` file to the root of this project following the schema below.

## Configuration Schema (`ticket-runner.yaml`)

```yaml
# Target Project Overlay Configuration
project:
  name: "<project-name>"               # Project identifier
  base_branch: "main"                  # Target base branch (e.g., main or master)
  branch: "agent/ticket-runner"        # Isolated branch for agent work

worker:
  provider: "opencode"                 # Agent backend: "opencode" or "antigravity"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "<non-interactive test command>"   # Executed by Gatekeeper (e.g., "pytest", "npm test")
  build_cmd: "<build or typecheck command>"    # Optional build check (or "" if none)
  max_attempts: 3                              # Attempts before tripping circuit breaker
  timeout_seconds: 300                         # Test timeout in seconds

lifecycle:
  mode: "human"                        # "human" (requires approval to commit) or "autonomous"
  queue_completion: "standby"          # "standby" (wait for tickets) or "terminate" (exit when empty)
```

## Stack-Specific Examples

### Node.js / TypeScript (npm / pnpm / yarn / bun)
```yaml
project:
  name: "my-web-app"
  base_branch: "main"
  branch: "agent/ticket-runner"

worker:
  provider: "opencode"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pnpm test"
  build_cmd: "pnpm run build"
  max_attempts: 3
  timeout_seconds: 300

lifecycle:
  mode: "human"
  queue_completion: "standby"
```

### Python (pytest & ruff)
```yaml
project:
  name: "my-python-service"
  base_branch: "main"
  branch: "agent/ticket-runner"

worker:
  provider: "opencode"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pytest"
  build_cmd: "python -m ruff check ."
  max_attempts: 3
  timeout_seconds: 300

lifecycle:
  mode: "human"
  queue_completion: "standby"
```

### Rust (Cargo)
```yaml
project:
  name: "my-rust-crate"
  base_branch: "main"
  branch: "agent/ticket-runner"

worker:
  provider: "opencode"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "cargo test"
  build_cmd: "cargo check"
  max_attempts: 3
  timeout_seconds: 300

lifecycle:
  mode: "human"
  queue_completion: "standby"
```

### Go
```yaml
project:
  name: "my-go-api"
  base_branch: "main"
  branch: "agent/ticket-runner"

worker:
  provider: "opencode"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "go test ./..."
  build_cmd: "go vet ./..."
  max_attempts: 3
  timeout_seconds: 300

lifecycle:
  mode: "human"
  queue_completion: "standby"
```

### Monorepo (pnpm / Turborepo)
```yaml
project:
  name: "my-monorepo"
  base_branch: "main"
  branch: "agent/ticket-runner"

worker:
  provider: "opencode"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pnpm turbo run test"
  build_cmd: "pnpm turbo run build"
  max_attempts: 3
  timeout_seconds: 600

lifecycle:
  mode: "human"
  queue_completion: "standby"
```
````

---

## Key Features

- **Decoupled Multi-Agent Support:** Orchestrates OpenCode and Antigravity CLI via the clean `AgentWorker` port abstraction.
- **Sequential Queue Loop:** Evaluates tickets one-by-one from `docs/tickets/<spec-slug>/`; relocates verified tickets to `completed/` upon Gatekeeper commit.
- **Pre-Flight Doctor:** Validates agent CLI availability, git tree cleanliness, configuration syntax, and hook installation before any code runs.
- **Token-Preserving Verification:** Persists heavy behavioral traces, logs, and screenshots out-of-band in `.agent/evidence/<ticket_id>/`, passing only bounded triage excerpts (≤ 30 lines / 1,000 characters) to LLMs.
- **Dual Presence (Nearby vs. Away):** Interactive split-screen Rich terminal dashboard when you are at your desk; escalates prompts to ticket-specific Discord threads when you are away.
- **Circuit Breaker:** Halts execution when verification attempts exceed the configured threshold, escalating to an operator decision (`[R]etry`, `[S]kip`, `[A]bort`).
- **Human-in-the-Loop Sign-Off:** Halts after green checks to present an Evidence Card via Terminal or Discord; commits strictly require explicit human approval.
- **Clean Architecture:** Strict inward dependency rule, zero I/O in the domain layer, abstract ports, and comprehensive test doubles.

---

## Prerequisites

- **Operating System:** Windows 10/11 (PowerShell environment) or Linux/macOS with a POSIX-compliant shell.
- **Python:** Version **3.11** or higher.
- **Agent CLI:** OpenCode CLI (`opencode`) or Antigravity CLI (`agy`) installed and authenticated in system PATH.
- **Git:** Git 2.30+ installed.
- **Discord Account (Optional):** Required only if enabling remote Away Mode notifications and slash command interaction.

---

## Installation & Setup

### 1. Install Ticket Runner

Clone the standalone orchestrator repository:
```powershell
git clone https://github.com/Viello/ticket-runner.git
cd ticket-runner
```

### 2. Create and Activate Virtual Environment
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

### 4. Create Global Configuration
Create your machine-wide configuration under `~/.ticket-runner/config.yaml`:
```powershell
mkdir ~/.ticket-runner
Copy-Item config.example.yaml ~/.ticket-runner/config.yaml
```

### 5. Set Environment Variables (If Using Discord)
If Discord integration is enabled, export your bot token:
```powershell
# PowerShell
$env:DISCORD_BOT_TOKEN = "your_actual_discord_bot_token"

# Bash / Zsh
export DISCORD_BOT_TOKEN="your_actual_discord_bot_token"
```

---

## How to Use

### CLI Commands & Reference

Ticket Runner provides an entry-point CLI (`ticket-runner` or `python ticket_runner.py`). All commands accept the `--project-dir <path>` argument to target any external codebase:

```powershell
# Syntax:
ticket-runner [--project-dir <path>] <command> [options]
# Alternatively, --project-dir can be specified after the subcommand:
ticket-runner <command> [--project-dir <path>] [options]
```

#### Core Subcommands

```powershell
# 1. Run pre-flight health checks on environment, git state, and agent binaries
ticket-runner --project-dir /path/to/my-app doctor
ticket-runner doctor --local-only   # Runs against current directory, terminal-only

# 2. Start the runner and begin processing the queue
ticket-runner --project-dir /path/to/my-app start
ticket-runner start --model qwen/qwen-plus  # Specific model override

# 3. Initialize a new target project (scaffolds directories, generates ticket-runner.yaml, syncs skills)
ticket-runner --project-dir /path/to/my-app init

# 4. Generate the standalone LLM configuration prompt for coding assistants
ticket-runner init --ai-prompt

# 5. Sync or update canonical agent skills from Viello/agent-skills
ticket-runner --project-dir /path/to/my-app skills sync

# 6. Inspect active ticket, token usage, and presence status
ticket-runner --project-dir /path/to/my-app status

# 7. Pause the active runner and release the queue lock for edits
ticket-runner --project-dir /path/to/my-app pause
```

#### Directory Resolution & Path Validation

| Argument | Description | Default Behavior |
| :--- | :--- | :--- |
| `--project-dir <path>` | Absolute or relative path to the target project repository. | If omitted, defaults strictly to current working directory (`Path.cwd().resolve()`). |
| `--config <path>` | Path to configuration file. | If relative and `--project-dir` is provided, resolved relative to target project root. |
| `--local-only` | Bypass Discord connectivity checks and notifications. | Disabled by default; notifications route to Discord in Away mode. |

> [!IMPORTANT]
> **Defensive Path Validation:** `--project-dir` is rigorously validated before running commands. Non-existent paths or paths pointing to regular files exit immediately with exit code `1` and an actionable error message. Target directories must be initialized Git repositories (`git rev-parse --is-inside-work-tree`).

### Exit Codes

Ticket Runner adheres to a strict exit code contract for operators, CI pipelines, and supervisors:

| Exit Code | Meaning | Description |
| :--- | :--- | :--- |
| `0` | **Clean Termination** | Queue drained cleanly under `terminate` policy, or standby watch loop exited via cooperative stop. |
| `1` | **Runtime Error** | Pre-flight Doctor check failure, misconfiguration, or unhandled runtime pipeline error. |
| `2` | **Operator Abort** | Operator selected abort (`UserAbortError`) at circuit-breaker escalation prompt. |
| `130` | **Graceful SIGINT** | Graceful shutdown via Ctrl+C (single cooperative stop or forced second press). |

### Terminal UI & Hotkeys

In **Nearby Mode**, Ticket Runner displays a rich split-view terminal dashboard:

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
- `[p]` — **Pause**: Releases `docs/tickets/.queue.lock` so you can add, edit, or reorder tickets.
- `[m]` — **Toggle Mode**: Manually switches between `Nearby` and `Away` presence modes.
- `[q]` — **Quit**: Gracefully terminates child worker processes, persists state to `.agent/state.json`, and shuts down.

### Presence Modes: Nearby vs. Away

- **Nearby Mode (Default):** Silences remote Discord pings while you are active at the terminal. Prompts and questions appear directly in your local terminal.
- **Away Mode:** Activated manually via `[m]` or automatically after 3 minutes of idle inactivity on an unanswered prompt. In Away mode, questions and milestone notifications route directly to ticket-specific Discord threads.

---

## How It Works

### Execution State Machine

Only **one** ticket executes at a time. The loop follows strict transitions:

```text
       [START]
          ↓
       DOCTOR (Pre-flight checks: git, CLI binaries, config, hooks)
          ↓
       PENDING (Select top alphanumeric pending ticket)
          ↓
    WORKING & PLANNING (AgentWorker execution)
       ├── Token usage >= 135k → Checkpoint handoff → Resume in fresh session
       ├── Worker needs input  → Terminal prompt / Discord thread
       └── Pause requested     → Release lock & wait
          ↓
    READY SIGNAL (.agent/signals/{ticket_id}_ready.json)
          ↓
    GATEKEEPER (Independent test_cmd, build_cmd, & Verification Harness)
       ├── PASS → Human Gate (Evidence Card on TUI/Discord)
       │           ├── APPROVE → Commit (<type>(<scope>): <Title>) → Archive ticket → Next ticket
       │           └── REJECT  → Feed rejection notes to Worker → Retry WORKING
       └── FAIL (Attempts < verification.max_attempts) → Feed bounded triage excerpt → Retry WORKING
                (Attempts exhausted) → CIRCUIT BREAKER TRIPPED → Escalate ([R]etry/[S]kip/[A]bort)
```

### Pre-Flight Checks (Doctor)

Before any ticket execution begins, `Doctor` inspects the environment, workspace, and configuration to catch missing tools, unconfigured dependencies, and invalid states early:

1. **Target Project Directory & Git Repository**: Validates that `--project-dir` (or `CWD`) exists, is an accessible directory, and is a valid Git worktree (verified via `git rev-parse --is-inside-work-tree`).
2. **Worker Provider CLI Binary**: Inspects system PATH for the executable corresponding to the configured `worker.provider`:
   - `opencode`: Verifies `opencode` CLI binary exists in PATH and executes `opencode --version`.
   - `antigravity`: Verifies `agy` CLI binary exists in PATH.
3. **Branch Isolation & Clean Working Tree**: Verifies that the repository working tree has zero uncommitted changes and is checked out to the designated isolation branch (`agent/ticket-runner`).
4. **Ticket Queue Validation**: Verifies `docs/tickets/` exists and contains at least one pending ticket specification.
5. **Configuration Schema & Model Definitions**: Validates `config.yaml` against schema constraints and confirms at least one selectable model is configured under `model.models`.
6. **Session Terminal Host**: Verifies configured terminal binary on PATH or prompts for interactive host selection (`wt.exe`, `pwsh.exe`, `powershell.exe`, `cmd.exe`).
7. **Verification Commands**: Resolves the leading executable of `verification.test_cmd` and `verification.build_cmd` against PATH.
8. **Pre-Push Hook Guardrail**: Verifies `.git/hooks/pre-push` is installed with blocking signature to prevent upstream pushes.
9. **Operating Rules & Skills**: Confirms `AGENTS.md` and required skill definitions (`implement`, `code-review`, `diagnosing-bugs`) exist on disk.
10. **Discord Connectivity & Permissions**: Validates bot credentials and channel permissions unless running with `--local-only`.

### Gatekeeper & Circuit Breaker

- **Independent Verification:** The Worker cannot mark tickets completed. Only Gatekeeper accepts work by running configured verification commands and harnesses.
- **Circuit Breaker:** When verification attempts exhaust `verification.max_attempts`, the Circuit Breaker trips, halting the loop and escalating via Terminal or Discord:
  - `[R]etry [hint]`: Restore attempt budget and resume Worker with optional operator guidance.
  - `[S]kip`: Discard uncommitted edits (behind confirmation) and advance to the next ticket.
  - `[A]bort`: Stop the runner while preserving the working tree for manual debugging.

### Context Handoffs & Token Budgets

To eliminate model hallucinations from context saturation, Ticket Runner monitors token telemetry:
- **120,000 tokens:** Warning emitted to dashboard/Discord.
- **135,000 tokens:** Automated Context Handoff triggered. The Worker executes `.agents/skills/handoff/SKILL.md` to persist progress to `.agent/checkpoints/{ticket_id}/handoff.md`. The runner resumes in a fresh session with the checkpoint as context.
- **150,000 tokens:** Hard ceiling forcing immediate Context Handoff.

### Token-Preserving Verification Guardrails

- **Out-of-band Execution:** Heavy verification harnesses (Playwright browser runners, CLI PTY drivers, load tests) execute outside the LLM context.
- **Disk Persistence:** Full logs, traces, screenshots, and DOM snapshots are saved strictly to `<project-dir>/.agent/evidence/<ticket_id>/`.
- **Bounded Triage Excerpts:** On verification failure, `evidence_triage.py` extracts a strictly bounded excerpt (maximum **30 lines / 1,000 characters**) covering the failing test and root cause. Raw browser transcripts are never injected into the LLM context.

### Dual-Mode Human-in-the-Loop Approval Gate

In Human-in-the-Loop mode (`lifecycle.mode: "human"`):
- Gatekeeper halts after green verification checks and formats an **Evidence Card** summarizing status, duration, artifact links, and human smoke scenarios.
- In **Nearby Mode**, an interactive terminal prompt displays the card with actions: `[y]` approve & commit, `[n]` reject & retry, `[d]` launch diagnostic session.
- In **Away Mode**, the card posts to the ticket's Discord thread, awaiting `/approve` or `/reject` slash commands.
- Commits are strictly blocked until human approval is confirmed.

### Spec Context Excerpt Injection

- Each ticket is linked to its parent spec via `Spec:` frontmatter or inferred from `docs/specs/<spec-slug>.md`.
- The Runner extracts `## Problem Statement` and `## Solution` (~300 tokens) and inlines them into the Worker's initial prompt as a **Spec Excerpt**.
- The prompt provides file path links so the Worker can read deeper requirements on demand without upfront context bloat.

### Git Safety & Push Guardrails

- All automated work occurs on `agent/ticket-runner`.
- Gatekeeper authors atomic commits following conventional commit syntax (`<type>(<scope>): <Title>`) with imperative bulleted changes and no ticket numbers.
- An installed pre-push hook (`.git/hooks/pre-push`) rejects all pushes from the agent branch to remote origins, guaranteeing zero unintended upstream pushes.

---

## Ticket Queue Workflow

Tickets live under `docs/tickets/<spec-slug>/` as individual markdown files:

```text
docs/tickets/
├── .queue.lock                       # Sentinel file lock held during execution
├── gotchas.md                        # Global operational lessons learned
└── 10b-living-documentation-and-roadmap/
    ├── T089-update-architecture.md   # Completed tickets relocated upon commit
    ├── T092-update-readme.md         # Active pending ticket
    └── completed/                    # Verified & committed archive
        └── T089-update-architecture.md
```

### Ticket File Format

Each ticket defines requirements, acceptance criteria, smoke scenarios, and gotchas:

```markdown
# T001 — Fix admin loading state
Status: pending
Spec: docs/specs/01-admin-panel.md
Reasoning: medium

### Requirements
- Add loading state to verified datasets table.
- Prevent duplicate loading indicators on refetch.
- Preserve existing pagination and sorting behavior.

### Acceptance Criteria
- Loading spinner displays during async fetch.
- No layout shift or double scrollbars.
- Existing CRUD operations remain green.

### Smoke Scenarios
**Scenario: Verify Admin Table Loading State**
- Setup: None (runs from repo root).
- Why: Ensure users see an unambiguous loading indicator during data retrieval.
- Steps:
  1. Open the admin datasets page.
  2. Trigger table sort refetch.
- Expected: Spinner displays immediately and disappears once rows render.

### Gotchas
- Table component uses virtualized rendering; loading state must wrap the table body.
```

### Queue Dynamics & Lockfile

- **Alphanumeric Ordering:** Tickets are evaluated in alphanumeric order (`T001`, `T002`, ...).
- **Lockfile & Live Editing:** When running, the Runner holds `.queue.lock`. Pressing `[p]` (Pause) releases the lock, allowing you to edit requirements, add tickets, or reprioritize the queue before resuming.
- **Archive Relocation:** Upon Gatekeeper pass and commit, the Runner updates ticket frontmatter (`Status: completed`, `Completed: <timestamp>`) and moves the file to `docs/tickets/<spec-slug>/completed/`.

### Spec-Closing Alignment Tickets

Every ticket queue decomposed under `docs/tickets/<spec-slug>/` must conclude with a final alignment ticket. This ticket audits the actual implementation against the originating specification and updates root living documents (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`, `README.md`) to reconcile any architectural divergence before the spec is archived.

---

## Configuration Reference

### Two-Tier Configuration System

Ticket Runner separates global machine configuration from project-specific overrides:
- **Global User Configuration (`~/.ticket-runner/config.yaml`)**: Stores machine-wide credentials, Discord bot tokens, default LLM models, and token budget defaults.
- **Project Overlay Configuration (`<project-dir>/ticket-runner.yaml`)**: Stores project-specific test commands, build commands, branch names, and agent provider selections.

### Global Configuration (`~/.ticket-runner/config.yaml`)

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `tokens.warn` | `int` | `120000` | Token threshold for warning notification. |
| `tokens.handoff` | `int` | `135000` | Token threshold for checkpointing and context handoff. |
| `tokens.ceiling` | `int` | `150000` | Hard token limit forcing immediate Context Handoff. |
| `presence.default_mode` | `string` | `"nearby"` | Default operational mode (`nearby` or `away`). |
| `presence.idle_escalation_minutes` | `int` | `3` | Inactivity minutes before prompts escalate to Discord. |
| `discord.enabled` | `bool` | `true` | Enable or disable Discord bot notifications. |
| `discord.token_env` | `string` | `"DISCORD_BOT_TOKEN"` | Environment variable holding Discord bot token. |
| `discord.guild_id` | `string` | `""` | Target Discord server snowflake ID. |
| `discord.channel_id` | `string` | `""` | Target Discord channel snowflake ID for threads. |
| `discord.notify_user_id` | `string` | `""` | Optional Discord user snowflake ID to @mention on alerts. |
| `git.auto_push` | `bool` | `false` | Always `false`. Never push automated work upstream. |
| `git.enforce_pre_push_hook` | `bool` | `true` | Ensure `.git/hooks/pre-push` guardrail is installed. |

### Project Overlay Configuration (`ticket-runner.yaml`)

| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `project.name` | `string` | `"my-project"` | Identifier for the target project. |
| `project.base_branch` | `string` | `"main"` | Base branch from which the agent branch is branched. |
| `project.branch` | `string` | `"agent/ticket-runner"` | Isolated working branch for agent operations. |
| `worker.provider` | `string` | `"opencode"` | Agent backend provider (`opencode` or `antigravity`). |
| `worker.execution_skill` | `string` | `".agents/skills/implement/SKILL.md"` | Path to the worker implementation discipline skill. |
| `verification.test_cmd` | `string` | `"pytest"` | Independent verification test command executed by Gatekeeper. |
| `verification.build_cmd` | `string` | `""` | Optional build/typecheck command executed before tests. |
| `verification.max_attempts` | `int` | `3` | Total verification attempts before tripping circuit breaker. |
| `verification.timeout_seconds` | `int` | `300` | Timeout for test and build command executions. |
| `lifecycle.mode` | `string` | `"human"` | `"human"` (requires human approval to commit) or `"autonomous"`. |
| `lifecycle.queue_completion` | `string` | `"standby"` | Behavior when queue empties (`standby` or `terminate`). |

### Worker Configuration

The `worker.provider` setting controls which agent CLI backend is orchestrated by the `AgentWorker` port:

| Provider | CLI Invocation | Description |
| :--- | :--- | :--- |
| `opencode` *(default)* | `opencode run --format json --auto "<prompt>"` | Production default. Drives OpenCode as an external subprocess with JSONL streaming telemetry and session resumption. |
| `antigravity` | `agy run --auto "<prompt>"` | Integrates with Google Antigravity CLI (`agy`) for environments leveraging Antigravity agent workflows. |


---

## Project Documentation & Specifications

For comprehensive architectural specifications and design records, consult:

- [ARCHITECTURE.md](ARCHITECTURE.md) — Concentric Clean Architecture layers, ports, adapters, and module responsibilities.
- [CONTEXT.md](CONTEXT.md) — Canonical domain vocabulary, concepts, and synonym prohibitions.
- [AGENTS.md](AGENTS.md) — Operating rules, invariants, verification guardrails, and pair-programming instructions.
- [docs/specs/](docs/specs/) — Active and planned specifications (Specs 10b, 11, 12, 13).
- [docs/adr/](docs/adr/) — Architectural Decision Records (ADRs 0001 to 0022).
