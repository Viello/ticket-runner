# T081 — Smoke regression: Bot smoke timeout and missing slash commands
Status: completed
Completed: 2026-09-22T14:52:00Z
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: None

### Requirements
- Fix regression identified during smoke verification of T075:
  - Observed:
    1. `py ticket_runner.py bot --smoke` fails with `Authentication failed: Connection timed out connecting to Discord.` after 15 seconds.
    2. `py ticket_runner.py bot --run` stays running but does not respond to `/status`, and no slash commands appear registered in Discord.
  - Expected:
    1. `ticket_runner bot --smoke` connects, completes `on_ready`, verifies permissions, runs smoke sequence, and exits 0.
    2. `ticket_runner bot --run` syncs application slash commands to the configured guild/channel on `on_ready`, enabling `/status`, `/pause`, and `/mode`.
- Jump-start:
  - Files to touch: `runner/adapters/discord/client.py`, `runner/adapters/discord/smoke.py`, `ticket_runner.py`
  - Seams to work at: `DiscordClient.on_ready` error handling and logging, guild synchronization exception propagation, ready event signalling
  - Verification: `python -m pytest tests/unit/adapters/test_bot_subcommand.py tests/unit/adapters/test_discord_client.py`

### Acceptance Criteria
- `ticket_runner bot --smoke` successfully connects and completes the smoke verification sequence without timing out on valid credentials.
- `ticket_runner bot --run` syncs command tree to the target guild, and any `on_ready` / sync errors are visibly logged to stderr rather than swallowed silently.
- Automated regression test added covering `on_ready` error propagation and timeout diagnostics.

### Smoke Scenarios
**Scenario: Bot smoke and command sync verification**
- Setup: Valid `DISCORD_BOT_TOKEN`, `channel_id`, and `guild_id` configured in `config.yaml`.
- Steps:
  1. Run `py ticket_runner.py bot --smoke`.
  2. Run `py ticket_runner.py bot --run` and inspect slash commands in the server.
- Expected:
  1. `--smoke` completes with exit code 0.
  2. `--run` registers `/status` and replies when invoked.

### Gotchas
- In `discord.py`, unhandled exceptions inside event handlers (`on_ready`, `on_message`) are caught by the library's internal `on_error` handler and do not raise to the caller or abort the loop. If `on_ready` fails while fetching the channel or syncing the tree, `ready_event.set()` is never reached while the background connection loop stays alive, leading to silent timeouts and unsynced commands.
