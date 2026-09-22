# T073 — Discord client lifecycle module (connect, guild sync, teardown)
Status: completed
Completed: 2026-09-22T08:21:30Z
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T072
Security: required

### Requirements
- Create `runner/adapters/discord/client.py` owning the `discord.py` `Client` instance and an `app_commands.CommandTree`. On `on_ready`: (1) fetch the channel object from `config.discord.channel_id`; (2) resolve `guild_id` — use `config.discord.guild_id` if non-empty, otherwise use `channel.guild.id`; (3) call `tree.sync(guild=discord.Object(id=guild_id))` for instant command registration; (4) set an `asyncio.Event` named `ready_event` to signal callers the bot is fully up.
- Expose `async def start(token: str) -> None` that calls `client.start(token)`.
- Expose `async def close() -> None` that calls `asyncio.wait_for(client.close(), timeout=2.0)`, swallowing `asyncio.TimeoutError`.
- The `CommandTree` is a public attribute so `commands.py` (T074) can register handlers against it.
- No slash command handlers are registered in this ticket — only the skeleton `CommandTree` with the lifecycle wiring.
- Write unit tests using `unittest.mock` or `pytest-asyncio` that verify: `ready_event` is set after `on_ready` fires; `guild_id` is sourced from config when non-empty; `guild_id` falls back to `channel.guild.id` when config value is empty.
- Jump-start: new `runner/adapters/discord/client.py`, `runner/adapters/discord/__init__.py` (export the client module), `runner/domain/config.py` (`DiscordConfig.guild_id` added in T070).

### Acceptance Criteria
- `ready_event` is set when `on_ready` completes.
- When `config.discord.guild_id` is non-empty, `tree.sync` receives `discord.Object(id=guild_id)` with that exact value.
- When `config.discord.guild_id` is empty, `tree.sync` receives the guild ID fetched from the channel.
- `close()` completes within 3 seconds even if `client.close()` hangs (guarded by the 2-second `wait_for` + test timeout).
- Security: the token string passed to `client.start()` comes exclusively from `os.environ[config.discord.token_env]`; it is not stored as an instance attribute or logged.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: Bot connects and shows online**
- Setup: Real `DISCORD_BOT_TOKEN` in environment, valid `channel_id` in `config.yaml`, bot invited to server.
- Steps: After T075 lands, run `ticket_runner bot --run`; observe the bot user in Discord.
- Expected: Bot appears online in the configured server within 10 seconds of command start.

**Scenario: Clean teardown**
- Setup: Same as above; bot is running via `--run`.
- Steps: Press Ctrl+C.
- Expected: Bot shows as offline in Discord within 5 seconds; process exits with code 130.

### Gotchas
- `client.start()` is a long-running coroutine that blocks until disconnected — run it as an `asyncio.Task` rather than awaiting it directly, so the caller can concurrently await `ready_event`.
- Guild-scoped `tree.sync()` propagates commands in under 1 second; global sync can take up to an hour — always sync to the guild, never globally.
- `asyncio.wait_for` on `client.close()` raises `asyncio.TimeoutError` on timeout; suppress it so the runner's exit path always completes cleanly.
