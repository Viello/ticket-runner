# Architecture & File Structure

Clean Architecture directory layout for Ticket Runner. Source code dependencies point strictly inward:
- **Adapters** $\rightarrow$ **Ports** & **Domain**
- **Application** $\rightarrow$ **Ports** & **Domain**
- **Ports** $\rightarrow$ **Domain**
- **Domain** has zero outward dependencies.

---

## 1. Triad Ecosystem Architecture

Ticket Runner operates within a decoupled three-repository ecosystem:

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

---

## 2. Runtime Separation: Runner vs. Target Project

Ticket Runner runs as an external CLI binary decoupled from the target codebase:

1. **Runner Installation Root (`Viello/ticket-runner`)**:
   - Installed globally or executed from its standalone clone.
   - Houses the CLI entry points, Clean Architecture domain engine, interactors, ports, and adapters.
   - Reads global machine configuration from `~/.ticket-runner/config.yaml` (Discord bot tokens, default model IDs, token ceiling defaults).
2. **Target Project Directory (`<project-dir>`)**:
   - Specified via `--project-dir <path>` (defaults to current working directory `Path.cwd()`).
   - The Runner process sets its working directory (`CWD`) to the Target Project.
   - All runtime state (`.agent/`), ticket queues (`docs/tickets/`), specifications (`docs/specs/`), project skills (`.agents/skills/`), and project overlay configuration (`ticket-runner.yaml`) resolve relative to the Target Project root.

---

## 3. Runner Repository Directory Layout (`ticket-runner/`)

```text
ticket-runner/
├── ticket_runner.py                  # CLI entry point (argparse: start, doctor, init, pause, status, skills)
├── requirements.txt                  # Python dependencies (discord.py, rich, pyyaml, pytest)
├── pyproject.toml                    # Package metadata, Python 3.11+, pytest configuration
│
├── scripts/
│   └── pre-push.sh                   # POSIX shell template for agent/ticket-runner guardrail
│
├── runner/
│   ├── __init__.py
│   ├── main.py                       # Top-level async runner lifecycle coordinator
│   ├── container.py                  # Pure Python Composition Root (wires adapters to interactors)
│   │
│   ├── domain/                       # Pure Domain Entities & Invariants (zero I/O, zero deps)
│   │   ├── __init__.py
│   │   ├── ticket.py                 # Ticket, TicketStatus, requirements, gotchas
│   │   ├── state.py                  # RunnerState, StateStatus, crash recovery state
│   │   ├── signal.py                 # ReadySignal, QuestionSignal, SignalStatus, verification models
│   │   ├── status_event.py           # Domain events for queue and worker state changes
│   │   ├── telemetry.py              # WorkerEvent, TokenUsage, ToolCall, WorkerMessage
│   │   ├── config.py                 # Frozen domain config (merges global config + project overlay)
│   │   ├── runtime_paths.py          # Value object resolving paths in <project-dir> and .agent/
│   │   ├── ring_buffer.py            # Fixed-capacity in-memory telemetry buffer (Spec 10)
│   │   ├── failure_analyser.py       # Pattern-matching failure classifier for test suites (Spec 10)
│   │   └── exceptions.py             # Domain hierarchy rooted at TicketRunnerError
│   │
│   ├── application/                  # Application Use Cases / Interactors
│   │   ├── __init__.py
│   │   ├── doctor.py                 # Pre-flight environment checks & binary verification (opencode/agy)
│   │   ├── queue_orchestrator.py     # Sequential ticket loop (standby vs terminate)
│   │   ├── worker_supervisor.py      # Multi-agent worker lifecycle via AgentWorker port
│   │   ├── handoff_coordinator.py    # Token budget rules (120k warn, 135k handoff, 150k ceiling)
│   │   ├── gatekeeper.py             # Test/build verification, harness driving, & Circuit Breaker
│   │   ├── ticket_processor.py       # Ticket execution seam driving verification loop & outcome mapping
│   │   ├── presence_coordinator.py   # Nearby vs Away mode & 3-min idle escalation timer
│   │   ├── git_operations.py         # Branch isolation, conventional commits, tree resets
│   │   ├── clean_slate.py            # Ephemeral queue clean-slate reset & commit authoring (ADR 0012)
│   │   ├── crash_recovery.py         # Crash recovery coordinator for dirty trees and stalled runs
│   │   ├── model_selection.py        # Model selection, reasoning variant, and fallback policy (ADR 0022)
│   │   ├── prompt_builder.py         # Context excerpt injector & ticket prompt synthesis (ADR 0011)
│   │   ├── state_coordinator.py      # Thread-safe atomic runner state coordinator
│   │   ├── tui_coordinator.py        # Terminal user interface coordinator and screen switching
│   │   ├── hotkey_dispatch.py        # Interactive hotkey handler for TUI (pause, open, abort)
│   │   ├── discord_thread_manager.py # Thread lifecycle coordinator for Discord integration
│   │   ├── evidence_triage.py        # Token-preserving triage extractor (<=30 lines / 1,000 chars)
│   │   └── scaffolding.py            # Project sniffer and config generator for ticket-runner init
│   │
│   ├── ports/                        # Pure Abstract Protocols (Dependency Inversion Seams)
│   │   ├── __init__.py
│   │   ├── agent_worker.py           # Protocol for spawning agents & streaming normalized WorkerEvents
│   │   ├── command_runner.py         # Protocol for CLI execution (streaming stdout & exit codes)
│   │   ├── ticket_repository.py      # Protocol for locked scanning/updating docs/tickets/ queue
│   │   ├── state_store.py            # Protocol for atomic .agent/state.json persistence
│   │   ├── signal_repository.py      # Protocol for watching/writing signals & questions
│   │   ├── discord_gateway.py        # Protocol for Discord thread lifecycle, slash commands & alerts
│   │   ├── discord_logger.py         # Protocol for streaming structured logs to Discord threads
│   │   ├── intervention.py           # Protocol for human operator questions and decisions
│   │   ├── approval_gateway.py       # Protocol for human-in-the-loop verification approval cards
│   │   ├── status_publisher.py       # Protocol for publishing status transitions to listeners
│   │   ├── terminal_display.py       # Protocol for Rich dashboard rendering & hotkey events
│   │   └── config_loader.py          # Protocol for loading and merging two-tier configurations
│   │
│   └── adapters/                     # Concrete Adapters (Outermost Infrastructure Circle)
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── subprocess_runner.py  # Asyncio subprocess implementing CommandRunner
│       │   └── windows_job.py        # Windows Job Object process tree termination wrapper
│       ├── opencode/
│       │   ├── __init__.py
│       │   └── opencode_worker.py    # OpenCode CLI adapter implementing AgentWorker protocol
│       ├── antigravity/
│       │   ├── __init__.py
│       │   └── antigravity_worker.py # Antigravity CLI / SDK adapter implementing AgentWorker protocol
│       ├── git/
│       │   ├── __init__.py
│       │   ├── git_client.py         # Git CLI operations using CommandRunner
│       │   └── pre_push_hook.py      # Installer/guardrail merger reading scripts/pre-push.sh
│       ├── markdown/
│       │   ├── __init__.py
│       │   ├── file_lock.py          # Windows msvcrt sentinel file locking context manager (.queue.lock)
│       │   ├── parser.py             # Frontmatter and markdown parser for ticket files
│       │   ├── spec_parser.py        # Spec excerpt parser for ticket prompt context injection
│       │   ├── serializer.py         # Serializer, status updater, and completed/ archiver
│       │   ├── gotchas_store.py      # Persistent parser and updater for docs/tickets/gotchas.md
│       │   ├── atomic_write.py       # Windows-safe atomic file replace utility
│       │   └── ticket_store.py       # Implements TicketRepository for docs/tickets/ directory
│       ├── filesystem/
│       │   ├── __init__.py
│       │   ├── json_state_store.py   # Implements StateStore via atomic tempfile replacement
│       │   └── signal_watcher.py     # Implements SignalRepository via filesystem polling
│       ├── discord/
│       │   ├── __init__.py
│       │   ├── client.py             # discord.py client lifecycle & event loop
│       │   ├── commands.py           # Slash commands (/mode, /pause, /status, /approve)
│       │   ├── gateway.py            # Implements DiscordGateway
│       │   ├── logger.py             # Implements DiscordLogger with chunking engine
│       │   ├── thread_listener.py    # Watches and routes messages inside ticket threads
│       │   ├── live_check.py         # Connection and guild readiness healthchecker
│       │   └── smoke.py              # Discord adapter smoke test verification utility
│       ├── ui/
│       │   ├── __init__.py
│       │   ├── terminal.py           # Rich Live dashboard & UI renderer implementing TerminalDisplay
│       │   ├── keyboard.py           # Non-blocking msvcrt keyboard reader for Windows
│       │   ├── terminal_detector.py  # Host environment sniffer (Windows Terminal, VS Code, raw conhost)
│       │   ├── terminal_prompts.py   # Human prompt helpers for interactive questions & decisions
│       │   ├── model_prompt.py       # Interactive model selector prompt for terminal UI
│       │   └── tui_launcher.py       # Out-of-band terminal window spawner for worker observation
│       ├── config/
│       │   ├── __init__.py
│       │   └── yaml_config_loader.py # Two-tier YAML loader merging global and project configs
│       └── json_status_publisher.py  # Implements StatusPublisher writing events to disk
│
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Pytest fixtures (temp filesystem, test doubles)
    ├── fakes/                        # Deterministic In-Memory Port Test Doubles
    │   ├── __init__.py
    │   ├── fake_command_runner.py    # Simulates CLI stdout streams and exit codes
    │   ├── fake_ticket_repository.py # In-memory ticket queue double
    │   ├── fake_state_store.py       # In-memory state persistence double
    │   ├── fake_signal_repository.py # In-memory signal and question double
    │   ├── fake_discord_gateway.py   # In-memory recorded discord threads and messages
    │   ├── fake_discord_logger.py    # In-memory recorded discord log events
    │   ├── fake_intervention.py      # In-memory scripted operator response double
    │   ├── fake_status_publisher.py  # In-memory status transition recorder
    │   └── fake_terminal_display.py  # In-memory terminal event recorder
    ├── unit/                         # Fast Isolated Layered Tests
    │   ├── domain/                   # Entity invariants, token budget math, paths, failure analysis
    │   ├── application/              # Interactor workflows using fakes
    │   └── adapters/                 # Parsers, serializers, locks, and file store tests
    ├── integration/                  # Out-of-band and Subsystem Tests
    │   └── test_discord_e2e.py       # End-to-end Discord smoke & flag verification
    └── specs/                        # Spec-Level Behavioral Verification Suites
        ├── test_spec_01_doctor.py
        ├── test_spec_02_queue.py
        ├── test_spec_03_worker.py
        ├── test_spec_04_gatekeeper.py
        ├── test_spec_06_state_ui.py
        └── test_spec_07_model_selection.py
```

---

## 4. Target Project Layout & Verification Subsystem (`<project-dir>/`)

When Ticket Runner targets an external codebase via `--project-dir <path>`, it expects or initializes the following directory structure:

```text
<project-dir>/
├── ticket-runner.yaml                # Project Overlay Config (test_cmd, build_cmd, base_branch)
├── .gitignore                        # Must ignore .agent/ runtime directory
├── <source-files>                    # Application source code under development
├── <test-files>                      # Project unit and integration test suites
│
├── .agents/skills/                   # Project-level Skills (synced from catalog or custom)
│   ├── implement/SKILL.md            # Worker implementation instructions
│   ├── code-review/SKILL.md          # Standards and spec review skill
│   ├── security-review/SKILL.md      # Security review discipline (ADR 0013)
│   └── verify-<app>/                 # Verification Subsystem Contract (Spec 13)
│       ├── SKILL.md                  # 5-step lifecycle: Launch -> Doctor -> Drive -> Evidence -> Cleanup
│       ├── harness/                  # Behavioral test drivers (Playwright, PTY CLI, HTTP)
│       │   ├── launch                # Spawns local app instance or dev server
│       │   ├── doctor                # Polls health endpoint or process vitality
│       │   ├── drive                 # Drives a named feature scenario
│       │   └── cleanup               # Shuts down processes and cleans test state
│       └── features/                 # Modular feature maps (<40 lines each)
│           ├── auth.md               # User POV path & harness commands for authentication
│           └── checkout.md           # User POV path & harness commands for checkout
│
├── .agent/                           # Untracked Runtime State Directory
│   ├── state.json                    # Active atomic runner state and crash recovery checkpoint
│   ├── signals/                      # Worker-to-Runner durable signals ({ticket_id}_ready.json)
│   ├── questions/                    # Worker operator questions ({ticket_id}.json)
│   ├── checkpoints/                  # Token budget context handoff checkpoints ({ticket_id}/handoff.md)
│   ├── logs/                         # Raw worker telemetry and stdout logs
│   ├── smoke_log_<spec-slug>.md      # Cumulative Gatekeeper smoke verification log
│   ├── evidence/                     # Verification Subsystem Evidence Artifacts (Spec 13)
│   │   └── <ticket_id>/              # Bounded evidence directory per ticket
│   │       ├── summary.json          # Exit code, duration, artifact links, sanitized failure excerpt
│   │       ├── harness.log           # Full untruncated harness stdout/stderr
│   │       └── screenshots/          # Captured UI screenshots and DOM traces
│   └── archive/                      # Completed specs and ticket folders (ADR 0012)
│
└── docs/
    ├── specs/                        # Active and planned specifications (Specs 10b, 11, 12, 13)
    ├── adr/                          # Architectural Decision Records (ADRs 0001 to 0022)
    └── tickets/                      # Active ticket queue
        ├── <spec-slug>/              # Active ticket directory (e.g., 10b-living-documentation-and-roadmap/)
        │   ├── T089-slug.md          # Pending or in-progress tickets
        │   └── completed/            # Completed tickets relocated upon Gatekeeper approval
        ├── .queue.lock               # Windows sentinel file lock during active execution
        └── gotchas.md                # Global cross-ticket operational knowledge log
```

---

## 5. Architectural Invariants & Cross-Cutting Contracts

1. **Clean Architecture Dependency Rule**:
   Source code dependencies point inward only. Application interactors depend solely on abstract domain entities and port interfaces. Concrete adapters (`OpenCodeWorker`, `AntigravityWorker`, `DiscordGateway`, `SubprocessRunner`) implement ports and are wired at the Composition Root (`runner/container.py`).

2. **External Path Resolution Invariant**:
   The Runner's CWD is the Target Project. Global binaries and configurations reside independently. All paths within `.agent/`, `docs/tickets/`, `docs/specs/`, and `.agents/skills/` resolve relative to `--project-dir`.

3. **Two-Tier Configuration Overlay**:
   `yaml_config_loader.py` merges `~/.ticket-runner/config.yaml` (machine-level defaults: Discord credentials, default models, timeouts) with `<project-dir>/ticket-runner.yaml` (project-specific overrides: `test_cmd`, `build_cmd`, `branch`, `worker.provider`) into an immutable domain `RunnerConfig`.

4. **Multi-Agent `AgentWorker` Port Contract**:
   Worker supervisor interacts exclusively with `AgentWorker` (`runner/ports/agent_worker.py`). Both `runner/adapters/opencode/` and `runner/adapters/antigravity/` implement identical command construction, stream decoding, and resource access contracts.

5. **Token-Preserving Verification Guardrails**:
   Verification harnesses run out-of-band. Full execution logs and visual artifacts are written directly to `<project-dir>/.agent/evidence/<ticket_id>/`. The LLM prompt receives exclusively a bounded triage excerpt (maximum **30 lines / 1,000 characters**) extracted by `evidence_triage.py`.

6. **Dual-Mode Human-in-the-Loop Approval Gate**:
   When verification passes in Human-in-the-Loop mode, execution pauses before committing. An `EvidenceCard` is dispatched via `ApprovalGateway` to the active presence channel (Rich TUI prompt in Nearby mode; Discord thread card with `/approve` in Away mode). Commits are strictly blocked until human sign-off.
