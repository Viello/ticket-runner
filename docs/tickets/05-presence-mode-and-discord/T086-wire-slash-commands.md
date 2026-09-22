# T086 — Wire live slash commands (/mode and /pause)
Status: pending
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: T085
Security: required

### Requirements
- Update `/mode` slash command in `runner/adapters/discord/commands.py` to accept a `mode` string argument (`nearby` | `away`). Handler calls `presence_coordinator.set_mode(mode)` and responds with `Presence mode set to {mode}.` Invalid values respond with an ephemeral error listing valid options.
- Update `/pause` slash command to call `state_coordinator.request_pause()` (or set `StateStatus.PAUSE_REQUESTED` via `StateCoordinator`) and respond with `Runner paused. Current ticket will complete verification before stopping.`
- Both commands accept live-injected `PresenceCoordinator` and `StateCoordinator` via the `register_commands` factory (update the function signature). Existing `StateStore` injection for `/status` is preserved.
- When `PresenceCoordinator` or `StateCoordinator` is `None` (standalone bot mode), commands respond with the existing `OFFLINE_NOTICE` string.
- The `mode` argument for `/mode` is a Discord `app_commands.Choice` enum: only `"nearby"` and `"away"` are accepted values — the bot never accepts free-text mode names to prevent injection of unknown modes.
- Argument validation: the `mode` parameter must be validated server-side (via Choices) so only `"nearby"` and `"away"` reach the handler. No additional sanitization is needed beyond Choices enforcement — but tests must verify that `set_mode` is only ever called with a member of `VALID_PRESENCE_MODES`.
- Anchor: `runner/adapters/discord/commands.py`, `runner/adapters/discord/client.py` (`register_commands` call site), `runner/domain/state.py` (`VALID_PRESENCE_MODES`), `runner/application/presence_coordinator.py`.
- Verification: `pytest tests/ -k slash_commands` — all tests green.

### Acceptance Criteria
- `/mode nearby` → `presence_coordinator.set_mode("nearby")` called, bot replies `Presence mode set to nearby.`
- `/mode away` → `presence_coordinator.set_mode("away")` called, bot replies `Presence mode set to away.`
- `/pause` → `state_coordinator.request_pause()` called (or equivalent), bot replies with pause confirmation.
- Discord `app_commands.Choice` restricts `/mode` to only `"nearby"` and `"away"` — no free-text accepted.
- `register_commands` updated signature is backward-compatible: existing call sites that pass only `state_store` continue to work (coordinators default to `None`).
- Offline (no coordinators): `/mode` and `/pause` reply with `OFFLINE_NOTICE`; `/status` continues to work as before.
- Security verification: `mode` argument value is only ever one of `VALID_PRESENCE_MODES` (`"nearby"`, `"away"`) before being passed to `set_mode` — enforced by Choices at the Discord API layer and verified in tests.

### Smoke Scenarios
**Scenario: `/mode away` switches presence**
- Setup: Fake `PresenceCoordinator` with `current_mode = "nearby"`. Fake Discord interaction.
- Steps: 1. Call `handle_mode(interaction, mode="away", presence_coordinator=fake_coordinator)`. 2. Check `fake_coordinator.set_mode` call args and `interaction.response` message.
- Expected: `set_mode("away")` called once. Interaction response content is `Presence mode set to away.`

**Scenario: `/mode nearby` switches presence**
- Setup: Same setup, `current_mode = "away"`.
- Steps: Call `handle_mode(interaction, mode="nearby", presence_coordinator=fake_coordinator)`.
- Expected: `set_mode("nearby")` called once. Response content is `Presence mode set to nearby.`

**Scenario: `/pause` sets pause-requested**
- Setup: Fake `StateCoordinator` recording calls. Fake interaction.
- Steps: Call `handle_pause(interaction, state_coordinator=fake_coordinator)`.
- Expected: `request_pause()` (or equivalent state transition) called. Interaction response contains pause confirmation text.

**Scenario: Slash commands offline-safe**
- Setup: Both coordinators = `None`.
- Steps: Call `handle_mode(interaction, mode="away", presence_coordinator=None)` and `handle_pause(interaction, state_coordinator=None)`.
- Expected: Both respond with `OFFLINE_NOTICE` text. No exceptions raised.

### Gotchas
- `app_commands.Choice` for string parameters uses the `choices` kwarg on `@app_commands.describe` or a `Literal` annotation — use `app_commands.Choice[str]` with an explicit `choices=` list on the command function parameter.
- `register_commands` now passes `presence_coordinator` and `state_coordinator` as closure variables into the command handlers via the factory pattern already used for `state_store`. Keep the factory pattern; do not use global state.
- Discord interactions must be acknowledged within 3 seconds — commands that trigger async state writes must use `await interaction.response.defer()` if the write may be slow, then `followup.send()`. For these simple coordinator calls, a direct `send_message` is sufficient.
- `StateCoordinator.request_pause()` method may not yet exist — add it to `StateCoordinator` as part of this ticket (it should transition to `PAUSE_REQUESTED` via `StateStore`).
