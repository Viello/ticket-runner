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


