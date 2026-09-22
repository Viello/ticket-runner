# Spec 05a: Discord Bot & Gateway

## Problem Statement

Ticket Runner has a stub `DiscordAdapter` that logs warnings instead of sending real messages.
The `DiscordConfig` domain type and Doctor's offline env-var check exist, but no real `discord.py`
connection is ever made. Developers cannot verify that their bot token, channel ID, or permissions
are correct without running the full ticket queue — and there is no safe, isolated path to prove
that Discord works before wiring it into presence-mode orchestration.

Additionally, the existing stub violates the two-port architecture committed to in Spec 05
(`DiscordGateway` / `DiscordLogger`): raw API calls are not yet separated from routing logic,
and there is no `FakeDiscordGateway` for deterministic unit tests.

## Solution

Implement the complete Discord Bot foundation in strict isolation from Presence Mode
orchestration:

1. **`DiscordGateway` port**: A runtime-checkable Protocol exposing six primitive Discord
   operations (`post_message`, `edit_message`, `pin_message`, `create_thread`, `edit_thread`,
   `archive_thread`). Tests anywhere in the codebase against Discord use a `FakeDiscordGateway`
   rather than the real `discord.py` adapter.

2. **Real `discord.py` adapter**: Implements `DiscordGateway` using `discord.py`, managing
   the asyncio event loop and WebSocket connection lifecycle within the Runner's own loop.

3. **Slash command tree** (`/status`, `/pause`, `/mode`): Registered against the bot's guild
   via hybrid guild-ID discovery; commands degrade gracefully when the orchestrator is offline.

4. **Thread reply listener** (`on_message`): Captures developer replies inside ticket threads
   to write answers back to `.agent/questions/{ticket_id}.json` via `SignalRepository`.

5. **Standalone bot CLI** (`ticket_runner bot --smoke` / `ticket_runner bot --run`): Lets
   developers verify real Discord connectivity and exercise slash commands without running the
   ticket queue.

6. **Doctor `--live` flag**: Extends the existing offline env-var check with an opt-in live
   gateway ping, without changing the default fast startup path.

7. **`DiscordConfig` extension**: Adds optional `guild_id` and `notify_user_id` fields to the
   existing domain config dataclass.

## User Stories

1. As a developer, I want a `DiscordGateway` Protocol defined in the ports layer, so that all
   Discord API calls in the codebase are mediated through a single, swappable seam.
2. As a developer, I want a `FakeDiscordGateway` in-memory test double, so that any test can
   record and assert exact Discord API calls without network I/O or a live bot token.
3. As a developer, I want the real `discord.py` adapter to implement `DiscordGateway`, so that
   swapping to a different messaging backend only requires replacing one adapter file.
4. As a developer, I want to call `post_message(channel_or_thread_id, content)` to post a
   plain-text or embed message to a channel or thread, receiving the new message ID as a return value.
5. As a developer, I want to call `edit_message(channel_or_thread_id, message_id, content)` to
   edit an existing message in-place.
6. As a developer, I want to call `pin_message(channel_or_thread_id, message_id)` to pin a
   message at the top of a thread (Status Card pinning).
7. As a developer, I want to call `create_thread(channel_id, name, starter_message)` which posts
   the starter message in the channel, creates a public thread from it, and returns both the
   thread ID and the starter message ID.
8. As a developer, I want to call `edit_thread(thread_id, *, archived, locked)` to archive
   and/or lock a completed ticket thread.
9. As a developer, I want to call `archive_thread(thread_id)` as a convenience shorthand that
   archives and locks a thread in a single call.
10. As a developer, I want the bot to automatically resolve the guild ID from `channel_id` at
    startup (via `fetch_channel`) and sync slash commands directly to that guild for instant
    (< 1 second) command propagation.
11. As a developer, I want to provide an optional `discord.guild_id` in `config.yaml` to bypass
    the auto-detect fetch and use a hardcoded guild ID for slash command sync.
12. As a developer, I want a `/status` slash command that reads `.agent/state.json` and replies
    with the last-persisted runner state, including a badge indicating whether the orchestrator is
    online or offline (standalone bot mode).
13. As a developer, I want `/pause` and `/mode` slash commands that reply with a clear offline
    notice when invoked in standalone bot mode, rather than silently failing or erroring.
14. As a developer, I want the bot to listen for non-bot messages posted inside ticket threads
    under the configured `channel_id` (the `on_message` listener), and write the content as an
    answer to `.agent/questions/{ticket_id}.json` via `SignalRepository.write_answer`.
15. As a developer, I want thread-to-ticket correlation performed purely by parsing the ticket ID
    from the thread name (`{ticket_id}-{slug}`) with no state store lookup required, so the
    mapping survives runner restarts.
16. As a developer, I want the thread reply listener to optionally enforce that the reply author
    matches `config.yaml: discord.notify_user_id`, so unauthorized users cannot answer runner
    prompts on a shared server.
17. As a developer, I want to run `ticket_runner bot --smoke` which: authenticates with Discord,
    verifies that the bot holds all required permissions, creates a temporary thread named
    `_smoke-test-verify`, posts a verification message, edits it to confirmed, archives and locks
    the thread, then deletes the starter announcement message — leaving the channel in exactly
    the state it was before the test. The command exits 0 on success and 1 on any failure.
18. As a developer, I want to run `ticket_runner bot --run` which starts the bot in standalone
    interactive mode, connects to Discord, registers slash commands, and keeps running until
    Ctrl+C — allowing me to manually exercise `/status`, `/pause`, `/mode`, and thread replies
    without running the ticket queue.
19. As a developer, I want `ticket_runner doctor` to continue doing a fast, offline env-var check
    of `DISCORD_BOT_TOKEN` by default, so startup stays instantaneous and works offline.
20. As a developer, I want `ticket_runner doctor --live` to additionally perform a live gateway
    ping and a least-privilege permission check against the real Discord API.
21. As a developer, I want the live permission check to explicitly verify: `Send Messages`,
    `Send Messages in Threads`, `Create Public Threads`, `Manage Threads`, `Manage Messages`,
    `Read Message History`, and `Embed Links` — reporting which specific permissions are missing.
22. As a developer, I want `DiscordConfig` to accept optional `guild_id` (for slash command sync
    override) and `notify_user_id` (for thread reply authorization) fields in `config.yaml`.
23. As a developer, I want the bot client to start as an `asyncio.Task` inside the Runner's
    existing event loop when `ticket_runner start` is running, so there is no inter-process
    coordination overhead.
24. As a developer, I want the bot to close its WebSocket cleanly (via `client.close()` with a
    2-second timeout) when Ticket Runner receives a termination signal or drains the queue, so
    Discord does not show the bot as online after the process exits.
25. As a developer, I want a Developer Portal onboarding guide (`docs/discord-setup.md`)
    documenting the exact bot scopes (`bot`, `applications.commands`), the required permission
    set, and `Message Content Intent` enablement, so I can reproduce the setup from scratch.
26. As a developer, I want `Message Content Intent` enabled in the Developer Portal, so the
    `on_message` listener can read the text of developer replies inside ticket threads without
    requiring modal dialogs or slash-command workarounds.

## Implementation Decisions

### DiscordGateway Port

A new `DiscordGateway` Protocol is added to the ports layer, making it `runtime_checkable`
so that `isinstance(gateway, DiscordGateway)` can be used for injection validation. All six
primitive operations are `async def`. Embed payloads are passed as plain Python dicts matching
Discord's embed structure — no `discord.Embed` objects cross the port boundary, keeping the
protocol adapter-agnostic.

The six operations:
- `post_message(channel_or_thread_id, content, *, embed=None) -> str` — returns the new message ID.
- `edit_message(channel_or_thread_id, message_id, content, *, embed=None) -> None`
- `pin_message(channel_or_thread_id, message_id) -> None`
- `create_thread(channel_id, name, starter_message, *, embed=None) -> tuple[str, str]` — returns
  `(thread_id, starter_message_id)`. Both IDs are needed because the starter message becomes the
  Status Card pinned in Spec 05b.
- `edit_thread(thread_id, *, archived=False, locked=False) -> None`
- `archive_thread(thread_id) -> None` — convenience that calls
  `edit_thread(thread_id, archived=True, locked=True)`.

### FakeDiscordGateway

`tests/fakes/fake_discord_gateway.py` records every call as a `DiscordCall` named tuple
appended to a `calls: list[DiscordCall]` attribute. It maintains an in-memory map of threads and
messages with auto-incrementing integer IDs, and exposes a `pending_replies` list that tests can
append to in order to simulate user thread replies.

### discord.py Adapter

The production adapter (`runner/adapters/discord/gateway.py`) wraps `discord.py`'s `Client`
(not `Bot`). It holds a reference to the running client instance, resolves channel/thread objects
inside each method call, and catches all `discord.py` exceptions, re-raising them as
`DiscordGatewayError` (new exception in the domain's exceptions module) so callers never import
`discord.py` types.

### Client Lifecycle

The client module (`runner/adapters/discord/client.py`) owns the `discord.py` `Client` instance
and the slash command `app_commands.CommandTree`. On `on_ready`:
1. Fetches the channel object from `channel_id`.
2. Uses `guild_id` from config if provided; otherwise uses `channel.guild.id`.
3. Calls `tree.sync(guild=discord.Object(id=guild_id))` for instant command registration.
4. Sets an asyncio `ready_event` to signal callers that the bot is ready.

Teardown: `async def close()` awaits `client.close()`, called by the Runner's exit lifecycle
wrapped in a 2-second `asyncio.wait_for` timeout.

### Slash Commands

Commands are defined in `runner/adapters/discord/commands.py` and registered on the `CommandTree`
owned by the client module. Each handler receives an injected `StateStore` reference to read
`.agent/state.json`. Online/offline determination: `runner_status == "running"` in state. In
offline mode, `/status` replies with state data plus the `[Offline / Standalone Bot]` badge;
`/pause` and `/mode` reply with the offline notice string.

### Thread Reply Listener

The `on_message` logic is extracted to a pure, testable function `process_thread_reply(message_data, signal_repository, config)`. Filtering order:
1. `message.author.bot` → skip.
2. Message channel type is not a thread → skip.
3. Parent channel ID ≠ configured `channel_id` → skip.
4. `notify_user_id` configured and sender ID ≠ `notify_user_id` → skip.
5. Extract ticket ID: regex `^([A-Z]\d{3,})` on `thread.name`.
6. Call `signal_repository.write_answer(ticket_id, message.content)`.
7. Post a short confirmation or error reply in the thread.

### DiscordConfig Extension

`DiscordConfig` gains two optional fields:
- `guild_id: str = ""` — bypass auto-detect; empty string means auto-detect.
- `notify_user_id: str = ""` — restrict reply listener; empty string means accept any user.

Validation: non-empty values must be all-digit strings (Discord snowflake IDs).

### `ticket_runner bot` Subcommand

New `bot` subcommand added to the top-level `ArgumentParser` with mutually exclusive `--smoke`
and `--run` flags. Both build a minimal container (config + runtime paths + signal repository)
and start the Discord client. `--smoke` runs the self-cleaning verification sequence and exits;
`--run` runs indefinitely until SIGINT.

### Doctor `--live` Extension

`Doctor.check_discord` gains a `live: bool = False` parameter. When `live=True`, after env-var
confirmation, it opens a minimal `discord.py` connection, fetches the configured channel (10-second
timeout), reads the bot's computed permissions via `channel.permissions_for(guild.me)`, closes
the connection, and reports pass/fail with per-permission breakdown. The `doctor` subcommand gains
`--live` which passes `live=True` to this check.

### Developer Portal Onboarding Guide

`docs/discord-setup.md` covers: creating a Discord Application and Bot User, enabling
`Message Content Intent` (Privileged Gateway Intents), generating the OAuth2 invite URL with
scopes `bot,applications.commands` and the correct permission integer, inviting the bot,
obtaining `channel_id` and optional `guild_id`, setting `DISCORD_BOT_TOKEN`, and running
`ticket_runner bot --smoke` to verify.

### Removal of DiscordAdapter Stub

The existing `runner/adapters/discord/discord_adapter.py` stub is deleted and replaced by the
real `DiscordGateway` adapter. Any existing callers in `Gatekeeper` and `TicketProcessor` that
fire-and-forget into `discord_adapter.send()` are updated to use the `DiscordGateway` port (or
removed if the logic belongs to `DiscordLogger` in Spec 05b).

## Testing Decisions

Tests verify **external observable behavior** only — what messages were posted, which thread IDs
were created, whether the signal file was written — never `discord.py` internals or event
dispatcher internals.

**Primary seam**: `DiscordGateway` is the single seam across the codebase. `FakeDiscordGateway`
is the sole test double for Discord behavior; no test imports `discord.py` directly.

**Modules tested:**
- Protocol conformance: both `FakeDiscordGateway` and the real adapter pass
  `isinstance(gateway, DiscordGateway)`.
- `FakeDiscordGateway` call recording: post, edit, pin, create_thread, archive_thread produce
  correct `DiscordCall` entries.
- Slash command handlers: `/status` reads offline state from a fake state store; `/pause` and
  `/mode` return the offline notice string.
- Thread reply listener (`process_thread_reply`): correctly filters bot authors, threads outside
  `channel_id`, wrong `notify_user_id`; calls `signal_repository.write_answer` with correct
  ticket ID parsed from the thread name.
- Smoke test sequence: posts to correct channel, creates `_smoke-test-verify` thread, edits,
  archives, deletes starter message.
- `Doctor.check_discord(live=True)`: passes when fake gateway returns the required permission set;
  fails with per-permission detail when permissions are missing.
- `DiscordConfig`: `guild_id` and `notify_user_id` reject non-digit non-empty strings.

**Prior art**: `tests/fakes/` (`FakeSignalRepository`, `FakeCommandRunner`) and
`tests/specs/test_spec_04_gatekeeper.py` for injection-based integration test patterns.

## Out of Scope

- `DiscordLogger` (severity routing, embed construction, Status Card, Live Digest) — Spec 05b.
- Presence Mode state machine, idle escalation timer, and mode-gated routing — Spec 05b.
- Question escalation from the Runner to Discord (queue → notification loop) — Spec 05b.
- Multi-channel fan-out or multi-server support.
- Voice channel alerts or audio notifications.
- Slack, Telegram, or webhook adapters.

## Further Notes

- The `DiscordGateway` / `DiscordLogger` two-port separation means this spec builds only the
  lower port (`DiscordGateway`). The upper port (`DiscordLogger`) with routing and formatting
  logic belongs to Spec 05b and depends on 05a being complete.
- Keeping `discord.py` types strictly inside `runner/adapters/discord/` and never crossing the
  port boundary means the domain and application layers remain importable on machines without
  `discord.py` installed — relevant for CI environments where `--local-only` is standard.
- The `create_thread` return value carries both the thread ID and the starter message ID because
  the starter message is what gets pinned as the Status Card in Spec 05b; callers need both IDs
  at the moment of thread creation.
- `ticket_runner bot --run` remains permanently useful as a debug harness after Spec 05b is
  complete: it lets developers exercise the gateway and slash commands without triggering OpenCode
  or the ticket queue.
