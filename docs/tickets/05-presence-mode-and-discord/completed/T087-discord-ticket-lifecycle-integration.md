# T087 — Integrate Discord into ticket lifecycle (Runner hooks)
Status: completed
Completed: 2026-09-23T06:01:00Z
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
- Setup: Configure a ticket runner with a mock Discord thread manager and mock Discord event logger. Provide a test ticket and cycle runner that immediately succeeds.
- Steps: 1. Run the ticket through the processor. 2. Verify recorded method calls on the Discord thread manager and logger.
- Expected: A dedicated ticket thread is opened first, the Status Card is updated through Working, Reviewing, and Verifying states, phase transition events are logged, and the thread is closed with the commit summary upon Gatekeeper approval.

**Scenario: Circuit Breaker → Discord critical embed**
- Setup: Configure the ticket processor with a mock Discord logger and a cycle runner that fails 3 consecutive times to exhaust attempt budgets.
- Steps: Run the ticket through the processor until the circuit breaker trips.
- Expected: The Discord logger records a `circuit_breaker_trip` event with critical severity, bypassing presence mode filtering.

**Scenario: Question signal → escalation timer scheduled and cancelled upon local answer**
- Setup: Configure the ticket processor with a mock presence coordinator and cycle runner that emits a question signal before the ready signal.
- Steps: Run the ticket through the processor; provide an answer via the intervention gateway.
- Expected: `schedule_escalation` is called upon receiving the question signal; `cancel_escalation` is called immediately when the answer is returned.

**Scenario: Disabled Discord suppresses all Discord calls**
- Setup: Configure the ticket processor with `discord_thread_manager=None` and `discord_logger=None`.
- Steps: Run a full ticket through the processor to approval.
- Expected: Ticket executes and finishes with approval; no Discord thread or logging calls are made.

### Gotchas
- `VerificationLoop` surfaces phase-transition events and critical notifications via `phase_callback` and `event_callback` parameters passed down from `GatekeeperTicketProcessor`.
- `close_ticket_thread` receives a `commit_summary` string derived from `ReadySignal.scope` and the list of modified files in the approved path.
- Keep `thread_id` and `status_card_message_id` as active ticket execution state on `GatekeeperTicketProcessor` rather than persisting in `RunnerState`.
- All Discord calls in hooks are wrapped in `try ... except (DiscordGatewayError, Exception)` so transient Discord network failures never fail or abort ticket processing.
