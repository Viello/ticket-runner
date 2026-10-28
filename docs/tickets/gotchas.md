# Global Gotchas & Lessons Learned

A chronological record of runtime quirks, platform pitfalls, and architectural lessons discovered during ticket implementations. Subsequent ticket sessions ingest these lessons to prevent recurring mistakes.

---

## Discord Snowflake Validation & Config Loader Defaults

- **Problem:** Discord snowflake IDs (like `guild_id` and `notify_user_id`) can be up to 20 digits and can be loaded from YAML either as quoted strings or unquoted numbers (integers). Applying integer length constraints or strict string typing without coercion in the loader breaks valid configurations, while mutating fields in a `frozen=True` dataclass fails.
- **Solution:** Handle type coercion and strip whitespace in the loader adapter (`str(val).strip() if val is not None else ""`), validate snowflake IDs using `str.isdigit()` in `DiscordConfig.__post_init__` for non-empty values, and provide empty string defaults so omitting optional fields maintains backward compatibility.

---

## RuntimePaths Containment Resolution & Smoke Log Fallbacks

- **Problem:** `RuntimePaths` root directory can be instantiated either as relative (`Path(".agent")`) or absolute (e.g. `tmp_path / ".agent"` in test harnesses). Performing path containment checks without resolving paths, or performing cross-drive checks on Windows, can lead to unexpected `ValueError` exceptions. Furthermore, `ReadySignal.scope` can be empty or omitted by workers, risking missing or malformed log paths.
- **Solution:** In `RuntimePaths.smoke_log_path`, sanitize the spec slug by replacing non-alphanumeric, non-hyphen characters with underscores and check `target.resolve().is_relative_to(root_resolved)` within a guarded `try/except (ValueError, RuntimeError)` block. In `VerificationLoop._append_smoke_log`, explicitly fallback to `ticket.id` when `ready_signal.scope` is empty or None before delegating to `smoke_log_path`.

---

## PromptBuilder Template Escaping & Command-Line Length Ceilings

- **Problem:** Python f-string prompt templates in `PromptBuilder.build` require literal JSON schema curly braces to be escaped as `{{` and `}}` to avoid KeyError interpolation failures. Additionally, as `AGENTS.md` invariants and prompt schema instructions expand, total Windows command length must be monitored to ensure it stays well below the 32,767-character Windows subprocess ceiling.
- **Solution:** Always double JSON schema braces (`{{` and `}}`) in prompt builder templates, and ensure unit tests for command length assertions accommodate new invariants while maintaining generous safety margins beneath the OS ceiling.

---

## Ticket Markdown Parser Status and Metadata Schema Constraints

- **Problem:** When generating or templating tickets in automation or recovery skills (such as `/smoke-fail`), introducing ad-hoc frontmatter status values like `Status: todo` or non-standard metadata causes `TicketMarkdownParser` or domain validation to reject tickets or crash with unhandled parsing errors.
- **Solution:** Adhere strictly to the domain entity status enum (`Status: pending`, `completed`, or `skipped`) in ticket templates, and structure all sections around standard markdown headers (`### Requirements`, `### Acceptance Criteria`, `### Smoke Scenarios`, `### Gotchas`) recognized by `TicketMarkdownParser`.

---

## DiscordGateway Protocol Conformance & Async Test Runner Mark

- **Problem:** `runtime_checkable` Protocols in Python only verify method existence, not parameter count or async signatures; missing or misaligned parameters will pass `isinstance` checks silently. Additionally, this repository executes async tests via `anyio` (`anyio-4.13.0`), causing tests marked with `@pytest.mark.asyncio` to fail with unhandled async function errors and unknown mark warnings.
- **Solution:** Mark all asynchronous test functions with `@pytest.mark.anyio`. Write exhaustive unit tests asserting every recorded `DiscordCall` attribute on `FakeDiscordGateway` to verify signature alignment. In `create_thread`, always return distinct snowflake strings for `(thread_id, starter_message_id)` to preserve the starter message ID needed for Status Card pinning in downstream specs.

---

## discord.py Exception Wrapping & Channel Resolution in Adapters

- **Problem:** `discord.py` operations raise library-specific exceptions (`discord.HTTPException`, `discord.NotFound`, `discord.Forbidden`, `discord.DiscordException`, plus `ValueError` on bad snowflake conversion). Letting these escape crosses the adapter boundary, leaking `discord.py` types to caller modules and breaking CLI/domain execution in `--local-only` mode. Furthermore, `client.get_channel` only checks the client's in-memory gateway cache and returns `None` on cold start before events are received.
- **Solution:** In `DiscordPyGateway`, wrap all six port methods in guarded blocks converting integer snowflakes, falling back from `client.get_channel` to `await client.fetch_channel` on cache misses, and catching all `discord.DiscordException` and conversion errors to re-raise as `DiscordGatewayError`. Ensure sensitive bot tokens are never included in exception messages or object representations.

---

## Discord Client Lifecycle, Guild-Scoped Sync & CommandTree Mocking

- **Problem:** `client.start()` is a long-running coroutine that blocks indefinitely until disconnected; directly awaiting it blocks concurrent execution of callers waiting for `ready_event`. Furthermore, global command tree synchronization (`tree.sync()`) can take up to an hour to propagate in Discord, delaying developer feedback. During unit testing, `discord.app_commands.CommandTree` directly accesses `client.http` and `client._connection._command_tree`, raising `AttributeError` or `ClientException` when wrapping standard mock clients.
- **Solution:** In orchestrators and CLI runners, schedule `client.start()` as a background `asyncio.Task` so callers can concurrently await `ready_event`. Always sync slash commands to a specific guild (`tree.sync(guild=discord.Object(id=guild_id))`) to achieve sub-second propagation. Guard `client.close()` with `asyncio.wait_for(client.close(), timeout=2.0)` catching `(asyncio.TimeoutError, TimeoutError)` so runner exit paths never hang. When mocking `discord.Client` for `CommandTree` tests, explicitly configure `mock._connection._command_tree = None` to avoid double-tree initialization errors.

---

## Discord Slash Commands & Thread Reply Pure Filtering Chain

- **Problem:** Slash command interactions and thread reply events can run in standalone mode before or without an active runner orchestrator session. If `StateStore.read()` returns `None` (state file absent on disk), attempting direct dictionary access raises `AttributeError`. In `process_thread_reply`, testing Discord message handling without live gateway connections requires pure function isolation from event dispatchers, handling duck-typed mock channels/threads without falsely classifying `TextChannel` or unconfigured `MagicMock` instances as threads, and handling absent question signals in `SignalRepository.write_answer` without crashing the listener.
- **Solution:** In `format_status_response`, gracefully handle `state is None` by returning `[Offline / Standalone Bot]\nNo runner state available.` and checking `runner_status != "running"` before formatting fields. Implement `process_thread_reply(message_data, signal_repository, config)` as a pure async function that strictly validates thread types (checking `discord.Thread`, channel type enums, and non-mock parent IDs), matches ticket IDs with regex `^([A-Z]\d{3,})`, enforces configured `channel_id` and optional `notify_user_id`, and safely wraps `signal_repository.write_answer` in a try/except block posting error feedback in-thread if the question signal is missing or invalid.

---

## Discord Bot Standalone CLI, Smoke Cleanup & SIGINT Teardown

- **Problem:** `--smoke` must leave the target Discord channel completely clean after verification. While Discord archives and locks a public thread via API, it leaves the original announcement/starter message in the parent channel. Failing to explicitly delete the starter announcement message pollutes the channel across smoke test runs. Additionally, `argparse` subcommands requiring mutually exclusive options can cause misleading error messages if mutual exclusivity is checked via manual `if/else` logic instead of native parser groups. Finally, SIGINT on Windows arrives as a `KeyboardInterrupt` which can abort coroutines mid-execution without cleanly disconnecting the Discord gateway WebSocket.
- **Solution:** Add `delete_message` to the `DiscordGateway` protocol, `FakeDiscordGateway`, and `DiscordPyGateway`. In `run_smoke`, after archiving the thread, delete the starter message explicitly (`await gateway.delete_message(channel_id, starter_msg_id)`). In `create_parser`, enforce mutual exclusivity between `--smoke` and `--run` using `parser.add_mutually_exclusive_group(required=True)`. In `run_bot`, handle `KeyboardInterrupt` and `signal.SIGINT` gracefully by cleanly awaiting `client.close()` and returning exit code 130.

---

## discord.py Guild Command Syncing & on_ready Exception Propagation

- **Problem:** In `discord.py`, commands decorated with `@tree.command` register globally by default. Calling `await tree.sync(guild=guild_obj)` syncs only guild-specific commands (`tree._guild_commands[guild_id]`). Without copying global commands first, `tree.sync` uploads an empty list (`[]`) to Discord, clearing all guild slash commands and causing Discord to display no slash commands for `/status`, `/pause`, and `/mode`. Additionally, `discord.py` catches exceptions raised in event handlers like `on_ready` inside its internal event dispatcher and calls `client.on_error` instead of propagating the exception to `client.start()`. If `ready_event` is only set at the completion of `on_ready`, any exception in `on_ready` hangs the caller until the connection timeout without printing the root cause.
- **Solution:** Always call `tree.copy_global_to(guild=guild_obj)` before calling `await tree.sync(guild=guild_obj)` when syncing global command definitions to a test or target guild. Wire an `on_error` handler on `client` to record `client.ready_error = exc` and set `client.ready_event` whenever an event error occurs before readiness, allowing CLI loops to fail fast and display the true exception to `stderr`. Ensure `client.close()` resets `ready_error = None`.

---

## Discord Live Pre-Flight Connection, Timeout Guards & Token Redaction

- **Problem:** Running a full bot lifecycle (like `DiscordClient` with command tree sync) for a simple pre-flight permission check is slow, prone to command tree sync timeouts, and unnecessarily complex. Furthermore, `channel.permissions_for(guild.me)` requires `guild.me` to be populated in cache; if the bot connects without the `Guilds` intent or fetches the channel before cache readiness, `guild.me` is `None`. Additionally, network issues or invalid tokens can cause pre-flight checks to hang indefinitely or print raw secret token strings to terminal output and logs during authentication failures.
- **Solution:** Use a short-lived, minimal `discord.Client(intents=discord.Intents.default())` that starts in a task, waits for readiness, and resolves permissions without syncing command trees. Wrap channel fetching in a 10-second `asyncio.wait_for` timeout guard and ensure `client.close()` and task cancellation always execute in a `finally` block. Never include the token value in `CheckResult.message` or `CheckResult.remediation`; always refer solely to the environment variable name (e.g. `DISCORD_BOT_TOKEN`).

---

## Discord Developer Portal Onboarding Documentation & Permission Bits

- **Problem:** Guiding developers through manual Discord bot onboarding requires exact, error-free permission calculations and clear distinctions between Discord snowflake IDs and usernames. If documentation omits the precomputed permission integer, developers must navigate third-party calculators and risk missing one of the 7 granular permissions required by Ticket Runner. Furthermore, omitting Developer Mode instructions prevents users from finding channel, guild, and user snowflake IDs in the Discord UI.
- **Solution:** In onboarding documentation (`docs/discord-setup.md`), provide the exact 7-permission bitwise integer (`326417606656`) directly in the OAuth2 URL template so it can be used without external tools. Explicitly document toggling Developer Mode under User Settings > Advanced prior to ID copying steps, and explain the security utility of `notify_user_id` as a numeric snowflake restriction for shared servers.

---

## DiscordLogger Precomputed Chunk Counts, Embed Field Limits & Test Double Recording

- **Problem:** When chunking long payloads for Discord, streaming chunks dynamically before the full split is evaluated leads to incorrect or placeholder continuation counts in `[continued N/M]` headers. In addition, Discord enforces strict character limits on embeds (title 256 chars, field name 256 chars, field value 1,024 chars, description 4,096 chars); exceeding title or field limits causes remote API 400 Bad Request errors. In test doubles, if a fake logger only records dispatched calls and silently drops suppressed events, downstream routing tests cannot differentiate between a bug where the logger wasn't called vs correct presence-mode suppression.
- **Solution:** In `split_chunks` and `format_chunks`, evaluate all split points upfront and calculate `M = len(raw_chunks)` before formatting or posting any messages, ensuring all continuation headers reference the exact total. Sanitize all embed dicts by truncating titles to 256 characters, field names to 256 characters, and field values to 1,024 characters, while applying 1,950-character chunking to descriptions. In `FakeDiscordLogger`, record all invocations with resolved `severity` and boolean `suppressed` decisions in `calls` so tests can assert routing behavior even when gateway dispatches are suppressed.

---

## Status Card Column Alignment, Pure Token Bar & Live Digest Rate-Limit Flushing

- **Problem:** Monospace Discord embeds require precise column alignments; if labels and colons are right-padded inconsistently across lines, the status card layout degrades into ragged text. Using date-time strings with full dates in `Last updated` violates the verbatim monospace spec layout. In the Live Digest, treating the 500-character rolling window as token count or estimating tokens instead of raw character slicing causes truncation errors. Furthermore, naive rate-limiting using `time.time()` breaks testability under simulated time, while failing to cancel pending delayed flushes upon `finish_live_digest()` can cause race conditions or drop the trailing `\n[done]` marker.
- **Solution:** Right-pad all status card field labels and colons to exactly 14 characters (`f"{'Label:':<14}{value}"`) and wrap the entire description in a markdown code block (```` ```\n...``` ````), ensuring colons and values align at column 15 across all 7 fields. Keep `Last updated` and `Started` strictly in `HH:MM UTC` format. In `update_live_digest`, apply character slicing `buffer[-500:]` and check elapsed time against `asyncio.get_running_loop().time()`. If within the 5-second floor, buffer chunks and schedule a single delayed flush task. In `finish_live_digest()`, mark the digest as completed, cancel and await any in-flight flush task, append `\n[done]` even if the window is empty, and edit the message immediately.

---

## Discord Thread-per-Ticket Lifecycle, Status Card Parent Pinning & Graceful Archival

- **Problem:** Discord creates public threads off an initial parent message posted to the parent channel (`channel.send()` followed by `message.create_thread()`). The starter announcement message is the Status Card itself, requiring both the `thread_id` and `starter_message_id` to be tracked and returned so the Status Card can be edited in-place throughout execution. Furthermore, Discord forbids pinning a message inside a thread before the thread entity exists, and calling `archive_thread` on a thread that is already archived or locked raises remote API errors (`DiscordGatewayError`), which would crash ticket completion during runner retries or restarts.
- **Solution:** In `DiscordThreadManager.open_ticket_thread`, invoke `gateway.create_thread` with the Status Card embed payload to post the parent starter message and spawn the thread in one seam, then call `gateway.pin_message(thread_id, starter_msg_id)` before calling `logger.start_live_digest(thread_id)`. Sync the created card state into `logger._status_cards` so subsequent phase transitions (`update_status_card`) retain ticket and spec metadata. In `close_ticket_thread`, post the green commit summary embed (`0x57F287`), update the Status Card to `✅ Committed`, and guard `gateway.archive_thread(thread_id)` in a `try/except DiscordGatewayError` block that logs a warning and exits cleanly without raising.---

## Idle Escalation Timer, Presence Auto-Reset & Notify User ID Isolation

- **Problem:** If a question signal or circuit breaker prompt remains unanswered while in `nearby` mode, the runner must escalate to `away` mode after `idle_escalation_minutes` and notify the developer via Discord `@mention` and a yellow embed. Directly calling `asyncio.sleep` in the coordinator creates untestable, hanging unit tests. In addition, rapid successive scheduling calls can stack multiple in-flight timers that fire duplicate Discord mentions, while resetting presence on failed thread replies could leave the runner stuck in `nearby` mode when no valid answer was recorded. Finally, including `notify_user_id` in terminal logs or state snapshots leaks developer identity into persistent disk state.
- **Solution:** In `PresenceCoordinator.schedule_escalation`, always invoke `self.cancel_escalation()` before scheduling a new task to prevent timer stacking, and provide a configurable `timer_factory` seam with signature `(delay_seconds, callback) -> Task` so test suites can inject immediate zero-delay completion. In `process_thread_reply`, inject an optional `PresenceCoordinator` and invoke `set_mode("nearby")` strictly within the `try:` block after `signal_repository.write_answer` succeeds, ensuring failure paths leave presence unchanged. Never write `notify_user_id` to `StateStore`, UI event sinks, or terminal outputs; interpolate it only into Discord `<@id>` mention strings sent directly over the Discord gateway.

---

## Discord Slash Command Choices, Parameter Normalization & Ephemeral Validation

- **Problem:** Discord slash commands registered with `@app_commands.choices` restrict options in the Discord UI, but command callbacks can receive parameters either as `app_commands.Choice[str]` (when invoked through the Discord gateway dispatcher) or as raw `str` strings (when invoked in unit test suites or direct harness calls). If a command handler assumes one type exclusively or calls `.value` on raw strings, `AttributeError` is raised in tests or runtime. Furthermore, if a slash command handler lacks defensive validation before dispatching to domain entities like `PresenceCoordinator` / `RunnerState`, invalid inputs could raise unhandled `StateFormatError` and crash the interaction response rather than returning an informative ephemeral error to the user.
- **Solution:** In slash command callbacks and handlers, normalize parameter inputs with `mode_val = mode.value if isinstance(mode, app_commands.Choice) else str(mode)`. Validate `mode_val in VALID_PRESENCE_MODES` before calling `presence_coordinator.set_mode()`, returning an ephemeral Discord reply listing valid options if validation fails. When testing command tree callbacks directly, test both `Choice` objects and plain strings, and assert parameter `choices` against `VALID_PRESENCE_MODES` on the registered `tree.get_command("mode").parameters`.

---

## Discord Ticket Lifecycle Integration & Gateway Exception Non-Interference

- **Problem:** Connecting Discord thread management and logging into the core ticket lifecycle (`GatekeeperTicketProcessor` and `VerificationLoop`) introduces remote I/O points at critical execution milestones (thread creation, status card updates, phase transitions, question escalation, thread archival). If Discord API calls raise `DiscordGatewayError` or network exceptions during verification or commit phases, an unhandled exception would crash ticket processing, fail valid commits, or leave the runner stuck. Additionally, question signals use `created_at` timestamps while ready signals use `timestamp`; submitting mismatched schema fields causes immediate `SignalFormatError` which consumes attempt budgets.
- **Solution:** Wrap all Discord thread management, status card updates, and event logging calls in `try ... except (DiscordGatewayError, Exception)` blocks that log warnings without bubbling exceptions up to the verification loop or orchestrator. Route critical events (`circuit_breaker_trip`, `hard_ceiling`, `handoff`, `verification_failed`) with `severity="critical"` so `DiscordLogger` bypasses presence mode suppression. Ensure `QuestionSignal` creation and parsing strictly adhere to the `created_at` field name.

---

## Discord Live Starter Message Resolution, Empty Message Guards & End-to-End Test Isolation

- **Problem:** Starter messages posted in a parent channel to create a public thread (`msg.create_thread()`) cannot be retrieved via `thread.fetch_message()` on the thread object itself, raising 404 `Unknown Message`. Additionally, attempting to send or edit a Discord message with empty content when no embed is provided causes Discord API error 50006 `Cannot send an empty message`. Pinning starter messages in parent channels may also trigger 403 `Missing Permissions` if the bot lacks channel-wide manage messages permissions. Furthermore, in end-to-end integration tests, signals seeded in repositories before `processor.process(ticket)` are purged by the isolation layer at the start of the ticket, leading to missing ready signal errors.
- **Solution:** In `DiscordPyGateway._resolve_message`, catch `discord.NotFound` on thread message fetching and fall back to `channel.parent.fetch_message(msg_id)` when `channel` is a thread. In `post_message` and `edit_message`, default empty content to `"..."` whenever `embed` is `None` to satisfy Discord API constraints. In `open_ticket_thread`, wrap `pin_message` in a guarded `try/except DiscordGatewayError` block so missing channel-level pin permissions do not abort thread opening. In integration test suites, seed signals dynamically inside the cycle runner callback so they are written during cycle execution rather than wiped by the initial ticket purge.

---

## External Runner Architecture Synchronization & Living Documentation Updates

- **Problem:** When evolving a monolithic or local repository orchestrator into an external multi-agent runner targeting `--project-dir`, living documentation (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`) can quickly drift out of date. Outdated references to superseded active specs (e.g. referencing specs 04–06 when specs 01–10 are archived), missing architectural layers (such as `tests/integration/`, `clean_slate.py`, `crash_recovery.py`), or obsolete ADR counters degrade developer and AI context.
- **Solution:** Maintain living documents as strict authoritative reflections of both the current working codebase and planned architectural boundaries. When updating `ARCHITECTURE.md`, verify that active spec lists, ADR indices, test directory trees, and adapter implementations reflect actual repository state alongside newly introduced ports (`AgentWorker`) and contracts (Verification Subsystem, `--project-dir` runtime separation).

---

## External Multi-Agent Domain Invariant Maintenance & Synonym Prohibitions

- **Problem:** As the system architecture transitions from a project-local runner to an external multi-agent orchestrator, new architectural concepts (Target Project, AgentWorker, Verification Harness, Evidence Card, Project Overlay Config, Skills Catalog, LLM Config Prompt) risk being referred to by vague or conflicting synonyms across agent sessions (e.g. "target repo", "client project", "LLM backend", "test harness", "verification summary"), muddying domain boundaries and confusing prompt contexts.
- **Solution:** Maintain explicit, canonical definitions in `CONTEXT.md` with dedicated `_Avoid_:` synonym blocks. Guard foundational orchestrator terms (such as `Worker` and `Gatekeeper`) against redefinition or dilution, and decouple agent lifecycle abstractions through `AgentWorker` while anchoring repository boundaries at `Target Project`.

---

## Agent Living Document Context Preservation & Invariant Density

- **Problem:** Adding new operational invariants and guardrails to root living documents like `AGENTS.md` can inadvertently bloat always-loaded agent context windows if written as multi-sentence explanatory prose. Excessive prose increases context consumption across every subsequent turn and degrades prompt adherence.
- **Solution:** Apply the `writing-for-agents` discipline strictly: lead with tight capitalized labels and positive prompts, formulate hard bounds numerically (e.g. 30 lines / 1,000 characters), prune explanatory commentary already covered in detailed specs, and keep statements checkable and dense.

---

## Nested Markdown Code Blocks in LLM Config Prompts & Two-Tier Configuration Clarity

- **Problem:** When providing standalone copy-pasteable Markdown LLM Config Prompts containing inner fenced code blocks (` ```yaml `, ` ```powershell `) within top-level documentation like `README.md`, standard 3-backtick delimiters prematurely close the outer container block, corrupting markdown rendering on GitHub and CLI viewers. Furthermore, conflating machine-level infrastructure settings (Discord bot tokens, global token limits) with repository-level settings in configuration templates confuses developers and AI assistants configuring new projects.
- **Solution:** Always enclose markdown templates containing inner fenced blocks in 4-backtick (` ````markdown ` ... ` ```` `) boundaries to guarantee clean parsing and syntax highlighting. Explicitly structure configuration documentation around the two-tier hierarchy: global machine settings in `~/.ticket-runner/config.yaml` vs minimal project overrides in `ticket-runner.yaml`, keeping the project overlay template lightweight and focused strictly on test commands, build commands, and branch names.

---

## Spec 10b Alignment Audit & Living Documentation Synchronization

- **Problem:** Evolving architectural specifications and introducing new domain vocabulary in `CONTEXT.md` (e.g. `Target Project`, `AgentWorker`, `Project Overlay Config`, `Verification Harness`, `Evidence Card`, `Skills Catalog`, `LLM Config Prompt`) easily leaves lingering avoided synonyms (like `setup prompt`, `session rollover`, `project settings`, `verification summary`, `dumps`) in top-level documentation, downstream draft specs, or README headers and tables of contents. Furthermore, changing section headers without updating corresponding table-of-contents anchor slugs breaks markdown in-page navigation.
- **Solution:** As part of every spec-closing alignment ticket, execute repository-wide automated audits checking against all `_Avoid_:` lists defined in `CONTEXT.md`, synchronize table-of-contents anchor slugs with revised header titles, verify all internal markdown links and code block fence balance (` ```` ` vs ` ``` `), and ensure test suites remain completely green before archiving the spec.

---

## AgentWorker Port Protocol Decoupling & Legacy OpenCode Aliasing

- **Problem:** When decoupling an application supervisor (`WorkerSupervisor`) from a concrete CLI adapter (`runner/adapters/opencode/opencode_worker.py`) using an abstract protocol (`AgentWorker`), directly importing the adapter anywhere in `worker_supervisor.py` violates Clean Architecture and fails AST/source import assertions. Conversely, requiring `agent_worker` unconditionally in the supervisor constructor breaks numerous legacy tests and interactors that instantiate `WorkerSupervisor` without passing test doubles. Furthermore, refactoring event wire models from `OpenCodeEvent` to `WorkerEvent` risks breaking external consumers and existing tests.
- **Solution:** Provide a class-level registration seam on `WorkerSupervisor` (`set_default_agent_worker_factory`) initialized at the Composition Root (`runner/container.py`) and test runner root (`tests/conftest.py`) while accepting `agent_worker: AgentWorker | None = None` in `__init__`. In the adapter module, define `OpenCodeEvent = WorkerEvent` as a direct alias and re-export it in `__init__.py`. In `OpenCodeWorker`, implement all protocol methods (`build_run_command`, `decode_event`, `extract_resource_access`) and ensure fallback scanning in `extract_resource_access` inspects both `actual_line` and `actual_event.raw` so no accessed resources are missed.

---

## Multi-Agent Provider Configuration & Antigravity Adapter CLI Parameterization

- **Problem:** Adding a new agent adapter like `AntigravityWorker` alongside `OpenCodeWorker` requires dynamically wiring the CLI adapter into both `RunnerContainer` and `WorkerSupervisor`'s default factory based on `worker.provider` ("opencode" vs "antigravity"). In addition, CLI argument construction for external tools must strictly avoid shell interpolation to prevent command injection, and stream decoding must handle diverse event envelopes and token structures without crashing or discarding unparseable lines.
- **Solution:** In `WorkerConfig`, validate `provider` against `VALID_WORKER_PROVIDERS = frozenset({"opencode", "antigravity"})` defaulting to `"opencode"`. In `runner/container.py`, select the factory dynamically (`worker_factory = AntigravityWorker if resolved_config.worker.provider == "antigravity" else OpenCodeWorker`) and wire it to both `WorkerSupervisor.set_default_agent_worker_factory` and `resolved_agent_worker`. In `AntigravityWorker`, construct commands as discrete argv tokens (`['agy', 'run', '--auto', prompt, ...]`), sanitize string inputs, validate against `MAX_LINE_CHARS`, safely decode token usage from either `tokens` or `usage`, and extract project-local skill and `AGENTS.md` access across structured payloads and raw text lines.

---

## Doctor Provider Binary & Target Project Git Repository Pre-Flight Verification

- **Problem:** When configuring alternative agent backends (like `worker.provider: "antigravity"`) or decoupling project execution to an external target directory (`--project-dir`), pre-flight checks must verify both the provider binary (`opencode` or `agy`) and the validity of the target Git repository before any queue or test processing occurs. Hardcoding `opencode` CLI checks or checking Git without verifying directory existence and git worktree status (`git rev-parse --is-inside-work-tree`) leads to misleading test/status errors. Furthermore, in test environments, binary path resolvers must be injectable (e.g. `which_fn` / `path_resolver`) so unit tests do not depend on host machine PATH or fail on legacy command runner mocks that omit `git rev-parse`.
- **Solution:** Extend `Doctor` with `_check_worker_binary` that resolves `worker.provider` dynamically and checks the corresponding binary (`opencode` or `agy`) using an injectable `which_fn` / `path_resolver` (defaulting to `shutil.which`). Add `_check_target_git_repo` verifying directory existence, directory type, and git worktree status via `git rev-parse --is-inside-work-tree` through `GitOperations` or `CommandRunner`. In `GitOperations.is_inside_work_tree`, handle real git responses (`out == "true"`), explicit failure exit codes, and legacy test doubles with default empty results so existing test suites remain backwards-compatible.

---

## External Project Root Resolution, Relative Path Ambiguity & Security Containment

- **Problem:** When decoupling the composition root (`runner/container.py`) and storage adapters (`RuntimePaths`, `DirectoryTicketStore`, `GotchasStore`, `QueueFileLock`) to operate on an external target directory (`--project-dir`), accepting raw string or relative path arguments leads to path ambiguity when subprocess working directories (`cwd`) change during execution. Furthermore, without defensive ticket ID and session ID validation, runtime paths constructed from external ticket identifiers (`ready_signal_path`, `checkpoint_dir`, `session_log_path`) could escape the target `.agent/` directory tree through directory traversal attacks (`../`, `..\`). Finally, resolving relative ticket paths in `DirectoryTicketStore` without referencing the target project root causes file lookup failures when ticket arguments contain `docs/tickets/` prefixes.
- **Solution:** In `runner/container.py:build_container`, normalize `project_dir` (and fallback `cwd`) immediately using `Path(project_dir).resolve()` and route the resolved path to all adapters and interactors (`RuntimePaths`, `DirectoryTicketStore`, `GotchasStore`, `QueueFileLock`, `GitOperations`, `GatekeeperCommandExecutor`, `WorkerSupervisor`, `QueueOrchestrator`, `TuiCoordinator`), while preserving backwards compatibility when omitted. In `RuntimePaths`, validate all ticket IDs against `TICKET_ID_PATTERN` (`^[A-Za-z0-9_-]+$`) and session IDs against `SESSION_ID_PATTERN` (`^ses_[A-Za-z0-9]+$`), and enforce containment checks (`target.resolve().is_relative_to(base.resolve())`) across all artifact paths. In `DirectoryTicketStore._resolve_ticket_path`, resolve relative ticket paths against both `self._root_dir` and `self._root_dir.parent.parent` (the project root) before falling back to candidate checks.

---

## argparse Subparser Default Clobbering & CLI Target Path Resolution

- **Problem:** When an argument like `--project-dir` or `--config` is declared on both the root `ArgumentParser` and on subparsers (`doctor`, `start`) with default values (such as `Path.cwd().resolve()`), Python's `argparse` executes subparser evaluation after parent parsing. If the operator passes `--project-dir <path> doctor` (before the subcommand), the subparser's default clobbers the parsed target directory back to `CWD`. Furthermore, passing an unvalidated non-existent directory or regular file path to `--project-dir` causes confusing, delayed errors inside git operations or storage adapters rather than a fast, informative pre-flight exit.
- **Solution:** In `ticket_runner.py:create_parser`, declare arguments on subparsers with `default=argparse.SUPPRESS`. This ensures arguments supplied either before or after subcommands are preserved without subparser defaults overwriting top-level flags. In `main()`, `run_doctor()`, and `run_start()`, defensively validate that `project_dir` exists and is a directory (`project_dir.exists()` and `project_dir.is_dir()`), exiting immediately with code 1 on invalid paths. In `Doctor.__init__`, resolve relative configuration, ticket, and git paths relative to `self._cwd` so external project structures are loaded accurately.

---

## Temporary Directory Isolation & Secret Auditing for Remote Skills Publication

- **Problem:** Publishing a remote skills catalog repository (such as `Viello/agent-skills`) from a local orchestrator workspace using `gh repo create` or `git init` directly inside the parent repository risks corrupting the parent repository's git remotes, accidentally committing internal `.env` files or session traces, or linking submodules unintentionally. Furthermore, pushing uninspected local skills to a public GitHub repository could leak API keys or private tokens.
- **Solution:** In `scripts/publish_agent_skills.py`, assemble and stage the skills catalog inside an isolated temporary directory (`tempfile.TemporaryDirectory()`) outside the project root. Enforce an automated security audit scanning for forbidden file names (`.env*`, `*.pem`, `*.key`, `*.token`, `credentials.json`) and regex patterns for credentials (GitHub PATs, private keys, API keys) prior to git staging. Isolate git operations (`git init -b main`, `git remote add origin`, `git push -u origin main`) entirely within the clean temporary directory so the parent Ticket Runner git repository is never linked or altered.

---

## Two-Tier Configuration Deep-Merging & Safe Path Resolution

- **Problem:** When loading layered configurations (global machine defaults vs project-level overrides), shallow dictionary updates (`dict.update()`) overwrite entire sub-sections (e.g., overriding only `tokens.ceiling` would erase `tokens.warn` and `tokens.handoff`). Conversely, list or scalar collisions could append duplicates instead of cleanly overriding parent settings. Additionally, accepting external `project_dir` or `project_config_path` arguments exposes the runner to directory traversal attacks (e.g. `../` escaping project root) or null-byte injection.
- **Solution:** Implement a recursive `_deep_merge` helper where nested dictionaries are recursively merged while lists and scalar values in the overlay strictly replace their base counterpart. Seed the merge with built-in safe machine defaults (`DEFAULT_MACHINE_CONFIG`), merge global user configuration (`~/.ticket-runner/config.yaml`) if present, and finally deep-merge the project overlay (`ticket-runner.yaml` or fallback `config.yaml`). Defensively sanitize all input paths by rejecting embedded null bytes, verifying directory existence, and using `path.resolve().is_relative_to(project_dir.resolve())` to guarantee project configuration files cannot escape the target project boundary.

---

## Project Manifest Sniffing, Malformed Manifests & Git Detached HEAD Clean Recovery

- **Problem:** Target project manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`) are untrusted and can contain malformed JSON, corrupted TOML syntax, or unexpected field types that cause crashes during static inspection. Furthermore, inspecting Git metadata on uncommitted repositories, bare directories, or detached HEAD states can cause Git commands to return non-zero exit codes, fail symbolic ref resolution, or raise unexpected errors. Finally, Windows PowerShell strips inner quotation marks when executing inline `python -c "..."` commands, causing syntax errors in CLI smoke tests.
- **Solution:** In `ProjectSniffer`, isolate file reads within bounded size limits (1MB) and parse JSON within guarded exception blocks that fall back to sensible defaults (`npm test`) without crashing. For Git inspection, verify `.git` directory presence and boundary containment before running commands, query `.git/HEAD` directly as a zero-process fallback, and catch all subprocess errors when resolving symbolic refs or branches, defaulting safely to `main`. When running self-contained Python smoke snippets in PowerShell, use PowerShell here-strings (`python -c @"..."@`) to preserve nested quotations cleanly.

---

## Skills Catalog Synchronization, Zip Slip Mitigation & Asynchronous Seam Bridging

- **Solution:** In `GitHubSkillsClient`, inspect every archive member before extraction, verifying path containment (`dest.is_relative_to(target)`) and rejecting any entry containing `..`, absolute paths, or suspicious links with immediate `SkillsSyncError`. Locate skill roots dynamically by searching for `SKILL.md` rather than assuming fixed nesting depths, preserving custom local skills and respecting `force=False` for modified files. Bridge async `CommandRunner` invocations to synchronous callers using `ThreadPoolExecutor` when an event loop is running, ensuring seamless execution across CLI, test suite, and async bot environments.

---

## .gitignore Newline Separation & Symlink Path Traversal in Project Scaffolding

- **Problem:** When appending entries such as `.agent/` to existing `.gitignore` files, missing trailing newlines can concatenate strings onto existing lines (corrupting previous ignore rules). Furthermore, naive filesystem scaffolding without un-resolved symlink inspection allows symlink traversal or overwriting linked files if a target path is an existing symlink pointing outside or inside the project directory.
- **Solution:** Check the trailing newline of `.gitignore` content before appending (`prefix = "" if (not content or content.endswith("\n") or content.endswith("\r\n")) else "\n"`), and validate raw un-resolved paths (`raw_target.is_symlink()`) as well as resolved relative containment (`target.resolve().is_relative_to(resolved_root)`) before creating files or directories during scaffolding.

---

## CLI Two-Tier Configuration Resolution, Subparser Defaults & Scaffolding Fallbacks

- **Problem:** When integrating two-tier configuration resolution (`~/.ticket-runner/config.yaml` + `<project-dir>/ticket-runner.yaml`) into CLI commands (`doctor`, `start`), top-level `--config` arguments with defaults (like `default=Path("config.yaml")`) clobber two-tier resolution, treating every invocation as an explicit config request and preventing automated fallback to `ticket-runner.yaml`. In addition, scaffolding un-manifested or empty repositories produces an empty `test_cmd: ""`, causing subsequent `VerificationConfig` and doctor pre-flight validation to immediately fail. Finally, omitting default models from `DEFAULT_MACHINE_CONFIG` causes initialized repositories to fail `Doctor.check_model` before a global user configuration is created.
- **Solution:** In `ticket_runner.py:create_parser`, declare top-level `--config` with `default=None` and subparser `--config` flags with `default=argparse.SUPPRESS` so `main()` can cleanly detect when `--config` is explicitly specified by the user (overriding `project_config_path` while still merging over global configuration). In `ProjectScaffolder.scaffold`, fallback empty detected test commands to `"python -m pytest"` so generated overlays are immediately valid and executable on Windows PATH. In `DEFAULT_MACHINE_CONFIG`, seed baseline default models (`deepseek/deepseek-chat` and `qwen/qwen-plus`) matching `config.example.yaml` so two-tier pre-flight checks pass cleanly out of the box.

---

## Evidence Triage ANSI Stripping, Bounded Excerpts & Dynamic Enum Annotation

- **Problem:** Verification and harness logs can contain multi-megabyte transcripts, terminal color escape codes, and binary noise. Dumping raw logs into Worker prompts rapidly blows up LLM context budgets, while truncating characters before stripping ANSI codes miscalculates token size and risks slicing escape sequences mid-byte. Furthermore, standard Python `Enum` singletons cannot attach runtime instance attributes (like rejection reasons) without mutating global enum state across concurrent checks.
- **Solution:** In `EvidenceTriage`, isolate the first failing test and error trace, strip ANSI escape sequences before bounding to `<=` 30 lines and `<=` 1,000 characters, and write `summary.json` atomically via `atomic_write_text`. In `ApprovalDecision`, implement a pure callable clone pattern (`ApprovalDecision.REJECT(reason="...")`) using `object.__new__` with custom `__eq__` and `__hash__`, preserving enum member identity while carrying immutable decision reasons. Defensively validate ticket IDs in `RuntimePaths.evidence_dir(ticket_id)` against `TICKET_ID_PATTERN` to block path traversal.

---

## ApprovalGateway Async Protocol Port & Fake Test Double Exhaustion Fail-Fast

- **Problem:** Human verification adapters (both interactive terminal prompts and Discord bot notifications) perform asynchronous I/O (blocking stdin, event waits, or network dispatches). Defining synchronous port methods would block the event loop or require threading workarounds. Additionally, if test doubles silently return `None` or default approvals when scripted decisions run out, tests with configuration bugs or runaway approval loops can pass erroneously or loop indefinitely.
- **Solution:** Define `ApprovalGateway` with an `async def request_approval(card: EvidenceCard) -> ApprovalDecision` method marked with `@runtime_checkable Protocol`. In `FakeApprovalGateway`, store scripted decisions in a list, record all incoming `EvidenceCard` instances in `.received_cards`, and raise `IndexError` immediately if `request_approval` is invoked with no remaining decisions, ensuring test setups fail fast.

---

## Gatekeeper Human Approval Fail-Closed Authorization, EvidenceCard Sourcing & Rejection Prompt Sanitization

- **Problem:** When introducing a human approval gate to `VerificationLoop`, naive implementations risk leaking commits if verification passes while the approval gateway is unconfigured, or if an unexpected/null decision is received. In addition, sourcing smoke scenarios from ephemeral signals rather than parsed ticket markdown causes inconsistencies between what the human verified and what was specified. Furthermore, un-sanitized operator rejection feedback passed directly into worker prompts can leak secrets or inject adversarial directives, while unbounded feedback can degrade worker context tokens.
- **Solution:** In `VerificationLoop`, enforce strict fail-closed authorization: in `"human"` mode, no commit or pass result is reachable without an explicit `ApprovalDecision.APPROVE`; missing gateways, unhandled decisions, or operator errors raise `UserAbortError` immediately. Source `smoke_scenarios` on `EvidenceCard` directly from the ticket's parsed markdown (`Ticket.smoke_scenarios`). Sanitize operator rejection reasons in `_format_rejection_hint` by stripping ANSI escape sequences, masking secret tokens/passwords, bounding text to `<= 400` characters and `<= 15` lines, and framing the hint cleanly as operator feedback for the worker retry prompt.

---

## Terminal Approval Rich Markup Escaping, Width Clamping, Dual Async/Sync Execution & Stream Buffering

- **Problem:** When rendering interactive verification approval cards with Rich, raw square-bracket hotkey prompts like `[y]`, `[n]`, and `[d]` are treated as Rich markup style tags and stripped from the terminal display. In addition, long unbroken evidence paths can overflow console borders on narrow terminals. When called from synchronous components (like `TerminalDisplay`), calling `asyncio.run()` directly inside an active event loop raises `RuntimeError: This event loop is already running`. Furthermore, when feeding keystrokes and rejection feedback through stdin streams (e.g. `"n\ntests look flaky\n"`), reading the single key leaves a trailing newline in the stream buffer, causing the subsequent `readline()` for rejection reason to return an empty string.
- **Solution:** In `TerminalApprovalAdapter.render_card`, escape Rich markup brackets as `\\[y]`, `\\[n]`, and `\\[d]`, and wrap text lines with `overflow="fold"` so long evidence paths fold safely within the clamped console width. In `request_approval_sync`, check `asyncio.get_running_loop()`; if a loop is already running, delegate execution to a `concurrent.futures.ThreadPoolExecutor` to run `asyncio.run()` safely without clashing with the active event loop. In stream key reading, peek and consume any immediate following newline character so subsequent `_read_line` calls receive the operator's actual feedback.

## Discord Approval Interaction Mock Truthiness, Thread Scoping & Secret Scrubbing

- **Problem:** When testing `discord.Interaction` responses, querying `interaction.response.is_done()` on a `MagicMock(spec=discord.Interaction)` returns a child `MagicMock` which is truthy in Python (`bool(mock) == True`). Naively checking `if resp.is_done():` causes adapters to always route to `followup.send` rather than `response.send_message`, breaking assertions and failing response dispatch in unit tests. Furthermore, slash command interactions `/approve` and `/reject` can be invoked from any channel or by unauthorized users, requiring strict origin thread and `notify_user_id` verification before returning approval decisions. Finally, Discord embed constraints (≤4,096 char description, ≤1,024 char per field, ≤25 fields) and secrets in environment variables require preemptive scrubbing and truncation before posting.
- **Solution:** In `_send_interaction_response`, inspect `resp.is_done()` return type, treating `MagicMock` instances as `False` unless explicitly configured as a boolean, and fall back from `send_message` to `followup.send` if `discord.InteractionResponded` is raised. In `DiscordApprovalAdapter`, validate channel IDs against target thread IDs and caller user IDs against configured `notify_user_id` (rejecting unauthorized attempts with ephemeral error messages). Preemptively scrub environment secrets matching sensitive keys (`TOKEN`, `KEY`, `SECRET`) and enforce strict Discord limits (≤4,096 char description, ≤1,024 char field values, ≤25 fields) in `build_evidence_card_embed`.

---

## Verification Skill Scaffolder Meta-Skill & Feature Map 4-Section Contract

- **Problem:** Agent-oriented verification meta-skills must provide clear, actionable instructions for detecting polyglot surfaces (Playwright for Web, PTY/subprocess for CLIs, curl/HTTP for APIs) without generating python runtime code or overfilling context windows. If the feature map template is underspecified or exceeds token budgets, subsequent agents create sprawling, unmaintainable test plans that blow up context on verification failures.
- **Solution:** In `create-verification-skill/SKILL.md`, define explicit surface detection heuristics anchored against `ProjectSniffer` patterns, a strict 5-step lifecycle (`Launch` → `Doctor` → `Drive` → `Evidence` → `Cleanup`), and stub comment documentation requirements for all 4 harness scripts. Enforce the feature map contract strictly across both `create-verification-skill` and `maintain-verification-skill`: exactly 4 required sections (`### Sub-features`, `### User POV Path`, `### Driving Harness`, `### Gotchas`) with a hard ceiling of ≤40 lines per feature file. In `maintain-verification-skill/SKILL.md`, provide an actionable 5-step audit process to prune orphaned features and scaffold uncovered surfaces.

---

## Spec 13 Alignment Audit & Living Documentation Synchronization

- **Problem:** When auditing living documentation (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`, `README.md`) against implemented specifications, forward-declared or newly introduced modules (such as `evidence.py`, `approval.py`, `terminal_approval.py`, test doubles, and verification meta-skills) can be omitted from directory trees or glossary entries, causing subtle drift between actual code and agent navigation guidance. Furthermore, status flags in roadmap tables and adapter environment notes in `AGENTS.md` can remain marked as planned or unimplemented, misleading subsequent agents and operators.
- **Solution:** Execute automated cross-checks comparing filesystem paths against `ARCHITECTURE.md` directory listings, verify glossary terms and `_Avoid_` synonym blocks in `CONTEXT.md` using deterministic regex sweeps, and systematically update implementation statuses and roadmap tables across `AGENTS.md` and `README.md`. Maintaining exact correspondence between code, tests, and living documentation ensures zero-guesswork agent navigation across future specification cycles.

---

## Discord One-Shot Notification Lifecycle & Token Redaction Guardrails

- **Problem:** Executing a one-shot notification CLI command (`ticket_runner.py notify <msg>`) without an injected gateway requires establishing a minimal connection with `discord.py`'s client (`client.start()`) to authenticate the HTTP session before resolving channels and posting messages. Awaiting readiness indefinitely or failing to handle errors can hang the CLI process. Furthermore, if network or Discord API exceptions happen to contain the secret bot token, echoing raw exceptions to stderr would compromise bot credentials.
- **Solution:** In `run_notify`, await `client.ready_event.wait()` with a 30-second timeout guard, inspect `client.ready_error` for fast failure reporting, and ensure `client.close()` and task cleanup unconditionally execute in a `finally` block. Defensively sanitize all error outputs by redacting `token_val` if present in exception strings, and validate that `channel_id` is a numeric snowflake before initiating connection tasks.

---

## Domain Scenario Data Rip & Legacy Unknown-Key Tolerance at the Signal Boundary

- **Problem:** Removing the smoke scenario data path from `Ticket` and `ReadySignal` risks runtime crashes when loading historical ticket markdown files or processing in-flight ready signals that still include legacy `manual_verification` payloads. If `ReadySignal.parse` strictly enforces a schema without unknown-key tolerance, legacy signals from earlier specifications or other workers cannot be loaded. Furthermore, downstream components like `Gatekeeper` and `TicketProcessor` that access `ready_signal.manual_verification` or `ready_signal.manual_verification_is_default` directly will raise `AttributeError` when those fields are deleted from domain dataclasses.
- **Solution:** Remove `smoke_scenarios` from `Ticket` and remove `_parse_smoke_scenarios` from `TicketMarkdownParser`, treating `### Smoke Scenarios` sections as inert ignored text. Remove `manual_verification` from `ReadySignal` dataclass and validator; decode payloads purely through required fields so extra/legacy keys like `manual_verification` pass through tolerated without error. In `Gatekeeper` and `TicketProcessor`, defensively guard legacy scenario access with `getattr(..., "manual_verification", ())` and `getattr(..., "manual_verification_is_default", True)` during intermediate migration states. In `PromptBuilder`, filter legacy invariant lines and instruct the human-driven `/live-qa` discipline directly.

---

## Evidence Card Scenario Rip & Surviving Field Limits Clamping

- **Problem:** Removing smoke scenarios from `EvidenceCard` and approval adapters (`TerminalApprovalAdapter`, `DiscordApprovalAdapter`) risks breaking shared field limit enforcement and secret redaction. In Discord approval embeds, scenario checklist rendering previously drove multi-field pagination (`Smoke Scenarios (cont. N)`) alongside 1024-character value truncation and 25-field caps. Stripping the scenario loop could accidentally remove the 1024/25 limit enforcement on surviving fields (`Evidence Paths`, `Test Status`, `Harness Status`) or miss secret scrubbing on paths. In `Gatekeeper`, dropping scenario sourcing, checklist printing, and commit-body injection must not bypass the fail-closed human approval gate (`ApprovalDecision.APPROVE` required to proceed).
- **Solution:** In `runner/adapters/discord/approval.py`, remove only the scenario formatting loop and field-chunking closure while retaining the 1024-character truncation on `Evidence Paths`, secret scrubbing (`_scrub_secrets`), and the final `fields[:MAX_DISCORD_FIELDS_COUNT]` clamp. In `EvidenceCard`, eliminate `smoke_scenarios` while preserving immutable tuple coercion for `evidence_paths`. In `VerificationLoop`, strip out `_append_smoke_log`, scenario fallback sourcing, warning logs, and commit-body injection while keeping the fail-closed human approval decision gate completely intact.

---

## Living Document Alignment for Human-Driven Live-QA & Invariants Mirroring

- **Problem:** When replacing an automated or worker-generated verification discipline (smoke scenarios) with a human-driven verification ritual (`/live-qa`), living documents (`AGENTS.md`, `README.md`) can retain stale instructions commanding agents to author, echo, or log scenarios. Because `PromptBuilder` dynamically extracts invariants from `AGENTS.md` under `## Invariants`, any leftover scenario rules in `AGENTS.md` silently re-inject obsolete completion gates into future worker prompts.
- **Solution:** Re-point `AGENTS.md` and `README.md` at the `/live-qa` verification contract using surgical edits guided by `/writing-for-agents` principles: front-load leading words (`live-qa`, `Evidence Card`, `Gatekeeper`), state target human verification behavior positively, explicitly state log path (`.agent/live-qa_log_<slug>.md`) and refusal-in-absence semantics, and ensure no lines command agents to author, embed, echo, or log scenarios. Verify with case-insensitive pattern searches that only legitimate survivors (such as transport checks or recovery skills like `/smoke-fail`) remain.

---

## Skill Catalog Retargeting & Vendor Sync Guardrails

- **Problem:** When re-targeting skill catalogs (`smoke-fail`, `to-tickets`, `implement`) from legacy smoke-scenario mechanisms to human-driven verification (`/live-qa`), unit tests like `test_smoke_fail_recovery_skill_ticket_runner_template_is_valid` that dynamically parse skill markdown templates will fail if their assertions expect legacy section headings or requirements text. Additionally, syncing skills to external catalogs (`Viello/agent-skills`) requires careful handling of project-specific queue sections without introducing personal paths or leaking internal references.
- **Solution:** Align parser unit test assertions with the updated live-qa regression ticket template (`# T<NNN> — Regression: <Scenario Title>` and live-qa session reference). Apply `/writing-for-agents` principles to frame requirements positively without prescriptive negative phrases. Ensure identical synchronization between vendored skills in `.agents/skills/` and the canonical `Viello/agent-skills` repository, verifying that public repos contain clean, portable Markdown without internal paths or personal environment leaks.

---

## Spec 14 Closing Alignment Audit, Glossary Synchronization & Living Document Parity

- **Problem:** When retiring legacy verification mechanisms (smoke scenarios) across multiple implementation tickets, residual references can linger in secondary documentation (`ARCHITECTURE.md` directory trees, Spec "migration overlap" notes, and `CONTEXT.md` glossary definitions). Deleting obsolete glossary entries outright violates the repository rule that historical entries must be marked superseded rather than deleted, while leaving them active misleads future agents into generating dead artifacts.
- **Solution:** In `CONTEXT.md`, retain `Smoke Scenarios (Superseded)` while introducing `Live QA Session` with explicit `_Avoid_` synonyms (`Smoke test session`, `manual testing`, `human verification run`, `smoke run`). In `ARCHITECTURE.md`, synchronize CLI entry points to include `bot` and `notify`, and update the runtime state tree from `smoke_log_<spec-slug>.md` to `live-qa_log_<spec-slug>.md`. In Spec 14 (`docs/specs/14-live-qa-replacement.md`), retire the "migration overlap" note now that both code, signals, adapters, and prompt invariants fully operate under the unified live-qa verification discipline.

---

## Antigravity CLI Empirical Surface Rewrite & Session ID Allowlist Relaxation

- **Problem:** Prior to T018, the Antigravity worker adapter (`runner/adapters/antigravity/antigravity_worker.py`) was coded against an imagined CLI surface (`agy run --auto <prompt> [--session <id>] [-m <model>] [--variant <reasoning>]`). When invoked on a real `agy` binary (v1.2.16+), every run failed with exit code 2 (`Error: unexpected argument "run"`). Furthermore, `agy`'s NDJSON output stream uses a closed 3-event vocabulary (`init`, `step_update`, `result`), token telemetry is nested under `step_update.usage` and `result.usage` with wire keys (`input_tokens`, `output_tokens`, `thinking_tokens`, `cache_read_tokens`, `cache_write_tokens`, `total_tokens`), tool arguments are structured under `step_update.tool_info.parameters`, and conversation IDs are emitted as UUIDs (`conversation_id`). The runner previously enforced an OpenCode-specific regex `SESSION_ID_PATTERN = re.compile(r"^ses_[A-Za-z0-9]+$")` in `runner/domain/runtime_paths.py`, causing valid Antigravity conversation UUIDs to be rejected by `safe_session_paths`, which silently skipped log creation.

---

## Antigravity Live Smoke Integration & Empirical JSONL Envelope Assertions

- **Problem:** Until T003, Antigravity integration had no live integration test counterpart to `tests/unit/adapters/test_live_opencode_smoke.py`. Unit tests mock the event stream, leaving the real `agy` subprocess execution untested against upstream CLI format breaks or argv changes. Furthermore, the empirical output stream format emitted by `agy -p ... --output-format stream-json` differs fundamentally from OpenCode's flat envelope: it uses a closed set of 3 event types (`init`, `step_update`, `result`), and session identifiers appear as `conversation_id` rather than `sessionID`.
- **Solution:** Add `tests/unit/adapters/test_live_antigravity_smoke.py` gated strictly on `TICKET_RUNNER_LIVE=1` using `pytestmark = pytest.mark.skipif(...)`. The smoke test resolves the binary respecting `AGENT_ANTIGRAVITY_BIN` before falling back to `shutil.which("agy")`, spawns the process via `SubprocessRunner.spawn` using the canonical headless flags (`-p`, `--output-format stream-json`, `--print-timeout 0`), isolates file system mutations to pytest's `tmp_path`, and asserts that stream events parse as JSON, include `conversation_id`, and exhibit the closed event vocabulary (`init`, `step_update`, or `result`).



---

## Worker Binary Env-Var Override Resolution in Doctor

- **Problem:** `Doctor._check_worker_binary` resolved `agy` / `opencode` by literal name only, so users with non-PATH installs (mise, asdf, pipx, custom dirs, CI) could not pass pre-flight. A naive override that silently falls back to PATH when the override path is wrong hides misconfiguration, and tests that construct `Doctor` without `env=` inherit `os.environ` and break on hosts where the override is exported.
- **Solution:** Resolution priority is (1) `AGENT_ANTIGRAVITY_BIN` / `AGENT_OPENCODE_BIN` env-var, then (2) `path_resolver(binary)` (`shutil.which`). When the env-var is set it must point at an existing executable file (`os.path.isfile` + `os.access(X_OK)`); otherwise the check fails with `"<VAR> is set to '<path>' but that path does not exist or is not executable."` and PATH is NOT consulted. The OpenCode branch runs `<override> --version` via `check_opencode(binary=...)`. Tests covering override behaviour pass `env={}` / `env={...}` explicitly for determinism. Worker adapters still spawn the literal `agy` / `opencode` names; the override currently affects Doctor pre-flight only.


---



## Pre-Push Hook Installer CLI Naming & Classmethod Re-use

- **Problem:** External scaffolding tools and shell users need to install the pre-push guardrail into `.git/hooks/pre-push` without fragile inline Python snippets. Naming the CLI argument `--target-dir` caused ambiguity between the target project root and its `.git/` subdirectory, and conflicted with the underlying `PrePushHookInstaller.install(git_dir=...)` parameter naming.
- **Solution:** Name the CLI argument `--git-dir <path>` consistently with the adapter classmethod, explicitly pointing to the `.git/` directory. Expose `main()` and execute via `python -m runner.adapters.git.pre_push_hook install --git-dir <path>`, delegating idempotency, template fallback (`DEFAULT_STANDALONE_HOOK`), and permission management directly to `PrePushHookInstaller.install()` without duplicating hook text or logic.

---

## Scaffold Sandbox Force Reset Semantics & Runtime State Preservation

- **Problem:** When resetting or re-scaffolding an onboarding sandbox (such as `D:\Sandbox\ticket-runner-live-target\`) using `--force`, a naive wipe would delete `.git/` (destroying commit history, branch configuration, and installed hooks) and `.agent/` (destroying runtime state such as active session logs, checkpoints, evidence, and durable signals). Furthermore, unconditioned execution on non-empty directories risks accidental data loss in interactive sessions.
- **Solution:** In `runner.tools.scaffold_sandbox`, `--force` selectively wipes only source-tree files (`AGENTS.md`, `ticket-runner.yaml`, `.agents/`, `docs/`, `src/`, `tests/`, `.gitignore`) while strictly preserving `.git/` and `.agent/`. In interactive mode without `--non-interactive`, prompt the operator for explicit confirmation before wiping. Auto-configure git identity (`ticket-runner-scaffold <noreply@local>`) locally only if `git config user.name` returns empty, preserving global operator identity.

---

## External Sandbox Scaffold Verification & One-Shot Initial Commit Exception

- **Problem:** Target project onboarding sandboxes require an initial git commit on `agent/ticket-runner` to establish a clean git tree before any worker or gatekeeper runs. Because `AGENTS.md` enforces "Gatekeeper alone commits", naive adherence would create a chicken-and-egg deadlock where no initial commit exists for the gatekeeper to branch or diff from. Furthermore, verification commands (`doctor`, `test_cmd`) executed via `--project-dir` must resolve tools against the target project environment rather than the runner repository.
- **Solution:** Permit `runner.tools.scaffold_sandbox` to author the initial baseline commit (`chore(sandbox): initialize ticket-runner onboarding sandbox`) as a documented one-shot bootstrap exception to ADR 0002. Re-invoking `scaffold_sandbox` without `--force` operates idempotently (0 files generated, preserving existing commit and branches), while `--project-dir <target>` runs pre-flight doctor checks and queue discovery seamlessly against external targets.

---

## Scaffold Output Sanitization, Spec Path Placeholders & Upstream ADR Drift

- **Problem:** When vending project files (`AGENTS.md`, welcome ticket) to an external sandbox target, host-specific `(ADR NNNN)` citations dangle or collide with target repository ADRs, while ticket frontmatter referencing nonexistent `docs/specs/<name>.md` paths causes confusion. However, deleting `Spec:` entirely violates `runner/domain/ticket.py:68` (`spec_path must be a non-empty string`) and triggers fallback parsing in markdown adapters. Furthermore, if `scripts/sync_agents_md.py` does not sanitize upstream invariant text before drift comparison, a sanitized sandbox copy will falsely report permanent drift against upstream. In addition, changing root invariant text without updating assertions in `PromptBuilder` tests causes invariant inlining regressions.
- **Solution:** Route all scaffold write sites through `runner.tools.sanitize.apply_sanitization` keyed by `file_kind`. For `agents_md`, strip `\s*\(ADR\s*\d{4}\)` while leaving terminating punctuation intact. For `welcome_ticket`, replace `docs/specs/[\w.-]+\.md` with a non-empty placeholder string (`N/A (sandbox demo)`) to satisfy domain validation. In `sync_agents_md.py`, sanitize `upstream_curated` prior to in-sync comparison as well as formatted output before writing. Keep root `AGENTS.md` ADR references intact while abstracting multibackend invariant wording, and align prompt builder inlining tests to match updated invariant text.
---

## All-Mode Public Skill Catalog Enumeration, Path Translation & Network Fallback

- **Problem:** In `all` skill mode, the public skill catalog repository (`https://github.com/Viello/agent-skills`) structures skills at the repository root (`<skill>/SKILL.md`), whereas the sandbox expects `.agents/skills/<skill>/SKILL.md`. Additionally, downloading the public catalog over the network introduces a potential runtime point of failure during sandbox scaffolding when offline or behind a proxy, and a naive implementation without a local directory override makes hermetic testing impossible.
- **Solution:** Fetch the published tarball (`archive/refs/heads/main.tar.gz`) in memory via standard library `urllib.request` and inspect archive members matching `<archive-root>/<skill>/SKILL.md` (exactly 3 path components), translating the root layout into sandbox `.agents/skills/<skill>/SKILL.md` while streaming directly through `apply_sanitization`. Plumb `--source-skills-dir` through both `scaffold()` and the CLI to bypass network requests for hermetic testing and offline operation. On network or extraction failures, warn and gracefully fall back to shipping the four curated default skills (`implement`, `code-review`, `diagnosing-bugs`, `handoff`), logging the count and fallback status without crashing.

---

## Doctor Provider Resolution Under Single-Tier Config Load & Discord `token_env` Requirement

- **Problem:** `Doctor._check_worker_binary` resolves `worker.provider` by calling `YamlConfigLoader.load(<project>/ticket-runner.yaml)` (single-tier) because it runs before `check_config` performs its two-tier merge. The T005/T007 scaffold overlay emits a `discord:` block containing only `enabled: false` and omits `token_env`, which `load_from_dict` requires (`Missing required field 'token_env' in section 'discord'`). The loader raises, `_get_worker_provider` swallows the exception, and the provider silently defaults to `"opencode"`. Result: live-test sites configured `worker.provider: "antigravity"` (external sandbox and in-repo harness alike) print `OpenCode CLI available (...)` instead of verifying `agy`, and never exercise `AGENT_ANTIGRAVITY_BIN`.
- **Solution:** In `Doctor._load_configuration`, load and cache the configuration via two-tier resolution (`self._config_loader.load_two_tier`) with fallback to single-tier `self._config_loader.load`, shared across `_get_worker_provider`, `check_config`, and `check_discord`. In `_get_worker_provider`, only fall back to the default `"opencode"` provider when no project configuration file exists on disk (preserving missing-config pre-flight test expectations). When an existing config file is genuinely broken or unloadable, return `None` so `_check_worker_binary` skips cleanly without masquerading as `opencode`, allowing `check_config` to surface the root validation error. In `runner/tools/scaffold_sandbox.py`, emit `discord.token_env: "DISCORD_BOT_TOKEN"` by default in `TICKET_RUNNER_YAML_TEMPLATE` to fix sandbox overlays at the source.

---

## Empty-Starter "Pure Empty" Requires a Bootstrap Commit to Track `.gitkeep`

- **Problem:** T009's locked *Pure Empty* design lists `.gitkeep` as "the sole tracked file", but never states that a commit must be authored. Without one, `git init -b main` + `git checkout -b agent/ticket-runner` leaves `.gitkeep` untracked and the tree dirty, so the file is not actually "tracked" and the scaffold commit that T010's acceptance criteria look for does not exist.
- **Solution:** After `git init -b main`, `git checkout -b agent/ticket-runner`, and installing the pre-push guardrail via `python -m runner.adapters.git.pre_push_hook install --git-dir <starter>/.git`, author one bootstrap commit on `agent/ticket-runner` (`chore(starter): initialize empty ticket-runner fresh-slate target`) staging only `.gitkeep`. `main` stays unborn (no commit), exactly as `runner.tools.scaffold_sandbox` leaves it — only `agent/ticket-runner` appears in `git branch`. This mirrors the one-shot bootstrap commit used by the external sandbox (T006) and in-repo harness (T008) scaffolds — see the "External Sandbox Scaffold Verification & One-Shot Initial Commit Exception" entry above — because T009 also left the commit unstated.

---

## `python -m` RuntimeWarning When the Package `__init__` Imports the CLI Module

- **Problem:** Running `python -m runner.adapters.git.pre_push_hook install --git-dir <path>` prints `RuntimeWarning: 'runner.adapters.git.pre_push_hook' found in sys.modules after import of package 'runner.adapters.git', but prior to execution of 'runner.adapters.git.pre_push_hook'`. `runner/adapters/git/__init__.py` eagerly imports `PrePushHookInstaller` from the same module being executed by `runpy`, so the module is already in `sys.modules` before `-m` executes it. The hook still installs correctly; the warning is noise, but it recurs for any `-m`-invoked CLI whose package `__init__` imports that module.
- **Solution:** Treat the warning as benign for hook installation (the scaffold tool shells out to this CLI and only inspects the exit code). If silencing is desired, drop the eager `from runner.adapters.git.pre_push_hook import PrePushHookInstaller` re-export from `runner/adapters/git/__init__.py` or guard it (`if __name__ != "__main__":`), importing the class lazily at call sites.

---

## `ticket-runner init` Uses `ProjectScaffolder`, Not `scaffold_sandbox` — Outputs Diverge

- **Problem:** `run_init` (`ticket_runner.py`) calls the lightweight `ProjectScaffolder` (`runner/adapters/cli/scaffolder.py`), **not** the comprehensive `runner.tools.scaffold_sandbox`. The two scaffolds produce different trees: `ProjectScaffolder` omitted `AGENTS.md`, the welcome ticket, `src/sample_app/`, `tests/test_smoke.py`, and the `.agent/logs/` + `.agent/evidence/` runtime dirs, and its fresh `.gitignore` carried only `.agent/`. T009's *Pure Empty* design ("run `ticket-runner init` and watch every artifact scaffold") assumed `init` produced the full sandbox tree, so Live-QA Scenario B failed against that expectation.
- **Solution:** Upgrade `ProjectScaffolder.scaffold` in place to emit the runnable artifacts, the two runtime dirs, and the fuller `.gitignore` (reusing `scaffold_sandbox`'s shared content constants and a new `build_agents_md_content` helper). **Do not** delegate `init` to `scaffold_sandbox.scaffold` directly: `ProjectScaffolder`'s exact-equality `ticket-runner.yaml` test pins heuristic fields (`name`/`provider`), while `scaffold_sandbox` hardcodes the sandbox name/provider and authors a git commit — neither of which `init` should do (T009: "Scaffold output is never committed"). Note the two tools' intentional divergences: `init` keeps full-catalog skills + heuristic provider and never commits; `scaffold_sandbox` ships 4 curated skills, pins `antigravity`, and commits.

---

## Agent-Skills Driver Minimal-Stub Discipline & `--project-dir` CLI-Only

- **Problem:** The agent-skills driver at `D:\Repos\agent-runner-driver\` is the live-test seat from which the user invokes `ticket-runner` against the skills clone. If the driver carried its own `ticket-runner.yaml`, `.agent/`, or `docs/tickets/`, a `ticket-runner start` invoked from the driver's CWD without `--project-dir` would silently pick those up — drifting the worker provider, scanning empty signal directories, and quietly running against the wrong Target Project. The T015 scaffold (per Spec 15 ticket T015) originally listed `ticket-runner.yaml` / `.agent/` / `docs/tickets/` creation, mirroring the T006/T008 bootstrap shape and ignoring the `runtime_paths` rule that `.agent/` belongs to the Target Project, not the invocation seat.
- **Solution:** Per T013's locked resolution, the driver carries no file the runner parses. Its only contents are `git/`, the pre-push hook, `.gitignore` (defensive), the initial scaffold commit, and `scripts/start.ps1` (which hard-codes `--project-dir D:\Repos\agent-skills` so the wrapper always scopes the runner to the skills clone). `YamlConfigLoader` schema remains unchanged — there is no YAML `project_dir:` key; the path is the CLI flag exclusively. T015 was amended to drop the three dead creation lines and to add the `scripts/start.ps1` requirement. Bootstrap is `pwsh D:\Repos\agent-runner-driver\scripts/start.ps1`; if `pwsh` is unavailable on a given Windows host, surface a fallback `scripts/start.bat` (cmd.exe shim) or pure-Python `scripts/start.py` to avoid silent wrapper failures.

---

## Agent-Skills Upstream HEAD Advance, Missing Root `.gitignore` & Pre-Push Hook Wiring

- **Problem:** The upstream repository `Viello/agent-skills` on `main` advanced to commit `727a94f` after publishing the 45-skill catalog (advancing past chart-time SHA `e4eb54c`). Upstream `Viello/agent-skills` does not contain a root `.gitignore`. Without adding `.agent/` and `docs/tickets/.queue.lock` into `.gitignore` on the target `agent/ticket-runner` branch, running ticket executions against `D:\Repos\agent-skills` would leave runner runtime state and queue locks untracked or risk polluting git status. Furthermore, Windows systems using `py -3` (or without standard `python` on PATH alias) require executing the pre-push hook installer CLI with `py -3 -m runner.adapters.git.pre_push_hook install --git-dir <path>`.

---

## Agent-Skills Driver Scaffolding, Python Launcher Execution & Queue Pre-Flight State

- **Problem:** On Windows environments where default `python` is an unaliased Microsoft Store execution alias or points to an inactive environment, bootstrap scripts invoking bare `python` fail silently or prompt store installations. Additionally, invoking Doctor against an upstream clone (`D:\Repos\agent-skills`) from the newly scaffolded driver (`D:\Repos\agent-runner-driver`) verifies git cleanly on `agent/ticket-runner`, but reports a missing tickets directory because `docs/tickets/` has not yet been seeded in the upstream repository.
- **Solution:** In `scripts/start.ps1`, detect `py` launcher availability via `Get-Command py` and prefer `py -3` with graceful fallback to `python`, adding an accompanying `scripts/start.bat` for cmd.exe execution. Confirm `Doctor` recognizes the driver's `--project-dir D:\Repos\agent-skills` target as a valid git repository on `agent/ticket-runner`, while noting that queue pre-flight failures are expected until T016/T017 decisions seed the demo queue in `agent-skills`.

---

## Antigravity `--print-timeout` Truncated Every Worker Turn into an Empty SUCCESS Result

- **Problem:** The Antigravity adapter hard-coded `DEFAULT_PRINT_TIMEOUT = "5s"` (`runner/adapters/antigravity/antigravity_worker.py`) and appended `--print-timeout 5s` to **every** `agy` invocation. `agy --help` documents the flag as *"Optional time limit for print mode; 0 waits until the turn completes (default 0s)"*, so the Runner replaced agy's safe default with a 5-second ceiling. When a turn outran the ceiling, agy printed `[agy] print timeout after 5s with turn in progress; returning partial output` and still exited 0 with a well-formed envelope whose `result` was `status: SUCCESS`, `response: ""`, and all-zero `usage`. Every real Worker turn runs for minutes, so **no** Antigravity Worker turn could complete - yet nothing raised: the failure was silent and SUCCESS-shaped, and the only tell was zero token usage (`tokens.current: 0`, `Token budget: 0 / 150,000`). The Runner then escalated via the default `bug_escalation_at: 1` and blocked on an interactive prompt, which read to the operator as "running but nothing happening".
- **Solution:** Set `DEFAULT_PRINT_TIMEOUT = "0"` to restore agy's "wait until the turn completes" semantics. Any positive value is an agy-side ceiling that cannot be safe here; the Runner already supervises the subprocess, so a wall-clock ceiling belongs there, not inside agy. Add a regression test at the adapter seam that runs the real `build_antigravity_run_command(...)` argv and asserts a non-empty `response` with non-zero `usage.total_tokens` - it goes red on `5s` and green on `0`. Because a zero-usage SUCCESS result is otherwise indistinguishable from a productive empty turn, the adapter now marks such a `result` (SUCCESS, empty response, and zero-or-absent usage) with a `WorkerEvent.anomaly` diagnostic that the supervisor records and notifies immediately, so the next occurrence surfaces in seconds rather than as a late escalation. This supersedes the `--print-timeout 5s` canonical-flag value recorded in the earlier T003 gotcha.

---

## Rich Live Display Swallows / Hides Interactive Terminal Prompts (`input()`)

- **Problem:** When `RichTerminalDisplay` is active (`rich.live.Live` running in the terminal), invoking Python's standard `input(prompt)` or `sys.stdin.readline()` from intervention or escalation gateways (e.g. `TerminalInterventionGateway.prompt_escalation` calling `Run /diagnosing-bugs? [Y/n]`) results in invisible prompts. The Live display layout buffers and continuously redraws over standard output, suppressing or displacing the prompt text so the user sees a frozen dashboard with no visible prompt. The user only discovers the prompt text after blindly typing and pressing Enter. Furthermore, if subsequent prompts or failure handlers are reached while Live remains unpaused, the process hangs waiting for keystrokes that the user cannot see.
- **Solution:** Before prompting the human for interactive terminal input, `TerminalInterventionGateway._read_line`, `HandoffCoordinator.default_recovery_confirmation`, and `TerminalApprovalAdapter.request_approval` suspend/stop the active `RichTerminalDisplay` context (`display.stop()`), execute the prompt and read input cleanly against standard terminal streams, and then resume the display (`display.start()`) in a `finally` block. Container dependency injection wires `resolved_terminal_display` to the intervention gateway, approval adapter, and handoff coordinator.

---

## Antigravity CLI Conflict Between `--model` and `--effort` Flags

- **Problem:** When launching the Antigravity Worker with an explicit model ID that embeds its reasoning effort tier (e.g. `gemini-3.8-flash-high`, `gemini-4-argon-medium`, `claude-sonnet-5-5-high`) on a ticket whose frontmatter defines `Reasoning: medium`, `AntigravityWorker.build_run_command` appends both `--model <model>` and `--effort <variant>` to `agy.exe`. `agy` rejects this with a fatal CLI argument conflict (`error: invalid model selection (--model "gemini-3.8-flash-high" --effort "medium"): --model gemini-3.8-flash-high conflicts with --effort=medium`) and exits immediately with code 1. This triggers `HandoffCoordinator`'s emergency recovery prompt `default_recovery_confirmation` (`Synthesize emergency checkpoint and resume with a fresh session? [Y/n]`), which in turn calls unpaused `input()` under `RichTerminalDisplay`, silently hanging the Runner on startup with zero visible output.
- **Solution:** In `runner/adapters/antigravity/antigravity_worker.py:build_antigravity_run_command`, inspect `model_id`. When both `model_id` and `variant` (effort) are present, strip any embedded effort suffix (`-high`, `-medium`, `-low`, `-xhigh`, `-max`) from `model_id` so that `agy.exe` receives the base model family (e.g. `--model gemini-3.8-flash`) along with the requested reasoning effort flag (e.g. `--effort medium`) without argument conflict. If no effort variant is requested, the configured model identifier is preserved as-is.


---

## Windows Gatekeeper Shell Command Quoting (`list2cmdline` Quote Corruption)

- **Problem:** Spawning Windows verification commands (`verification.test_cmd` / `verification.build_cmd`) via `asyncio.create_subprocess_exec("cmd.exe", "/d", "/s", "/c", command)` routes arguments through Python's `subprocess.list2cmdline` serializer. `list2cmdline` wraps arguments in outer quotes and converts every embedded double quote (`"`) into `\"`. Because `cmd.exe` does not unescape `\"`, child binaries (like `python -c "import glob,yaml; ..."`) receive literal `\"` characters and split tokens on internal whitespace, crashing with `SyntaxError: unterminated string literal` on every verification run. Furthermore, waiting on `SubprocessProcessHandle.wait()` after process termination can raise an unhandled `asyncio.CancelledError` if `_stderr_drain_task` was cancelled, because in Python 3.8+ `CancelledError` inherits from `BaseException` rather than `Exception`.
- **Solution:** In `SubprocessRunner` (`runner/adapters/cli/subprocess_runner.py`), detect Windows `cmd.exe /c` shell commands using `is_windows_cmd_shell(executable, args)` and format an unescaped shell string via `build_windows_cmd_shell_string(executable, args)` (`"{executable}" {switches} /c "{command_str}"`). Spawn it using `asyncio.create_subprocess_shell`, preserving `WindowsJobObject` process-tree assignment, `DEFAULT_STREAM_LIMIT`, and concurrent stderr draining. In `SubprocessProcessHandle`, catch `(Exception, asyncio.CancelledError)` in `_drain_stderr` and `wait()` so process termination cleanly reaps the task without raising `CancelledError`.


---

## Antigravity Token Occupancy, Heartbeat Stall Decoupling & Ready Signal Precedence

- **Problem:**
  1. In `agy`, `step_update.usage.total_tokens` equals `input_tokens + output_tokens`, omitting cached prompt tokens (~35k tokens in typical runs) and reasoning tokens. Populating `TokenUsage.total` from `total_tokens` caused `TokenUsage.occupancy` to under-report context occupancy by ~35k tokens. Conversely, `result.usage` at turn conclusion is the cumulative sum of all per-step usages across the entire turn (e.g. ~175k tokens across 30 steps), which falsely breached the 150k ceiling.
  2. Telemetry and heartbeat stall tracking in `WorkerSupervisor` were tied strictly to OpenCode `step_finish` events with non-None `token_usage`, starving `last_step_time` during long tool call sequences in Antigravity and failing to update `.agent/state.json` or publish status events.
  3. When a Worker emitted a valid `.agent/signals/<ticket_id>_ready.json` before a turn finished, a late budget action (crossing 135k or 150k on the closing step or cumulative result) triggered `KILLED_HANDOFF` or `KILLED_CEILING` and escalated via `run_cycle`, discarding the completed ticket into an emergency handoff or ceiling failure.
- **Solution:**
  1. In `AntigravityWorker._extract_token_usage`, force `total = None` for `step_update` usage events (`is_step_update=True`), enabling `TokenUsage.occupancy` to calculate true context-window occupancy (`input + output + reasoning + cache_read + cache_write`) per ADR 0015. In `WorkerSupervisor.run`, track `step_usage_observed` and suppress feeding cumulative `result.usage` to `BudgetMonitor.observe()` when per-step usage was already seen.
  2. In `WorkerSupervisor.run`, advance `last_step_time` on active tool events (`step_type == "tool"` or `event.type in ("tool_call", "tool_use")`), advance `step_counter` and `last_step_time` on completed steps (`step_finish` or `step_update` with `state in ("DONE", "ERROR")`), and forward active tool invocations to `_ui_event_sink`.
  3. Give valid ready signals on disk precedence over late `KILLED_HANDOFF` and `KILLED_CEILING`: in `WorkerSupervisor.run`, suppress calling `_on_budget_action` when a ready signal is present, and in `HandoffCoordinator.run_cycle`, evaluate ready signal presence before checking CEILING or HANDOFF escalation, immediately returning `SingleCycleStatus.READY`.


---

## Autonomous Ticket Queue Boundary & Idempotent Ticket Finalization

- **Problem:** When an AI coding agent executes tickets under the `implement` skill, unconditional instructions in Step 4 (`Ticket Transition & Gotchas`: updating ticket frontmatter to `Status: completed` and relocating the file to `completed/`) and Step 6 cause autonomous workers to prematurely move the active ticket markdown file before emitting the ready signal. When Gatekeeper verification passes and the human approves the Evidence Card, `DirectoryTicketStore.finalize_completed` looked only for the pending ticket file at `ticket.path`, raising `TicketFormatError: Ticket file not found` and aborting the atomic commit. Furthermore, if `finalize_completed` unconditionally allowed files in `completed/`, callers passing an already-archived path would bypass archive collision guards.
- **Solution:**
  1. In `.agents/skills/implement/SKILL.md`, scope Step 4 to `*(interactive mode only — skip in Ticket Runner autonomous execution; pass new gotchas via the ready signal JSON and let Gatekeeper relocate the ticket)*` and define the full ready Signal schema in Step 6, clarifying that ticket relocation, status updates, and `docs/tickets/gotchas.md` logging are performed exclusively by the Gatekeeper.
  2. In `PromptBuilder.build`, expand Guardrail 1 to `No Git Staging, Commits, or Queue File Mutations`, explicitly forbidding editing `docs/tickets/gotchas.md` directly and modifying, moving, or deleting any Ticket file under `docs/tickets/`.
  3. In `DirectoryTicketStore._resolve_ticket_path`, add `allow_premature_completed: bool = False`. When resolving a ticket that was expected at a pending location but is missing because the Worker prematurely moved it to `<spec_dir>/completed/<ticket_filename>`, return the completed path while still raising `TicketFormatError` if the caller explicitly passed a path already inside `completed/` or if the file is missing from both locations. In `finalize_completed`, resolve with `allow_premature_completed=True`, ensure `.gitkeep` exists, update header metadata in place, and return cleanly.


---

## Target Project Live-Run Sanitization & Queue Reset Conventions

- **Problem:** When an autonomous Queue run is interrupted or halted after an unhandled defect (such as child command quote corruption or premature Ticket file relocation), the Target Project working tree is left in a dirty, inconsistent state: untracked files authored by the Worker, stale `.agent/` state files (`state.json`, `status.json`, diagnostic logs), `.queue.lock` left locked, and pending Tickets moved to `completed/` without Gatekeeper commits. Restarting the Runner in this state causes `CrashRecovery` to either resume against corrupt state, crash on lock timeouts, or skip pending Tickets whose files are missing from the pending Queue directory.
- **Solution:** Before resuming a live Queue run following Runner remediation, sanitize the Target Project back to its clean baseline commit: restore pending Ticket files and gotchas via `git checkout`/`git restore`, purge untracked Worker artifacts and premature `completed/` folders, delete stale lock (`docs/tickets/.queue.lock`) and `.agent/` runtime state files, and verify `git status --porcelain` is clean while preserving human-authored pre-flight predictions (`observations/`). In the Runner, verify that provisioned Worker Skills (like `.agents/skills/implement/SKILL.md`) in the Target Project match the updated Runner definitions without leaking unintended skill catalog files.

---

## Pre-Dispatch HITL Gate State Machine & Prompt Guidance Ingestion

- **Problem:** When a ticket has `mode == "HITL"` or `status == TicketStatus.BLOCKED`, autonomous execution must halt *before* spawning any Worker subprocess. Prior to prompting the human operator, the system must transition the state machine to `WAITING_FOR_USER`, publish a `RunState.WAITING_FOR_USER` status event, update the Discord Status Card, and schedule away escalation. Furthermore, on operator `PROCEED`, operator guidance text must be prepended to the worker's initial prompt without clobbering existing instructions. On operator `SKIP`, the ticket must be finalized as skipped (`**Status:** skipped`) with `**Status note:** Skipped by operator at HITL pre-dispatch gate` without running any worker cycle; and on operator `ABORT`, a `UserAbortError` must immediately abort execution without erroneously recording a circuit-breaker trip (which is reserved for verification failure budget exhaustion).
- **Solution:**
  1. In `runner/domain/status_event.py`, declare `RunState.WAITING_FOR_USER = "waiting_for_user"`. In `runner/domain/ticket.py`, declare property `Ticket.is_hitl` returning `self.mode.upper() == "HITL" or self.status == TicketStatus.BLOCKED`.
  2. In `runner/ports/intervention.py`, add `InterventionAction.PROCEED` and declare `request_hitl_intervention(self, ticket: Ticket) -> InterventionDecision` on `InterventionGateway`. In `runner/adapters/ui/terminal_prompts.py`, implement `request_hitl_intervention` rendering interactive choices (`[p]roceed [with guidance]`, `[s]kip`, `[a]bort`), pausing active Live displays during prompts, and defaulting to abort in non-interactive environments.
  3. In `VerificationLoop.run` (`runner/application/gatekeeper.py`), execute the pre-dispatch check before `cycle_runner` is called: transition state to `WAITING_FOR_USER`, publish status event, update Discord card, and schedule presence escalation if away. On `PROCEED`, cancel escalation, reset presence to nearby, and prepend `Human guidance:\n{hint}\n\n` to `self._pending_prompt`. On `SKIP`, return `VerificationLoopResult.skipped(diagnostics=..., status_note=...)`. On `ABORT`, raise `UserAbortError` directly without tripping the circuit breaker.
  4. In `runner/application/ticket_processor.py`, guard initial phase transition (`if not ticket.is_hitl: await _on_phase_change("Working")`), and forward `status_note` through `TicketOutcome.skipped(status_note=...)` to `DirectoryTicketStore.finalize_skipped(...)`.
