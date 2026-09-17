# Architecture & File Structure

Clean Architecture directory layout for Ticket Runner. Source code dependencies point strictly inward (`adapters` -> `ports` & `domain`, `application` -> `ports` & `domain`, `domain` has zero dependencies).

```text
ticket-runner/
├── ticket_runner.py                  # CLI entry point (argparse: start, doctor, pause, status)
├── config.yaml                       # Runner configuration
├── requirements.txt                  # Python dependencies (discord.py, rich, pyyaml)
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
│   │   ├── queue.py                  # Queue, alphanumeric ordering, completed relocation
│   │   ├── state.py                  # RunnerState, StateStatus, crash recovery state
│   │   ├── signal.py                 # ReadySignal, QuestionSignal, SignalStatus
│   │   ├── checkpoint.py             # Checkpoint entity, handoff metadata
│   │   ├── telemetry.py              # WorkerEvent, TokenUsage, ToolCall, WorkerMessage
│   │   ├── config.py                 # Frozen domain config dataclasses (RunnerConfig, etc.)
│   │   ├── runtime_paths.py          # Value object for resolving paths inside .agent/
│   │   └── exceptions.py             # Hierarchy rooted at TicketRunnerError
│   │
│   ├── application/                  # Application Use Cases / Interactors
│   │   ├── __init__.py
│   │   ├── doctor.py                 # Pre-flight environment checks & binary verification
│   │   ├── queue_orchestrator.py     # Sequential ticket loop (standby vs terminate)
│   │   ├── worker_supervisor.py      # OpenCode subprocess execution & stream telemetry
│   │   ├── handoff_coordinator.py    # Token budget rules (120k warn, 135k handoff, 150k ceiling)
│   │   ├── gatekeeper.py             # Test/build verification commands & Circuit Breaker
│   │   ├── ticket_processor.py       # Ticket execution seam driving verification loop & outcome mapping
│   │   ├── presence_coordinator.py   # Nearby vs Away mode & 3-min idle escalation timer
│   │   └── git_operations.py         # Branch isolation, conventional commits, tree resets
│   │
│   ├── ports/                        # Pure Abstract Protocols (ADR 0006 Seams)
│   │   ├── __init__.py
│   │   ├── command_runner.py         # Protocol for CLI execution (streaming stdout & exit codes)
│   │   ├── ticket_repository.py      # Protocol for locked scanning/updating docs/tickets/ queue
│   │   ├── state_store.py            # Protocol for atomic .agent/state.json persistence
│   │   ├── signal_repository.py      # Protocol for watching/writing signals & questions
│   │   ├── discord_gateway.py        # Protocol for Discord thread lifecycle & alerts
│   │   ├── terminal_display.py       # Protocol for Rich dashboard rendering & hotkey events
│   │   └── config_loader.py          # Protocol for loading RunnerConfig
│   │
│   └── adapters/                     # Concrete Adapters (Outermost Circle)
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py
│       │   └── subprocess_runner.py  # Asyncio subprocess implementing CommandRunner
│       ├── opencode/
│       │   ├── __init__.py
│       │   └── opencode_worker.py    # Worker stream driver converting JSON to WorkerEvents
│       ├── git/
│       │   ├── __init__.py
│       │   ├── git_client.py         # Git CLI operations using CommandRunner
│       │   └── pre_push_hook.py      # Installer/guardrail merger reading scripts/pre-push.sh
│       ├── markdown/
│       │   ├── __init__.py
│       │   ├── file_lock.py          # Windows msvcrt sentinel file locking context manager (.queue.lock)
│       │   ├── parser.py             # Parser for individual ticket files & gotchas.md
│       │   ├── serializer.py         # Serializer, status updater, and completed/ archiver
│       │   └── ticket_store.py       # Implements TicketRepository for docs/tickets/ directory
│       ├── filesystem/
│       │   ├── __init__.py
│       │   ├── json_state_store.py   # Implements StateStore via atomic tempfile replacement
│       │   └── signal_watcher.py     # Implements SignalRepository via filesystem polling
│       ├── discord/
│       │   ├── __init__.py
│       │   ├── client.py             # discord.py client lifecycle & event loop
│       │   ├── threads.py            # Thread-per-Ticket creation, updates, and locking
│       │   ├── commands.py           # Slash commands (/mode, /pause, /status)
│       │   └── gateway.py            # Implements DiscordGateway
│       ├── ui/
│       │   ├── __init__.py
│       │   └── terminal.py           # Rich Live dashboard & non-blocking msvcrt keyboard
│       └── config/
│           ├── __init__.py
│           └── yaml_config_loader.py # PyYAML adapter implementing ConfigLoader
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # Pytest fixtures (temp filesystem, test doubles)
│   ├── fakes/                        # Deterministic In-Memory Port Implementations
│   │   ├── __init__.py
│   │   ├── fake_command_runner.py    # Simulates CLI stdout streams and exit codes
│   │   ├── fake_ticket_repository.py # In-memory ticket queue double
│   │   ├── fake_state_store.py       # In-memory state persistence double
│   │   ├── fake_signal_repository.py # In-memory signal and question double
│   │   ├── fake_discord_gateway.py   # In-memory recorded discord threads and messages
│   │   └── fake_terminal_display.py  # In-memory terminal event recorder
│   ├── unit/                         # Fast Isolated Layered Tests
│   │   ├── domain/                   # Entity invariants, token budget math, paths
│   │   ├── application/              # Interactor workflows using fakes
│   │   └── adapters/                 # Parser, serializer, lock, and file store tests
│   └── specs/                        # Spec-Level Behavioral Tests (Specs 01-06)
│       ├── test_spec_01_doctor.py
│       ├── test_spec_02_queue.py
│       ├── test_spec_03_worker.py
│       ├── test_spec_04_gatekeeper.py
│       ├── test_spec_05_presence.py
│       └── test_spec_06_state_ui.py
│
├── .agent/                           # Runtime Directory (git-ignored)
│   ├── state.json
│   ├── checkpoints/
│   ├── signals/
│   ├── questions/
│   ├── logs/
│   └── archive/                      # Completed spec ticket dirs & spec files (ADR 0012)
│
├── .agents/skills/                   # Vendored Skills Catalog
│   ├── implement/SKILL.md
│   ├── to-tickets/SKILL.md
│   └── handoff/SKILL.md
│
└── docs/
    ├── specs/                        # Active specs: 04, 05, 06 (01–03 archived to .agent/archive/)
    ├── adr/                          # ADRs 0001 to 0015
    └── tickets/                      # Active ticket queue (specs 04–06)
        ├── .queue.lock               # Sentinel lockfile during execution
        └── gotchas.md                # Cross-ticket global lessons learned
```
