# T085 — Idle escalation timer and presence auto-reset
Status: completed
Completed: 2026-09-22T17:07:00Z
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: T084
Security: required

### Requirements
- Extend `PresenceCoordinator` (at `runner/application/presence_coordinator.py`) with: `schedule_escalation(ticket_id, thread_id, discord_logger)` — starts an `asyncio.Task` timer for `config.idle_escalation_minutes` (default 3). On expiry: sets `presence_mode = "away"`, posts a critical yellow embed with `@mention` (using `config.discord.notify_user_id`) in `thread_id` via `discord_logger`. `cancel_escalation()` cancels the pending task and clears it.
- The `@mention` is posted as a separate plain-text `post_message` call before the embed (matching the Question Signal protocol in the spec: mention first, embed second).
- The `notify_user_id` is read from `DiscordConfig.notify_user_id` (already in config — see `runner/domain/config.py`). It must never be logged or written to any file — only used in the message string.
- Extend `process_thread_reply` in `runner/adapters/discord/thread_listener.py`: after successfully calling `signal_repository.write_answer(ticket_id, content)`, also call `presence_coordinator.set_mode("nearby")` if a `PresenceCoordinator` is passed. Wire this through `DiscordClient.on_message` by injecting `PresenceCoordinator` into `DiscordClient`.
- `PresenceCoordinator` gains a `set_mode(mode)` method that persists via `StateCoordinator` (equivalent to explicit mode assignment rather than toggle).
- Timer implementation must use `asyncio.get_event_loop().call_later` or `asyncio.create_task` — never `time.sleep`. Tests must be able to fast-forward the timer by passing a stub `asyncio` loop or a replaceable timer factory.
- Anchor: `runner/application/presence_coordinator.py`, `runner/adapters/discord/thread_listener.py`, `runner/adapters/discord/client.py`.
- Verification: `pytest tests/ -k "escalation or presence_reset"` — all tests green.

### Acceptance Criteria
- `schedule_escalation` starts a cancellable asyncio task; calling it a second time without cancelling the first must replace the old task (not stack timers).
- On expiry: `presence_mode` transitions to `"away"`, a plain-text `@mention` is posted, then the yellow embed is posted — two separate `post_message` calls in order.
- `cancel_escalation()` cancels the asyncio task; no Discord posts occur after cancellation.
- `process_thread_reply` resets presence to `"nearby"` only after a successful `write_answer` — failure must not reset presence.
- `notify_user_id` is never written to a log file, console output, or state file.
- Security verification: confirm `notify_user_id` is interpolated into Discord message content only (not echoed to terminal, not persisted).

### Smoke Scenarios
**Scenario: Escalation fires after idle timeout** [also auto-covered]
- Setup: Stub timer to fire after 1ms (inject a factory that creates immediate tasks). `FakeDiscordGateway`. Set `presence_mode = "nearby"`.
- Steps: 1. Call `schedule_escalation("T042", "thread-99", discord_logger)`. 2. Await event loop for 10ms.
- Expected: `presence_mode` is now `"away"`. `FakeDiscordGateway` records: (1) `post_message` with `<@{notify_user_id}>`, then (2) `post_message` with yellow embed (colour `0xFEE75C`), title `❓ Worker Question`.

**Scenario: Escalation cancelled on local answer** [also auto-covered]
- Setup: Same stub timer. `FakeDiscordGateway`. `presence_mode = "nearby"`.
- Steps: 1. Call `schedule_escalation("T042", "thread-99", discord_logger)`. 2. Immediately call `cancel_escalation()`. 3. Await event loop for 10ms.
- Expected: `presence_mode` remains `"nearby"`. Zero `post_message` calls on `FakeDiscordGateway`.

**Scenario: Second `schedule_escalation` replaces the first** [also auto-covered]
- Setup: Stub immediate-fire timer. `FakeDiscordGateway`.
- Steps: 1. Call `schedule_escalation("T042", "thread-99", discord_logger)`. 2. Immediately call `schedule_escalation("T042", "thread-99", discord_logger)` again. 3. Await.
- Expected: Exactly 2 total Discord `post_message` calls (one mention + one embed) — not 4.

**Scenario: Discord answer resets presence to nearby** [also auto-covered]
- Setup: `FakeDiscordGateway`. `presence_mode = "away"`. Fake message object from the configured channel, thread named `T042-some-slug`, sent by `notify_user_id`.
- Steps: 1. Call `process_thread_reply(message, signal_repository, config, presence_coordinator=presence_coordinator)`. 2. Check `presence_coordinator.current_mode`.
- Expected: `signal_repository.write_answer("T042", content)` called. `presence_coordinator.current_mode == "nearby"`.

### Gotchas
- Stacking timers (calling `schedule_escalation` twice without cancel) must be defended against — the second call must cancel the pending task before creating a new one.
- The asyncio task holds a reference to `discord_logger` and `thread_id` at the time of scheduling — if those change between scheduling and firing, the task uses the original values. This is intentional and correct.
- `process_thread_reply` is a module-level async function; `PresenceCoordinator` injection should be optional (default `None`) to preserve backward compatibility with existing call sites in `DiscordClient.on_message`.
- Security: `notify_user_id` must not appear in any log output (the mention string is posted to Discord only, never printed to stdout/stderr or written to `.agent/` state files).
