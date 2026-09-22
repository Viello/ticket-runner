# T074 — Slash commands (/status, /pause, /mode) and thread reply listener
Status: pending
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T073

### Requirements
- Create `runner/adapters/discord/commands.py` defining three `@tree.command` handlers registered on the `CommandTree` from T073. Each handler receives an injected `StateStore` reference via closure or dependency injection:
  - `/status`: reads `.agent/state.json` via `StateStore.load()`; replies with the persisted runner state fields plus `[Offline / Standalone Bot]` badge when `runner_status != "running"`.
  - `/pause`: replies with an offline notice string in standalone mode; no state mutation.
  - `/mode`: replies with the same offline notice string in standalone mode.
- Create `runner/adapters/discord/thread_listener.py` containing a pure function `process_thread_reply(message_data, signal_repository, config)` implementing the five-step filtering chain from the spec (bot author → thread type → parent channel ID → notify_user_id → ticket ID extraction). On match, calls `signal_repository.write_answer(ticket_id, content)` and posts a short confirmation reply. Ticket ID extracted via regex `^([A-Z]\d{3,})` on `thread.name`.
- Wire `process_thread_reply` as the `on_message` handler in the client module from T073.
- Write unit tests covering: `/status` reads offline state and includes the badge; `/pause` and `/mode` return the offline notice; `process_thread_reply` correctly filters bot authors, non-thread channels, wrong parent channel, wrong `notify_user_id`, and calls `write_answer` with the parsed ticket ID on a valid reply.
- Jump-start: new `runner/adapters/discord/commands.py`, new `runner/adapters/discord/thread_listener.py`, `runner/adapters/discord/client.py` (register `on_message`), `runner/ports/signal_repository.py` (the `write_answer` method), `tests/fakes/fake_signal_repository.py` (already has write methods — model tests against it), `tests/fakes/fake_state_store.py`.

### Acceptance Criteria
- `/status` reply includes the `[Offline / Standalone Bot]` badge when the state store shows the runner is not running.
- `/pause` and `/mode` reply with a non-empty offline notice string; they do not raise an exception or post nothing.
- `process_thread_reply` skips messages from bot authors.
- `process_thread_reply` skips messages in non-thread channels.
- `process_thread_reply` skips messages whose thread's parent channel ID differs from `config.discord.channel_id`.
- When `config.discord.notify_user_id` is non-empty, messages from other user IDs are skipped.
- `process_thread_reply` calls `signal_repository.write_answer("T042", content)` for a thread named `T042-some-slug`.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: /status in standalone mode**
- Setup: Bot running via `ticket_runner bot --run` (T075); `.agent/state.json` absent or `runner_status` not "running".
- Steps: Type `/status` in the configured Discord channel.
- Expected: Bot replies with runner state fields and `[Offline / Standalone Bot]` badge visible in the message.

**Scenario: /pause in standalone mode**
- Setup: Same as above.
- Steps: Type `/pause`.
- Expected: Bot replies with a clear offline notice; no error or empty response.

**Scenario: Thread reply captured**
- Setup: Bot running via `--run`; create a thread named `T042-test-slug` under the configured channel.
- Steps: Post any text message in the thread as the authorized user (or any user if `notify_user_id` is unset).
- Expected: `.agent/questions/T042.json` is written with the message content; bot posts a confirmation reply in the thread.

**Scenario: Unauthorized reply ignored**
- Setup: `notify_user_id` set to a specific user ID in `config.yaml`; a different user posts in the ticket thread.
- Steps: Post a reply as the unauthorized user.
- Expected: No `.agent/questions/` file is written; bot does not reply.

### Gotchas
- `process_thread_reply` must be a pure function (not an event handler method) so it can be unit-tested without a live Discord client.
- The regex `^([A-Z]\d{3,})` matches `T042`, `T100`, etc., from the start of the thread name — ensure the thread name format `{ticket_id}-{slug}` is matched reliably, including threads named without a trailing slug.
- `StateStore.load()` may return `None` if the state file is absent (bot started before the runner ever ran) — handle this gracefully with a "no state available" reply rather than an exception.
- Discord message content is only available with `Message Content Intent` enabled in the Developer Portal; without it, `message.content` will be an empty string.
