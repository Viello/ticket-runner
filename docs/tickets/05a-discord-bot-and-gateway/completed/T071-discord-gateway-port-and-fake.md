# T071 — DiscordGateway port and FakeDiscordGateway test double
Status: completed
Completed: 2026-09-22T07:38:30Z
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T070

### Requirements
- Define `DiscordGateway` as a `runtime_checkable` Protocol in `runner/ports/discord_gateway.py` with six async methods: `post_message`, `edit_message`, `pin_message`, `create_thread`, `edit_thread`, `archive_thread`. Method signatures must match the spec exactly (see Implementation Decisions > DiscordGateway Port). Embed payloads are plain `dict`; no `discord.py` types cross the boundary.
- Export `DiscordGateway` and `DiscordGatewayError` from `runner/ports/__init__.py` alongside the existing ports.
- Implement `FakeDiscordGateway` in `tests/fakes/fake_discord_gateway.py`. It records every call as a `DiscordCall` named tuple appended to `self.calls: list[DiscordCall]`. It maintains an in-memory message/thread map with auto-incrementing integer IDs. It exposes `pending_replies: list[str]` that tests append to in order to simulate user thread replies.
- Write unit tests verifying: both `FakeDiscordGateway` and the yet-to-exist real adapter shell pass `isinstance(gateway, DiscordGateway)`; all six call types produce correct `DiscordCall` entries on `FakeDiscordGateway`.
- Jump-start: `runner/ports/__init__.py` (add `DiscordGateway`), new file `runner/ports/discord_gateway.py`, new file `tests/fakes/fake_discord_gateway.py`, `tests/fakes/__init__.py` (export the new fake), existing fake pattern: `tests/fakes/fake_signal_repository.py`.

### Acceptance Criteria
- `isinstance(FakeDiscordGateway(), DiscordGateway)` is `True` at runtime.
- `FakeDiscordGateway.post_message` returns an auto-incremented string message ID and appends a `DiscordCall` to `calls`.
- `FakeDiscordGateway.create_thread` returns a `(thread_id, starter_message_id)` tuple; both IDs are strings.
- `FakeDiscordGateway.archive_thread` is equivalent to `edit_thread(thread_id, archived=True, locked=True)`.
- `DiscordGateway` and `DiscordGatewayError` are importable from `runner.ports`.
- `pytest tests/` passes with no regressions.

### Smoke Scenarios
**Scenario: Verify DiscordGateway protocol conformance and fake gateway call recording**
- Setup: None
- Steps: Run `python -c "import asyncio; from runner.ports import DiscordGateway, DiscordGatewayError; from tests.fakes import FakeDiscordGateway; fake = FakeDiscordGateway(); assert isinstance(fake, DiscordGateway); asyncio.run(fake.post_message('chan-1', 'hello')); assert len(fake.calls) == 1 and fake.calls[0].method == 'post_message'; print('DiscordGateway port and fake verified')"`
- Expected: Prints `DiscordGateway port and fake verified` with exit code 0.

### Gotchas
- `runtime_checkable` Protocols only check for method presence, not signatures — the fake's async signatures must exactly match the Protocol or structural subtyping checks will pass incorrectly for the wrong reasons.
- `create_thread` must return both the thread ID and the starter message ID as separate values — the starter message ID is needed by Spec 05b for Status Card pinning; don't collapse them into one.
- Keep `FakeDiscordGateway` in `tests/fakes/`, not in the production source tree, to avoid importing it from production code accidentally.
