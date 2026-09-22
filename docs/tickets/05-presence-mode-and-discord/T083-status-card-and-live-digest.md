# T083 — Status Card and Live Digest
Status: pending
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: T082

### Requirements
- Extend `DiscordLoggerImpl` (or add a companion `DiscordThreadLogger`) with: `post_status_card(ticket, thread_id)` → posts the blurple embed with the exact verbatim field layout from the spec, then calls `DiscordGateway.pin_message` for the returned message ID.
- `update_status_card(thread_id, message_id, *, status, attempt, tokens_current, started_at)` → constructs the updated embed and calls `DiscordGateway.edit_message` in-place; sets `Last updated` to current UTC.
- Token bar format: `~{round(current/1000)}k / 150k  {bar} {pct}%` — 10 `█`/`░` blocks; blocks 1–8 green (plain), block 9 yellow at ≥ 120k (token warning threshold), block 10 red at ≥ 135k (handoff threshold). Bar construction is a pure function and unit-tested independently.
- `start_live_digest(thread_id)` → posts a single plain-text message; records `(thread_id, message_id)` state.
- `update_live_digest(content_chunk)` → appends to rolling 500-char window; fires `edit_message` at most once per 5-second floor (uses `asyncio` monotonic clock). Faster streams are buffered; next scheduled edit posts accumulated content.
- `finish_live_digest()` → fires one final `edit_message` appending `\n[done]`; stops further edits.
- Anchor patterns: `runner/adapters/discord/gateway.py` (`post_message`, `edit_message`, `pin_message`), `runner/domain/state.py` (`TokenState` fields for token values).
- Verification: `pytest tests/ -k "status_card or live_digest"` — all tests green.

### Acceptance Criteria
- Status Card embed colour is `0x5865F2` (blurple) — not severity-routed.
- Field label column is right-padded with spaces so colons align at column 14 (matching verbatim spec layout).
- `Status` field shows current phase with full breadcrumb trail in parentheses: `Running → Reviewing → Verifying → ✅ Committed`.
- `pin_message` is called with the status card's message ID immediately after `post_message`.
- Live Digest rate-limiter test: submit 20 updates within 1 second; confirm at most 1 `edit_message` call fired (rate floor enforced).
- `finish_live_digest()` always appends exactly `\n[done]` — even if the last content window is empty.
- Token bar pure function verified for: 0k (all ░), 80k (6 blocks), 120k (9th block), 135k (10th block), 150k (all █).

### Smoke Scenarios
**Scenario: Status Card posted and pinned on ticket start**
- Setup: Inject `FakeDiscordGateway`. Create a `Ticket` with `id="T042"` and `slug="defer-clean-slate"`.
- Steps: 1. Call `post_status_card(ticket, thread_id="999")`. 2. Inspect `FakeDiscordGateway` calls.
- Expected: One `post_message` call with embed containing `T042 · defer-clean-slate` in description. One `pin_message` call with the returned message ID. Embed colour is `0x5865F2`.

**Scenario: Status Card edited in-place on phase change**
- Setup: `FakeDiscordGateway`, known `status_card_message_id = "111"`.
- Steps: 1. Call `update_status_card("999", "111", status="🟡 Reviewing", attempt=2, tokens_current=80000, started_at="13:04 UTC")`. 2. Inspect calls.
- Expected: Exactly 1 `edit_message` call (no new `post_message`). Updated description contains `🟡 Reviewing` and `(Running → Reviewing → Verifying → ✅ Committed)`.

**Scenario: Live Digest rate-limit floor**
- Setup: Patch asyncio time so 5 seconds = 100ms wall time. Start live digest on `FakeDiscordGateway`.
- Steps: 1. Call `update_live_digest()` 20 times in rapid succession (< 100ms total). 2. Wait 200ms. 3. Count `edit_message` calls.
- Expected: At most 1 `edit_message` call for the rapid burst; a final edit fires after the 5-second floor.

**Scenario: Live Digest `[done]` marker on session end**
- Setup: `FakeDiscordGateway` with active live digest.
- Steps: 1. Call `update_live_digest("last chunk")`. 2. Call `finish_live_digest()`. 3. Inspect last `edit_message` call.
- Expected: Final edit content ends with `\n[done]`. No further edits after `finish_live_digest()` call.

### Gotchas
- The Live Digest rolling window is 500 *characters*, not token count — ensure `content[-500:]` slicing, not token estimation.
- The rate-limiter must use `asyncio` monotonic time (`loop.time()` or `asyncio.get_event_loop().time()`), not `time.time()`, so tests can fast-forward without wall-clock delays.
- `finish_live_digest()` must guarantee the `\n[done]` write even if an in-flight rate-limited edit is pending — cancel the pending task and write immediately.
- Status Card `Last updated` field is UTC time only (HH:MM UTC) to match the spec verbatim layout — do not include date.
