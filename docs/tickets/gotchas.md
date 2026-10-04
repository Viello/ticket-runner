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
