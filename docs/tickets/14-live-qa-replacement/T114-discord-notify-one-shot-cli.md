# T114 — Discord notify one-shot CLI subcommand
Status: pending
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: None
Security: required

### Requirements
- A `notify` subcommand on `ticket_runner.py` that posts exactly one message to the configured Discord status channel and exits: validate Discord enablement, channel id, and token env var; build the bot container; post via the existing gateway port's message-posting method; exit non-zero with a clear diagnostic when configuration is missing. Reuses existing Discord settings — no new `config.yaml` keys and no gateway port changes.
- Jump-start:
  - Files to touch: `ticket_runner.py` (subparser around lines 220–223 next to `pause`/`status` placeholders; dispatch in `main()` near the `bot` branch; async `run_notify` helper mirroring `run_bot` at lines 596–647), `runner/ports/discord_gateway.py` (use `post_message` as-is), `runner/domain/config.py` (`DiscordConfig`: `enabled`, `channel_id`, `token_env`).
  - Seams to work at: CLI seam — `tests/unit/adapters/test_bot_subcommand.py` drives `run_bot` with an injected fake gateway; mirror that shape for `run_notify`. Also extend `tests/unit/test_cli.py` for parser wiring.
  - Verification: `python -m pytest tests/unit/adapters/test_bot_subcommand.py tests/unit/test_cli.py`

### Acceptance Criteria
- `py ticket_runner.py notify "hello"` posts one message to the configured channel via the injected gateway and exits 0.
- Missing/invalid config (`enabled: false`, absent `channel_id`, unset token env var) exits non-zero with a distinct, actionable diagnostic naming the missing setting.
- No new config schema fields; `doctor` and existing subcommands unaffected.
- Security verification: the token is read only from the env var named by `config.discord.token_env`, never logged, never echoed in diagnostics; message text is passed through without shell interpolation; unit tests assert the token value appears nowhere in captured output.

### Smoke Scenarios
**Scenario: notify posts to Discord**
- Setup: `config.yaml` with `discord.enabled: true`, valid `channel_id`, `DISCORD_BOT_TOKEN` set in env; bot not otherwise required to be running.
- Why: Live-qa sessions stream per-scenario verdicts through this command; if one-shot posting works, the streaming hook has its transport.
- Steps: 1. Run `py ticket_runner.py notify "live-qa: scenario X — verified"`. 2. Watch the configured Discord channel. 3. Then unset the token env var and re-run.
- Expected: The message appears in the channel within seconds and the command exits 0; the second run exits non-zero with a diagnostic naming the missing token env var, and no traceback.

### Gotchas
- `run_bot` builds its container via `build_bot_container` from `runner.container` — reuse that path; do not hand-wire discord.py in the CLI layer.
- Mutual-exclusivity precedent: the `bot` parser uses `add_mutually_exclusive_group`; `notify` takes a single positional message — quote it in PowerShell (`py ticket_runner.py notify "msg"`).
