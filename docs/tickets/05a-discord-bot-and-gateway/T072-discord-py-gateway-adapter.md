# T072 — Real discord.py gateway adapter and stub removal
Status: pending
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T071
Security: required

### Requirements
- Implement `runner/adapters/discord/gateway.py` with a class `DiscordPyGateway` that implements `DiscordGateway` using `discord.py`'s `Client` (not `Bot`). It holds a reference to the running `discord.Client` instance passed in at construction. Each of the six port methods resolves channel/thread objects via `client.get_channel` / `client.fetch_channel`, performs the `discord.py` API call, and re-raises any `discord.py` exception as `DiscordGatewayError` so callers never import `discord.py` types.
- Delete `runner/adapters/discord/discord_adapter.py` and remove the `DiscordAdapter` import and usage from `runner/application/gatekeeper.py`. The Gatekeeper's fire-and-forget escalation calls (`self._discord_adapter.send(...)`) are removed entirely — Spec 05b will wire real notification routing via `DiscordLogger`.
- Update `runner/adapters/discord/__init__.py` to export `DiscordPyGateway` instead of `DiscordAdapter`.
- Write a protocol conformance test: `isinstance(DiscordPyGateway(mock_client), DiscordGateway)` is `True`.
- Jump-start: new `runner/adapters/discord/gateway.py`, delete `runner/adapters/discord/discord_adapter.py`, `runner/adapters/discord/__init__.py`, `runner/application/gatekeeper.py` (lines ~22 and ~763 — the import and the `_discord_adapter` assignment), `tests/specs/test_spec_04_gatekeeper.py` (remove any `DiscordAdapter` injection).

### Acceptance Criteria
- `isinstance(DiscordPyGateway(mock_client), DiscordGateway)` is `True`.
- All `discord.py` exceptions raised inside `DiscordPyGateway` methods are caught and re-raised as `DiscordGatewayError`.
- `runner/adapters/discord/discord_adapter.py` no longer exists.
- No file in `runner/` imports `DiscordAdapter`.
- `runner/application/gatekeeper.py` contains no reference to `discord_adapter` or `DiscordAdapter`.
- Security: bot token is read only from the environment variable named in `config.discord.token_env`; it is never logged or included in exception messages.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: No discord.py types leak into domain**
- Setup: Search the codebase for `import discord` outside `runner/adapters/discord/`.
- Steps: Run `grep -r "import discord" runner/domain runner/application runner/ports`.
- Expected: No matches.

### Gotchas
- `discord.py` is an async library; each gateway method must be `async def` and must `await` the underlying API calls.
- `client.get_channel` returns `None` if the channel is not in the cache; prefer `await client.fetch_channel(id)` for reliability, but be prepared to catch `discord.NotFound`.
- Gatekeeper's `_discord_adapter` field and the `discord_adapter` constructor parameter will need to be removed cleanly — check the Gatekeeper constructor signature and any test fixtures that inject a stub `DiscordAdapter`.
- `discord.py` must remain confined to `runner/adapters/discord/`; the domain and application layers must stay importable without `discord.py` installed (relevant for CI with `--local-only`).
