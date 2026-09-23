# T088 — End-to-end Discord smoke and local-only flag verification
Status: completed
Completed: 2026-09-23T06:50:00Z
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: T087

### Requirements
- Write an end-to-end integration test module at `tests/integration/test_discord_e2e.py` that exercises the full Discord adapter stack using `FakeDiscordGateway` (no real bot token required): ticket open → Live Digest stream → Status Card updates → question signal → escalation → answer → presence reset → commit → thread close.
- Verify that `--local-only` flag (or `config.discord.enabled = False`) suppresses all Discord calls across the full ticket lifecycle: `GatekeeperTicketProcessor` must not call any `DiscordGateway` method.
- Verify that the Doctor startup check skips Discord credentials when `--local-only` is set (already tested partially in T076 — extend or reference those tests, do not duplicate).
- The e2e test should wire the real implementations (`DiscordLoggerImpl`, `DiscordThreadManager`, `PresenceCoordinator`, `GatekeeperTicketProcessor`) with fake boundaries (`FakeDiscordGateway`, `FakeSignalRepository`, fake `WorkerCycleRunner`).
- Anchor: `tests/integration/`, `runner/application/ticket_processor.py`, `runner/application/discord_thread_manager.py`, `runner/adapters/discord/gateway.py` (`FakeDiscordGateway` already exists in `tests/fakes/`).
- Verification: `pytest tests/integration/test_discord_e2e.py -v` — all scenarios green.

### Acceptance Criteria
- E2e test covers the scenario table: thread open → status card pinned → live digest started → question posted → escalation scheduled → answer resets presence → status card updated → commit embed → thread archived.
- `--local-only` integration test confirms zero `DiscordGateway` calls for a full ticket run.
- All existing tests continue to pass (`pytest tests/` — no regressions).
- Test module uses only `FakeDiscordGateway` and test doubles — no real Discord API calls, no bot token required.

### Smoke Scenarios
**Scenario 1: Full Discord lifecycle with fake gateway**
- Setup: None (uses in-memory test doubles: `FakeDiscordGateway`, `FakeSignalRepository`, `FakeInterventionGateway`).
- Why: Validates the end-to-end event choreography and message sequences when a ticket runs through working, question, answer, review, verification, commit, and thread archival.
- Steps: Run `py -m pytest tests/integration/test_discord_e2e.py -k test_full_discord_lifecycle_with_fake_gateway -v` in terminal.
- Expected: Test passes. The simulated gateway logs `create_thread` → `pin_message` (Status Card) → `post_message` (Live Digest) → `post_message` (user mention) → `post_message` (question embed) → `edit_message` (Status Card: Reviewing) → `edit_message` (Live Digest: `\n[done]`) → `post_message` (commit embed) → `edit_message` (Status Card: ✅ Committed) → `archive_thread`.

**Scenario 2: local-only produces zero Discord calls**
- Setup: None (in-memory execution with `discord.enabled=False`).
- Why: Proves that users running in offline or local-only mode do not generate any network traffic or trigger Discord API errors.
- Steps: Run `py -m pytest tests/integration/test_discord_e2e.py -k test_local_only_flag_suppresses_all_discord_calls -v` in terminal.
- Expected: Test passes. `GatekeeperTicketProcessor` completes ticket approval with `len(gateway.calls) == 0`.

**Scenario 3: Transient gateway error does not abort ticket**
- Setup: None (in-memory `FakeDiscordGateway` configured with `raise_on_post_message=DiscordGatewayError(...)`).
- Why: Ensures Discord rate limits or temporary connection drops do not crash the local ticket runner or fail worker execution.
- Steps: Run `py -m pytest tests/integration/test_discord_e2e.py -k test_transient_gateway_error_does_not_abort_ticket -v` in terminal.
- Expected: Test passes. The exception is caught and logged, while ticket processing proceeds normally to `TicketOutcome.approved`.

**Scenario 4: Live Discord integration smoke (Actual Discord)**
- Setup: Ensure `$env:DISCORD_BOT_TOKEN` is set in PowerShell and `config.yaml` has a valid `discord.channel_id`.
- Why: Proves that real Discord API calls (thread creation, starter message lookup on parent channel, message editing, permissions) succeed against real Discord servers.
- Steps: Run `py -m pytest tests/integration/test_discord_e2e.py -k test_actual_discord_lifecycle_live -v -s` in terminal.
- Expected: Test passes in ~15-20s. A dedicated thread `ticket-T999` appears in the target Discord channel, receives updates, and is archived after commit embed.

### Gotchas
- The e2e test is the integration-level smoke for the entire Spec 05 surface area — it should be the canonical reference test for any future Discord refactors.
- Keep e2e test file count lean: one test module with named test functions for each scenario. Avoid parameterizing across too many axes — clarity over brevity here.
- `asyncio` event loop management in pytest: use `pytest-asyncio` with `asyncio_mode = "auto"` (already in the project config) — do not manually create event loops in tests.
- All call-order assertions on `FakeDiscordGateway` should use the recorded call log, not `MagicMock` call counts, to keep ordering explicit and readable.
