# T087 — Integrate Discord into ticket lifecycle (Runner hooks)
Status: pending
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: T086

### Requirements
- Inject `DiscordThreadManager` and `DiscordLoggerImpl` into `GatekeeperTicketProcessor` (at `runner/application/ticket_processor.py`) and the surrounding orchestration layer.
- On ticket start (before first `WorkerCycleRunner` call): call `discord_thread_manager.open_ticket_thread(ticket, config.discord.channel_id)` and store `(thread_id, status_card_message_id)` for the duration of the ticket.
- On phase transition (Working → Reviewing → Verifying): call `discord_thread_manager.update_status_card(thread_id, msg_id, status=…)` and route the appropriate event through `discord_logger.log(event_type, payload, thread_id, presence_mode)`.
- On question signal: call `presence_coordinator.schedule_escalation(ticket_id, thread_id, discord_logger)`.
- On local answer (via `InterventionGateway.ask_question` returning): call `presence_coordinator.cancel_escalation()`.
- On circuit breaker trip (attempt 3 of 3): route `circuit_breaker_trip` event through `DiscordLogger` (always-critical, red embed).
- On hard ceiling (≥ 150k tokens): route `hard_ceiling` event through `DiscordLogger` (always-critical, red embed).
- On handoff (≥ 135k tokens): route `handoff` event through `DiscordLogger` (always-critical, yellow embed).
- On verification failure: route `verification_failed` event through `DiscordLogger` (always-critical, red embed).
- On ticket commit (gatekeeper pass): call `discord_thread_manager.close_ticket_thread(thread_id, msg_id, commit_summary)`.
- When `discord_thread_manager` is `None` or `discord_enabled=False` in config: all hooks are no-ops — `GatekeeperTicketProcessor` must not require Discord to be present.
- Anchor: `runner/application/ticket_processor.py`, `runner/application/gatekeeper.py` (`VerificationLoop`), `runner/application/queue_orchestrator.py`, `runner/application/discord_thread_manager.py`, `runner/application/presence_coordinator.py`.
- Verification: `pytest tests/ -k ticket_processor` — all existing tests still green; new integration tests for Discord hooks pass.

### Acceptance Criteria
- Existing `GatekeeperTicketProcessor` tests pass unchanged — Discord injection is additive.
- `open_ticket_thread` is called once per ticket at the start of `_process_ticket`.
- `close_ticket_thread` is called once per ticket on gatekeeper pass (in `TicketOutcome.approved` path).
- `schedule_escalation` is called when `result.is_question_pending` is handled; `cancel_escalation` is called when local answer is provided.
- All critical events (circuit breaker, hard ceiling, handoff, verification failure) route through `DiscordLogger` regardless of `presence_mode`.
- When Discord is disabled (`discord_thread_manager=None`): ticket processing completes normally with no Discord calls.

### Smoke Scenarios
**Scenario: Full ticket lifecycle in Discord**
- Setup: Stub `DiscordThreadManager` (records calls). Stub `DiscordLoggerImpl` (records events). Run a fake ticket through `GatekeeperTicketProcessor` with cycle runner returning immediate pass.
- Steps: 1. Call `processor.process(ticket)`. 2. Inspect call log on stubs.
- Expected: `open_ticket_thread` called first. Live Digest started. At least one `update_status_card` call for Working phase. `close_ticket_thread` called with commit summary on pass.

**Scenario: Circuit Breaker → Discord critical embed**
- Setup: Cycle runner returns failure 3 times (tripping breaker). `FakeDiscordLogger` records events.
- Steps: Run ticket through processor until circuit breaker trips.
- Expected: `FakeDiscordLogger` records a `circuit_breaker_trip` event with critical severity. `presence_mode` irrelevant — event always recorded.

**Scenario: Question signal → escalation timer scheduled**
- Setup: Cycle runner returns `is_question_pending`. Fake `PresenceCoordinator`.
- Steps: Run ticket; when `is_question_pending`, inspect coordinator.
- Expected: `schedule_escalation(ticket_id, thread_id, discord_logger)` called. Local answer → `cancel_escalation()` called.

**Scenario: local-only suppresses all Discord calls**
- Setup: `discord_thread_manager=None` passed to processor constructor.
- Steps: Run a full ticket through processor.
- Expected: No exceptions; `TicketOutcome.approved` returned normally. Zero Discord gateway calls.

### Gotchas
- `VerificationLoop` may need to surface phase-transition events via a callback or notification sink — check whether `notify` callback already covers phase changes or whether a new `phase_callback` parameter is cleaner.
- `close_ticket_thread` receives a `commit_summary` string — derive it from the `ReadySignal.scope` + modified files list already available in the approved-path code block.
- Avoid storing `thread_id` in `RunnerState` (that is Spec 06 territory) — keep it as in-memory state on the ticket processor or pass it through the call chain for the ticket's duration only.
- All Discord calls in hooks must be wrapped in `try/except DiscordGatewayError` — a transient Discord failure must never abort ticket processing.
