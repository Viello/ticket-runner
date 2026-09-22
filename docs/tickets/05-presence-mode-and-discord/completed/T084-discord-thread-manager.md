# T084 — Discord thread manager (thread-per-ticket lifecycle)
Status: completed
Completed: 2026-09-22T16:32:00Z
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: T083

### Requirements
- Implement `DiscordThreadManager` at `runner/application/discord_thread_manager.py` as an application service injected with `DiscordGateway` (for raw API) and `DiscordLoggerImpl` (for Status Card / Live Digest). Accepts `discord_enabled: bool` — when `False`, all methods are no-ops.
- `open_ticket_thread(ticket, channel_id) -> tuple[str, str]`: posts the Status Card starter embed in `channel_id`, calls `DiscordGateway.create_thread(channel_id, name="{ticket_id}-{slug}", starter_message="…")`, pins the Status Card, starts the Live Digest. Returns `(thread_id, status_card_message_id)`.
- `close_ticket_thread(thread_id, status_card_message_id, commit_summary)`: posts a commit summary embed (green, title `✅ Committed`), edits the Status Card to `✅ Committed` phase, calls `DiscordGateway.archive_thread(thread_id)`.
- `update_status_card(thread_id, message_id, **fields)`: delegates to `DiscordLoggerImpl.update_status_card`.
- Tests use `FakeDiscordGateway` and a real `DiscordLoggerImpl` wired to it (or `FakeDiscordLogger` for routing tests).
- Verification: `pytest tests/ -k discord_thread_manager` — all tests green.

### Acceptance Criteria
- Thread name is exactly `{ticket_id}-{slug}` (e.g. `T042-defer-clean-slate-prompt`).
- Status Card is pinned immediately after thread creation — `pin_message` is called with `(thread_id, status_card_message_id)`.
- Live Digest is started (`post_message` for digest placeholder) immediately after thread open.
- Commit embed colour is `0x57F287` (Discord green); Status Card phase updated to `✅ Committed` before `archive_thread` is called.
- `archive_thread` is called exactly once during `close_ticket_thread`; no additional `post_message` calls after it.
- When `discord_enabled=False`, no `DiscordGateway` methods are invoked — all methods return `("", "")` or `None` silently.

### Smoke Scenarios
**Scenario: Thread opened on ticket start**
- Setup: `FakeDiscordGateway` configured to return `("thread-id-99", "msg-id-1")` for `create_thread`. `discord_enabled=True`.
- Steps: 1. Call `open_ticket_thread(ticket, channel_id="channel-1")`. 2. Inspect all gateway calls.
- Expected: `create_thread` called with `name="T042-defer-clean-slate"`. `pin_message` called with `("thread-id-99", "msg-id-1")`. A second `post_message` (Live Digest placeholder) called in `thread-id-99`. Returns `("thread-id-99", "msg-id-1")`.

**Scenario: Thread closed on ticket commit**
- Setup: `FakeDiscordGateway`, known `thread_id="thread-99"`, `message_id="msg-1"`.
- Steps: 1. Call `close_ticket_thread("thread-99", "msg-1", commit_summary="feat(discord): add logger")`. 2. Inspect calls.
- Expected: `post_message` call with green commit embed. `edit_message` call updating Status Card to `✅ Committed`. `archive_thread("thread-99")` called last.

**Scenario: No gateway calls in local-only mode**
- Setup: `discord_enabled=False`.
- Steps: 1. Call `open_ticket_thread(ticket, channel_id="channel-1")`. 2. Call `close_ticket_thread("x", "y", "summary")`.
- Expected: Zero calls to any `FakeDiscordGateway` method.

### Gotchas
- The starter message passed to `DiscordGateway.create_thread` becomes the parent (non-thread) message — it is the Status Card itself. The `thread_id` and `starter_message_id` are both returned and both must be stored so the Status Card can be edited later.
- Discord does not allow pinning a message before the thread exists — `create_thread` must complete before `pin_message`.
- `archive_thread` sets both `archived=True` and `locked=True` per the spec; calling it on an already-locked thread must not raise — handle `DiscordGatewayError` gracefully by logging and continuing.
