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
- **Solution:** In `DiscordThreadManager.open_ticket_thread`, invoke `gateway.create_thread` with the Status Card embed payload to post the parent starter message and spawn the thread in one seam, then call `gateway.pin_message(thread_id, starter_msg_id)` before calling `logger.start_live_digest(thread_id)`. Sync the created card state into `logger._status_cards` so subsequent phase transitions (`update_status_card`) retain ticket and spec metadata. In `close_ticket_thread`, post the green commit summary embed (`0x57F287`), update the Status Card to `✅ Committed`, and guard `gateway.archive_thread(thread_id)` in a `try/except DiscordGatewayError` block that logs a warning and exits cleanly without raising.



