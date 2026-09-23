# T086 — Wire live slash commands (/mode and /pause)
Status: completed
Completed: 2026-09-23T05:26:36Z
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
**Scenario: `/mode away` switches presence** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Verifies that passing `mode="away"` to the `/mode` slash command triggers `PresenceCoordinator.set_mode('away')` and confirms mode change in Discord reply.
- Steps:
  1. Run the following Python snippet in terminal:
     ```powershell
     python -c "import asyncio; from unittest.mock import AsyncMock, MagicMock; import discord; from runner.adapters.discord.commands import handle_mode; class FakePresence: set_mode = lambda s, m: print(f'Coordinator set_mode: {m}') or m; interaction = MagicMock(spec=discord.Interaction); interaction.response.send_message = AsyncMock(side_effect=lambda msg, **kw: print(f'Reply: {msg}')); asyncio.run(handle_mode(interaction, mode='away', presence_coordinator=FakePresence()))"
     ```
- Expected: Terminal prints:
  `Coordinator set_mode: away`
  `Reply: Presence mode set to away.`

**Scenario: `/mode nearby` switches presence** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Verifies that passing `mode="nearby"` to `/mode` updates `PresenceCoordinator` to `"nearby"` and returns confirmation message.
- Steps:
  1. Run the following Python snippet in terminal:
     ```powershell
     python -c "import asyncio; from unittest.mock import AsyncMock, MagicMock; import discord; from runner.adapters.discord.commands import handle_mode; class FakePresence: set_mode = lambda s, m: print(f'Coordinator set_mode: {m}') or m; interaction = MagicMock(spec=discord.Interaction); interaction.response.send_message = AsyncMock(side_effect=lambda msg, **kw: print(f'Reply: {msg}')); asyncio.run(handle_mode(interaction, mode='nearby', presence_coordinator=FakePresence()))"
     ```
- Expected: Terminal prints:
  `Coordinator set_mode: nearby`
  `Reply: Presence mode set to nearby.`

**Scenario: `/pause` sets pause-requested** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Verifies that executing `/pause` invokes `StateCoordinator.request_pause()` to schedule pausing after the active ticket verification.
- Steps:
  1. Run the following Python snippet in terminal:
     ```powershell
     python -c "import asyncio; from unittest.mock import AsyncMock, MagicMock; import discord; from runner.adapters.discord.commands import handle_pause; class FakeState: request_pause = lambda s: print('StateCoordinator: request_pause called'); interaction = MagicMock(spec=discord.Interaction); interaction.response.send_message = AsyncMock(side_effect=lambda msg, **kw: print(f'Reply: {msg}')); asyncio.run(handle_pause(interaction, state_coordinator=FakeState()))"
     ```
- Expected: Terminal prints:
  `StateCoordinator: request_pause called`
  `Reply: Runner paused. Current ticket will complete verification before stopping.`

**Scenario: Slash commands offline-safe** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Verifies that when bot runs standalone without live orchestrator coordinators, `/mode` and `/pause` respond gracefully with `OFFLINE_NOTICE`.
- Steps:
  1. Run the following Python snippet in terminal:
     ```powershell
     python -c "import asyncio; from unittest.mock import AsyncMock, MagicMock; import discord; from runner.adapters.discord.commands import handle_mode, handle_pause; interaction = MagicMock(spec=discord.Interaction); interaction.response.send_message = AsyncMock(side_effect=lambda msg, **kw: print(f'Reply: {msg}')); asyncio.run(handle_mode(interaction, mode='away', presence_coordinator=None)); asyncio.run(handle_pause(interaction, state_coordinator=None))"
     ```
- Expected: Terminal prints:
  `Reply: Runner is offline (standalone bot mode). Command is unavailable.`
  `Reply: Runner is offline (standalone bot mode). Command is unavailable.`

### Gotchas
- `app_commands.Choice` for string parameters uses the `choices` kwarg on `@app_commands.describe` or a `Literal` annotation — use `app_commands.Choice[str]` with an explicit `choices=` list on the command function parameter.
- `register_commands` now passes `presence_coordinator` and `state_coordinator` as closure variables into the command handlers via the factory pattern already used for `state_store`. Keep the factory pattern; do not use global state.
- Discord interactions must be acknowledged within 3 seconds — commands that trigger async state writes must use `await interaction.response.defer()` if the write may be slow, then `followup.send()`. For these simple coordinator calls, a direct `send_message` is sufficient.
- `StateCoordinator.request_pause()` method may not yet exist — add it to `StateCoordinator` as part of this ticket (it should transition to `PAUSE_REQUESTED` via `StateStore`).
