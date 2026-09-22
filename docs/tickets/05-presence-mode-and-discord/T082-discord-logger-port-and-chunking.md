# T082 — DiscordLogger port and chunking engine
Status: pending
Spec: docs/specs/05-presence-mode-and-discord.md
Blocked by: None

### Requirements
- Introduce a `DiscordLogger` protocol (port) at `runner/ports/discord_logger.py` with a `FakeDiscordLogger` test double in `tests/fakes/`.
- Implement `DiscordLoggerImpl` at `runner/adapters/discord/logger.py` that accepts structured log events (severity + payload + thread_id), applies the severity routing table from the spec (critical always / routine `away`-only based on `presence_mode`), and dispatches via the injected `DiscordGateway`.
- Payloads exceeding 1,950 characters are split on the last `\n` at or before character 1,950; if no newline exists, split at exactly 1,950. Chunk 1 has no prefix; chunks 2…M are prefixed with `[continued N/M]\n`. Total chunk count `M` is computed before any chunk is posted.
- Chunking applies to both plain-text routine posts and embed description bodies. Embed titles and field names are never chunked — truncate to Discord API per-field limits instead.
- Anchor patterns: `runner/ports/discord_gateway.py` (protocol shape), `runner/adapters/discord/gateway.py` (call pattern), `runner/domain/state.py` (`VALID_PRESENCE_MODES`, `presence_mode` field).
- Verification: `pytest tests/ -k discord_logger` — all chunking tests green.

### Acceptance Criteria
- `DiscordLogger` protocol is defined with at minimum `log(event_type, payload, thread_id, presence_mode)` and `post_embed(thread_id, embed_dict)` methods.
- `FakeDiscordLogger` records all calls with resolved severity and suppression decisions; tests for routing bypass chunking.
- `DiscordLoggerImpl` respects the full event classification table from the spec.
- Chunking unit tests verify: 1,950-char payload → 1 chunk; 1,951-char payload → 2 chunks; 3,900-char payload → 2 chunks; 3,901-char → 3 chunks.
- Split always occurs on the last `\n` before 1,950; falls back to hard split at 1,950 when no newline exists.
- Continuation headers are correctly numbered `[continued 2/3]` format (1-indexed, slash-separated).

### Smoke Scenarios
**Scenario: Chunking splits on newline**
- Setup: Construct a `FakeDiscordGateway`, inject into `DiscordLoggerImpl` with `presence_mode = "away"`. Build a string of 2,100 chars containing a `\n` at position 1,940.
- Steps: 1. Call `log("routine", payload, thread_id="T", presence_mode="away")`. 2. Inspect calls recorded by `FakeDiscordGateway`.
- Expected: Exactly 2 `post_message` calls. Second call content starts with `[continued 2/2]\n`. Combined content equals original payload with no characters lost.

**Scenario: No-newline hard split**
- Setup: Construct a `FakeDiscordGateway` and a 2,100-char string with no `\n` characters.
- Steps: 1. Call `log("routine", payload, thread_id="T", presence_mode="away")`. 2. Inspect calls.
- Expected: Chunk 1 is exactly 1,950 chars; chunk 2 is `[continued 2/2]\n` + remaining 150 chars.

**Scenario: Critical event always posts in nearby mode**
- Setup: `presence_mode = "nearby"`. Emit a `circuit_breaker_trip` event (critical severity).
- Steps: Call `log("circuit_breaker_trip", "Attempt 3/3 failed", thread_id="T", presence_mode="nearby")`.
- Expected: `FakeDiscordGateway` records exactly 1 `post_message` call with a red embed (colour `0xFF0000` or equivalent).

**Scenario: Routine event suppressed in nearby mode**
- Setup: `presence_mode = "nearby"`. Emit a `phase_transition` event (routine severity).
- Steps: Call `log("phase_transition", "Running → Reviewing", thread_id="T", presence_mode="nearby")`.
- Expected: `FakeDiscordGateway` records 0 `post_message` calls.

**Scenario: Routine event posts in away mode**
- Setup: `presence_mode = "away"`. Emit a `phase_transition` event.
- Steps: Call `log("phase_transition", "Running → Reviewing", thread_id="T", presence_mode="away")`.
- Expected: `FakeDiscordGateway` records 1 `post_message` call with content starting with `🔄`.

### Gotchas
- `M` (total chunk count) must be computed before any chunk is posted so continuation headers reference the correct final count — don't post chunk 1 then compute the rest.
- Discord API limits: embed `description` max 4,096 chars; embed `title` max 256 chars; field `value` max 1,024 chars. The 1,950-char chunking applies to the payload passed to `DiscordLogger`, not Discord's own per-embed limits.
- The `FakeDiscordLogger` records suppression decisions (not just dispatched calls) so unit tests can assert that routing logic ran correctly even when no gateway call was made.
