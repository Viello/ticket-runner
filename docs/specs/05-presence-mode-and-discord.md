# Spec 05: Presence Mode and Discord Integration

## Problem Statement

Developers working at their desks experience notification fatigue if every milestone and prompt sends mobile or remote pings, yet walking away from the computer leaves the autonomous runner stalled indefinitely when clarification questions or verification failures arise. Additionally, with no structured log of what the Worker did or what the LLM produced, post-mortems and debugging are slow and depend entirely on local terminal scroll-back.

## Solution

Provide a dual Presence Mode (`nearby` vs `away`) that silences routine remote alerts while the developer is actively at the terminal, combined with an automated 3-minute idle escalation timer. Embed an in-process Discord bot using `discord.py` that manages a clean Thread-per-Ticket lifecycle with a pinned Status Card, a Live Digest of LLM output, structured severity-routed log messages, and interactive question handling. All Discord API calls are abstracted behind a `DiscordGateway` protocol; all logging logic (severity routing, chunking, embed construction) sits behind a `DiscordLogger` port above it.

## User Stories

1. As a developer, I want the Runner to default to `nearby` mode, keeping notifications and question prompts local to my terminal while I am at my desk.
2. As a developer, I want to press `[m]` in the terminal to immediately toggle between `nearby` and `away` mode when I leave my desk.
3. As a developer, I want the Runner to automatically switch to `away` mode and send an urgent Discord ping if a question prompt sits unanswered at the terminal for 3 minutes.
4. As a developer, I want the in-process Discord bot to create a dedicated thread for each Ticket in `#ticket-runner` upon ticket start, keeping ticket discussions cleanly segregated.
5. As a developer, I want a pinned Status Card at the top of each thread — showing ticket ID, slug, spec, current phase, attempt count, token usage, and timestamps — updated in-place as the ticket progresses, so I never need to scroll to know where a ticket stands.
6. As a developer, I want a Live Digest message in each thread that is edited in-place to show a rolling window of what the LLM is currently writing, so I can follow Worker activity without being flooded with posts.
7. As a developer, I want critical events (Circuit Breaker trips, hard ceiling hits, handoffs, verification failures, question signals, and runner crashes) posted to the Ticket thread regardless of Presence Mode, so the thread is always a complete audit trail.
8. As a developer, I want routine events (phase transitions, milestone notices, token warnings, security review bookends, queue changes) posted to the Ticket thread only in `away` mode, suppressing noise when I am at the terminal.
9. As a developer, I want critical log posts rendered as colour-coded Discord Embeds (red for critical/failure, yellow for warning, green for milestone), and routine posts as plain text with emoji prefixes, so I can triage at a glance.
10. As a developer, I want any log payload exceeding Discord's 2,000-character limit to be split on the last newline before 1,950 characters, with continuation headers `[continued N/M]`, so no log content is lost and lines are never broken mid-way.
11. As a developer, I want to answer clarification questions directly inside the Discord thread, having my response update the question Signal and resume Worker execution.
12. As a developer, I want answering an escalated prompt on Discord to automatically reset Presence Mode back to `nearby`, so that subsequent local actions do not produce redundant remote alerts.
13. As a developer, I want to issue Discord slash commands (`/mode nearby`, `/mode away`, `/pause`, `/status`) to remotely monitor and control the Runner.
14. As a developer, I want completed Ticket threads automatically archived and locked upon verification and commit, keeping the channel clean and focused.
15. As a developer, I want the Runner to require Discord bot credentials during startup Doctor checks unless the `--local-only` flag is passed, ensuring remote monitoring is not silently broken.
16. As a developer, I want Discord bot operations to execute natively within the Runner's single `asyncio` event loop, eliminating multi-process coordination bugs.

## Implementation Decisions

### In-Process Bot Execution

The Discord client is initialized directly using `discord.py` within the `asyncio` event loop. The bot token is retrieved strictly from the environment variable specified in `config.yaml` (`token_env: "DISCORD_BOT_TOKEN"`).

### Two-Port Discord Architecture

Two named ports separate raw API access from logging logic:

- **`DiscordGateway`**: Raw Discord API seam. Exposes primitive operations: `post_message`, `edit_message`, `pin_message`, `create_thread`, `edit_thread`, `archive_thread`. Test doubles implement this protocol to record calls without network I/O.
- **`DiscordLogger`**: Logging logic port above `DiscordGateway`. Owns severity routing (critical vs routine), embed construction, message chunking, Status Card edits, and Live Digest rate-limited edits. Accepts structured log events from the Runner and decides format, targeting, and dispatch. Tests for routing and chunking logic use a fake `DiscordLogger`; tests for the API boundary use a fake `DiscordGateway`.

### Thread-per-Ticket Lifecycle

1. **Ticket start**: Bot posts a Status Card starter message in `channel_id` and invokes `create_thread(name="{ticket_id}-{slug}")`. The Status Card is immediately pinned.
2. **Active run**: Thread receives Live Digest updates, critical log embeds, and (in `away` mode) routine plain-text log posts.
3. **Ticket completion**: Bot posts a commit summary embed, edits the Status Card to `✅ Committed`, then invokes `thread.edit(archived=True, locked=True)`.

### Status Card

A single message pinned at the top of each Ticket thread, edited in-place at every phase transition. Fields:

```
Ticket:       T042 · defer-clean-slate-prompt-until-exit
Spec:         05-presence-mode-and-discord
Status:       🟡 Verifying   (Running → Reviewing → Verifying → ✅ Committed)
Attempt:      2 / 3
Tokens:       ~118k / 150k  ████████░░ 79%
Started:      13:04 UTC
Last updated: 13:11 UTC
```

The `Last updated` timestamp doubles as a liveness signal: a stale card indicates a bot crash or frozen Runner.

### Live Digest

A single plain-text message posted at the start of each Session Run, edited in-place to show a rolling 500-character window of the LLM's current response content. The edit fires at most once every 5 seconds or every ~200 tokens, whichever comes first, to stay within Discord rate limits. The message is marked `[done]` when the Session Run ends and is not deleted, leaving a final snapshot of the LLM's last output in the thread.

### Event Classification and Severity Routing

| Event | Criticality | Format | Mode gate |
|---|---|---|---|
| Circuit Breaker trip (attempt N of 3) | 🔴 Critical | Red embed | Always |
| Hard ceiling hit (150k tokens) | 🔴 Critical | Red embed | Always |
| Handoff triggered (135k threshold) | 🔴 Critical | Yellow embed | Always |
| Question signal posted (needs answer) | 🔴 Critical | Yellow embed + `@mention` | Always |
| Runner shutdown / crash | 🔴 Critical | Red embed | Always |
| Verification failed (with diagnostic) | 🔴 Critical | Red embed | Always |
| Live Digest (rolling LLM excerpt) | 🔴 Critical | Plain text, edited in-place | Always |
| Worker phase transition | 🟢 Routine | Plain text `🔄` | `away` only |
| Milestone notice (review started, signal emitted) | 🟢 Routine | Plain text `✅` | `away` only |
| Token warning (120k threshold) | 🟢 Routine | Plain text `⚠️` | `away` only |
| Security review start / end | 🟢 Routine | Plain text `🔒` | `away` only |
| Queue state change (enqueue, dequeue, exhausted) | 🟢 Routine | Plain text `📋` | `away` only |
| Ticket committed (success) | 🟢 Routine | Plain text `✅` | `away` only |
| Runner startup | 🟢 Routine | Plain text `🚀` | `away` only |

### Message Chunking

Any log payload exceeding 1,950 characters is split on the last newline before the 1,950-character boundary. Each chunk is posted as a separate message prefixed with `[continued N/M]` where N is the chunk index (1-based) and M is the total chunk count. This applies to both plain-text routine posts and the body of embed descriptions. Embed titles and field names are never chunked — they are truncated to Discord's per-field limits.

### Inactivity Escalation Timer

When a prompt requiring human input (question Signal or Circuit Breaker trip) is displayed in `nearby` mode, an `asyncio` timer is scheduled for `idle_escalation_minutes` (default: 3 minutes). If answered locally, the timer is cancelled. If it expires, the Runner transitions to `away` mode and posts a critical embed with an `@mention` in the Ticket thread.

### Auto-Reset on Discord Reply

Receiving a valid answer message in a Discord thread immediately sets `presence_mode = "nearby"` in the Presence coordinator's state machine.

## UI Contract

This section defines port-boundary contracts for Discord output — the exact embed fields, formats, and routing rules that `DiscordLogger` and `DiscordGateway` must produce. Behavioural fidelity is the hard constraint; aesthetic rendering is Discord's responsibility. For `presence_mode` and `tokens` field names, see Spec 06 § State Schema (authoritative).

### Status Card Embed Fields

The Status Card is a Discord embed posted as the first message in each Ticket thread and pinned immediately. It is edited in-place at every phase transition via `DiscordGateway.edit_message`.

Verbatim field layout (monospace, as seen in Discord code block inside the embed description):

```
Ticket:       T042 · defer-clean-slate-prompt-until-exit
Spec:         05-presence-mode-and-discord
Status:       🟡 Verifying   (Running → Reviewing → Verifying → ✅ Committed)
Attempt:      2 / 3
Tokens:       ~118k / 150k  ████████░░ 79%
Started:      13:04 UTC
Last updated: 13:11 UTC
```

Rules:
- Embed colour (Discord API integer): `0x5865F2` (blurple) — not severity-routed; Status Card is always neutral
- `Tokens` line format: `~{round(current/1000)}k / 150k  {bar} {pct}%` — token bar uses the same 10-block `█`/`░` format defined in Spec 06 § Token Bar Format (blocks 1–8 green, 9 yellow at ≥ 120k, 10 red at ≥ 135k)
- `Last updated` is refreshed on every `edit_message` call; staleness indicates a bot crash or frozen Runner
- Field label column is right-padded with spaces to align colons at column 14
- `Status` field shows the current phase with the full breadcrumb trail in parentheses; breadcrumb order: `Running → Reviewing → Verifying → ✅ Committed`

### Live Digest Contract

The Live Digest is a single plain-text message posted at the start of each Session Run via `DiscordGateway.post_message`. It is edited in-place by `DiscordGateway.edit_message`.

Rules:
- One Live Digest message per Session Run; never deleted, never split into multiple messages
- Rate-limit floor: edits fire at most once every 5 seconds — a faster stream is buffered and the next edit posts the accumulated content
- Rolling window: the last 500 characters of raw LLM stream content (not token count — character count)
- On Session Run end: the final edit appends `\n[done]` to the current window content and stops further edits
- The `[done]` marker is never removed; it is the final snapshot of that Session Run

Verbatim end-of-run format:
```
…inspecting existing implementation in `src/runner/`
Writing `tests/unit/test_presence_coordinator.py`…
All checks pass. Emitting ready signal.
[done]
```

### Question Signal Embed

When a question Signal is posted, `DiscordLogger` sends two API calls to the thread: a plain-text `@mention` message followed immediately by a yellow embed.

**Message 1 — mention (plain text, `post_message`):**
```
<@{discord_user_id}>
```
Rule: `discord_user_id` comes from `config.yaml: discord.notify_user_id`. Sent as standalone message content — not inside the embed — so Discord triggers a push notification on the user's device.

**Message 2 — question embed (`post_message`):**

| Embed field | Value |
|---|---|
| colour | `0xFEE75C` (yellow) — question is a pause, not a failure |
| title | `❓ Worker Question` |
| description | `{question_body}` from the question Signal file |
| footer text | `Posted at {HH:MM} UTC · Reply in this thread to answer` |

Rule: the two messages are posted in immediate succession. No other messages are posted between them. The thread reply that resolves the question must update the Signal file at `.agent/questions/{ticket_id}.json` and trigger `presence_mode → "nearby"` reset via the Presence coordinator.

### Message Chunking Header

Verbatim header format: `[continued 2/3]` — 1-indexed chunk number, slash-separated, enclosed in square brackets, on its own line before the chunk body.

Rules:
- Trigger: any payload passed to `DiscordLogger` whose character count exceeds 1,950
- Split point: last `\n` at or before character position 1,950; if no newline exists in the payload, split at exactly 1,950
- Chunk 1 has no prefix — it is posted as-is
- Chunks 2…M are each prefixed with `[continued N/M]\n` on its own line
- `M` (total chunk count) is computed before any chunk is posted; all headers reference the same final `M`
- Applies to both plain-text routine posts and embed description bodies
- Embed **title** and **field names** are never chunked — truncate to Discord API per-field limits (256 chars for title; 1,024 chars for field value) instead

Verbatim example for a 2,451-character payload split at position 1,943 (last newline before 1,950):
```
[chunk 1 — 1,943 chars, no prefix]

[continued 2/2]
[remaining 508 chars]
```

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that idle timers trigger mode transitions, that question Signals are updated when thread replies are received, that threads are archived upon completion, and that `--local-only` disables Discord startup checks. Tests do not inspect `discord.py` internal event dispatchers.
- **Modules Tested**: Presence coordinator, idle escalation monitor, Discord thread manager, notification router, `DiscordLogger` chunking logic, Status Card editor, Live Digest rate limiter.
- **Seams and Test Doubles**:
  - Fake `DiscordGateway`: records raw API calls (messages posted, messages edited, threads created) and simulates user replies. Used for integration-level tests.
  - Fake `DiscordLogger`: records structured log events with their resolved severity and format. Used for unit tests of Runner → Logger routing, bypassing chunking and embed construction.
- **Chunking Tests**: Dedicated unit tests verify that payloads of 1,950, 1,951, 3,900, and 3,901 characters produce the correct number of chunks, that splits occur on newlines, and that continuation headers are correctly numbered.
- **Live Digest Tests**: Verify that the rate limiter suppresses edits below the 5-second floor and that the final `[done]` marker is always written when a Session Run ends.

## Out of Scope

- Multi-channel fan-out across multiple Discord servers.
- Voice channel alerts or audio notifications.
- Slack or Telegram adapters (architecture supports them via gateway ports, but initial implementation targets Discord).

## Further Notes

- The Thread-per-Ticket pattern ensures that even after hundreds of completed tickets, the main Discord channel remains completely uncluttered, with historical context cleanly archived under threads.
- The `DiscordLogger` / `DiscordGateway` separation means Discord can be replaced with any future adapter (Slack, Telegram, webhook) by swapping only the `DiscordGateway` implementation — the `DiscordLogger` routing logic is adapter-agnostic.
- The Live Digest is always-on (not mode-gated) because it is the primary signal that the Worker is alive and making progress. A thread with a stale Live Digest and a stale Status Card is the canonical indicator of a hung session.
