# T075 — ticket_runner bot subcommand (--smoke and --run)
Status: pending
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T074
Security: required

### Requirements
- Add a `bot` subcommand to the top-level `ArgumentParser` in `ticket_runner.py` with two mutually exclusive flags: `--smoke` and `--run`.
- Both flags build a minimal container (config loaded from `--config`, `RuntimePaths`, `SignalRepository`) and start the Discord client from T073.
- `--smoke` runs the self-cleaning verification sequence: authenticate, verify required permissions, create a thread named `_smoke-test-verify`, post a verification message, edit it to "verified", archive and lock the thread, delete the starter announcement message. Exits 0 on success, 1 on any failure, printing a human-readable failure reason to stderr.
- `--run` starts the client loop (blocking) and exits cleanly on SIGINT with exit code 130.
- Implement the smoke sequence as a standalone async function `run_smoke(gateway, channel_id)` testable in isolation using `FakeDiscordGateway`.
- Write unit tests for `run_smoke`: verifies the correct sequence of `DiscordCall` entries and that the starter message is deleted at the end.
- Jump-start: `ticket_runner.py` (`create_parser`, `main`, new `run_bot` async function), `runner/adapters/discord/client.py` (T073), `runner/container.py` or a simpler inline build for the bot-only minimal container, `tests/fakes/fake_discord_gateway.py` (T071).

### Acceptance Criteria
- `ticket_runner bot --help` prints usage for `--smoke` and `--run` flags.
- `ticket_runner bot --smoke` exits 0 on a real Discord connection with all permissions granted.
- `ticket_runner bot --smoke` exits 1 if authentication fails or a required permission is missing, with a message naming the failure.
- After `--smoke` completes successfully, the configured channel contains no threads or messages from the smoke run.
- `ticket_runner bot --run` exits 130 on SIGINT/Ctrl+C.
- Security: token is read from `os.environ[config.discord.token_env]` immediately before `client.start()`; it is never stored in an instance variable, logged, or included in error messages.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: Successful smoke run**
- Setup: Real `DISCORD_BOT_TOKEN` in environment; bot has all 7 required permissions in the configured channel.
- Steps: Run `ticket_runner bot --smoke`.
- Expected: Process exits 0; no `_smoke-test-verify` thread visible in the channel; no messages left behind.

**Scenario: Missing permission detected**
- Setup: Revoke `Manage Messages` permission from the bot in Discord server settings.
- Steps: Run `ticket_runner bot --smoke`.
- Expected: Process exits 1; stderr includes "Manage Messages" or equivalent permission name.

**Scenario: Interactive standalone mode**
- Setup: Real bot token and channel.
- Steps: Run `ticket_runner bot --run`; exercise `/status`; press Ctrl+C.
- Expected: Bot responds to `/status`; process exits 130; bot appears offline in Discord within 5 seconds.

### Gotchas
- `--smoke` must leave the channel in exactly the state it was before — the starter message must be deleted (not just the thread archived). Discord archives a public thread but leaves the starter message in the parent channel; delete it explicitly via `gateway.delete_message` or the underlying `discord.py` `Message.delete()`.
- If the spec's `DiscordGateway` protocol does not expose `delete_message`, add it in this ticket (it is only needed for `--smoke`'s cleanup step) and update the Protocol and `FakeDiscordGateway` accordingly.
- Mutual exclusivity of `--smoke` and `--run` should be enforced with `argparse`'s `add_mutually_exclusive_group`, not ad-hoc if/else logic.
- SIGINT on Windows arrives as a `KeyboardInterrupt`; the asyncio loop must handle it the same way `run_start` does in `ticket_runner.py`.
