# T070 — DiscordConfig extension and DiscordGatewayError domain exception
Status: pending
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: None

### Requirements
- Extend `DiscordConfig` with two optional fields: `guild_id: str = ""` and `notify_user_id: str = ""`. Both must validate that non-empty values are all-digit strings (Discord snowflake IDs); empty string means "not set". Add validation in `__post_init__` consistent with the existing `token_env` validation pattern.
- Add `DiscordGatewayError(TicketRunnerError)` to the domain exceptions module so adapters can re-raise `discord.py` exceptions through the port boundary without leaking library types into domain code.
- Update the YAML loader tests to cover the two new fields round-tripping through load.
- Jump-start: `runner/domain/config.py` (`DiscordConfig` dataclass, lines ~124–142), `runner/domain/exceptions.py` (add after `UserAbortError`), `runner/adapters/config/yaml_config_loader.py` (ensure new fields round-trip through YAML load), `tests/unit/` for config validation tests.

### Acceptance Criteria
- `DiscordConfig(guild_id="12345", notify_user_id="67890")` constructs without error.
- `DiscordConfig(guild_id="not-a-snowflake")` raises `ConfigError` with a message naming the field.
- `DiscordConfig(notify_user_id="bad!")` raises `ConfigError`.
- Empty strings `guild_id=""` and `notify_user_id=""` are accepted (the "not set" sentinel).
- `DiscordGatewayError` is importable from `runner.domain.exceptions` and is a subclass of `TicketRunnerError`.
- Existing `config.yaml` files that omit the new fields load without error.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: Config with new fields loads cleanly**
- Setup: Add `discord: { guild_id: "123456789012345678", notify_user_id: "987654321098765432" }` to `config.yaml` alongside existing discord fields.
- Steps: Run `ticket_runner doctor`.
- Expected: Doctor config check passes; no errors about unknown keys.

**Scenario: Invalid snowflake rejected at load time**
- Setup: Set `discord: { guild_id: "not-a-snowflake" }` in `config.yaml`.
- Steps: Run `ticket_runner doctor`.
- Expected: Doctor config check fails with a message referencing `guild_id` and snowflake format.

### Gotchas
- `DiscordConfig` is `frozen=True` — all validation lives in `__post_init__`, same as `token_env`.
- Snowflake IDs can be up to 20 digits; validate with `str.isdigit()`, not a length constraint.
- Keep the YAML loader change minimal: the new fields have defaults, so existing `config.yaml` files that omit them must still load without error.
