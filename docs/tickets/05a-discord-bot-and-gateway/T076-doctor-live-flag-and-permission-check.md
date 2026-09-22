# T076 — Doctor --live flag and live gateway permission check
Status: pending
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T075
Security: required

### Requirements
- Add `live: bool = False` parameter to `Doctor.check_discord()`. When `live=True`, after the existing offline env-var check, open a minimal `discord.py` connection (10-second timeout on `fetch_channel`), read the bot's computed permissions via `channel.permissions_for(guild.me)`, close the connection, and report pass/fail with a per-permission breakdown for all 7 required permissions: Send Messages, Send Messages in Threads, Create Public Threads, Manage Threads, Manage Messages, Read Message History, Embed Links.
- The offline env-var path (current behavior) must remain completely unchanged when `live=False`.
- Add `--live` flag to the `doctor` subcommand parser in `ticket_runner.py`. Pass `live=True` to `Doctor.run()` which in turn passes it to `check_discord()`.
- Write unit tests: `check_discord(live=True)` passes when a fake gateway returns the full permission set; fails with per-permission detail when one or more permissions are missing.
- Jump-start: `runner/application/doctor.py` (`check_discord` method around line 550, `CHECK_DISCORD` constant, `run()` method signature), `ticket_runner.py` (`create_parser` doctor subcommand block, `run_doctor` function signature), `tests/unit/` for doctor tests, `tests/fakes/fake_discord_gateway.py` (T071 — may need a `get_permissions()` method or the live check's connectivity helper needs its own seam).

### Acceptance Criteria
- `ticket_runner doctor` (no flag) completes without any network call; behavior is identical to pre-ticket.
- `ticket_runner doctor --live` with all 7 permissions present: check passes with a message listing all permissions as verified.
- `ticket_runner doctor --live` with `Manage Messages` revoked: check fails; the failure message names `Manage Messages` explicitly.
- `ticket_runner doctor --live` when the bot token is invalid: check fails within 15 seconds (timeout guard) with an authentication error message.
- Security: the token value is never logged or included in `CheckResult.message` or `CheckResult.remediation`; only the env var name is referenced.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: Offline check is unchanged**
- Setup: Valid `DISCORD_BOT_TOKEN` set in environment; no network connection.
- Steps: Run `ticket_runner doctor` (no `--live`).
- Expected: Doctor completes in under 2 seconds; Discord check passes with "Discord token verified" message; no network timeout occurs.

**Scenario: Live check passes**
- Setup: Valid token, bot in server with all 7 required permissions.
- Steps: Run `ticket_runner doctor --live`.
- Expected: Discord check passes; output lists all 7 permissions as verified.

**Scenario: Live check reports missing permission**
- Setup: Revoke `Create Public Threads` from the bot in Discord channel settings.
- Steps: Run `ticket_runner doctor --live`.
- Expected: Discord check fails; output explicitly names `Create Public Threads` as missing.

### Gotchas
- The live check opens a minimal connection — prefer a short-lived `discord.Client` with just `fetch_channel` rather than a full `on_ready` lifecycle; this avoids the need to sync the command tree just for a permission check.
- `channel.permissions_for(guild.me)` requires the `guild.me` member to be cached; ensure the client's intents include `Guilds` (enabled by default) so the member object is available.
- The 10-second `fetch_channel` timeout guard must be implemented with `asyncio.wait_for` and report a clear timeout message if it fires — do not let it silently hang the doctor run.
- Doctor's `run()` method signature change (adding `live: bool`) must remain backward-compatible with all existing test call sites.
