# Spec 05: Presence Mode and Discord Integration

## Problem Statement

Developers working at their desks experience notification fatigue if every milestone and prompt sends mobile or remote pings, yet walking away from the computer leaves the autonomous runner stalled indefinitely when clarification questions or verification failures arise.

## Solution

Provide a dual Presence Mode (`nearby` vs `away`) that silences remote alerts while the developer is actively at the terminal, combined with an automated 3-minute idle escalation timer. Embed an in-process Discord bot using `discord.py` that manages a clean Thread-per-Ticket lifecycle, handles interactive questions remotely, and automatically resets Presence Mode to `nearby` upon receiving a remote response.

## User Stories

1. As a developer, I want the Runner to default to `nearby` mode, keeping notifications and question prompts local to my terminal while I am at my desk.
2. As a developer, I want to press `[m]` in the terminal to immediately toggle between `nearby` and `away` mode when I leave my desk.
3. As a developer, I want the Runner to automatically switch to `away` mode and send an urgent Discord ping if a question prompt sits unanswered at the terminal for 3 minutes.
4. As a developer, I want the in-process Discord bot to create a dedicated thread for each Ticket in `#ticket-runner` upon ticket start, keeping ticket discussions cleanly segregated.
5. As a developer, I want token warnings (120k), handoff notices, and Gatekeeper diagnostic logs posted directly into the Ticket's Discord thread in `away` mode.
6. As a developer, I want to answer clarification questions directly inside the Discord thread, having my response update the question Signal and resume Worker execution.
7. As a developer, I want answering an escalated prompt on Discord to automatically reset Presence Mode back to `nearby`, so that subsequent local actions do not produce redundant remote alerts.
8. As a developer, I want to issue Discord slash commands (`/mode nearby`, `/mode away`, `/pause`, `/status`) to remotely monitor and control the Runner.
9. As a developer, I want completed Ticket threads automatically archived and locked upon verification and commit, keeping the channel clean and focused.
10. As a developer, I want the Runner to require Discord bot credentials during startup Doctor checks unless the `--local-only` flag is passed, ensuring remote monitoring is not silently broken.
11. As a developer, I want Discord bot operations to execute natively within the Runner's single `asyncio` event loop, eliminating multi-process coordination bugs.

## Implementation Decisions

- **In-Process Bot Execution**: The Discord client is initialized directly using `discord.py` within the `asyncio` event loop. The bot token is retrieved strictly from the environment variable specified in `config.yaml` (`token_env: "DISCORD_BOT_TOKEN"`).
- **Thread-per-Ticket Lifecycle**:
  1. Ticket start: Bot posts starter message in `channel_id` and invokes `create_thread(name="{ticket_id}-{slug}")`.
  2. Active run: Thread receives milestone notices, token warnings (120k), and Gatekeeper logs.
  3. Ticket completion: Bot posts commit summary and invokes `thread.edit(archived=True, locked=True)`.
- **Inactivity Escalation Timer**: When a prompt requiring human input (question signal or Circuit Breaker trip) is displayed in `nearby` mode, an `asyncio` timer is scheduled for `idle_escalation_minutes` (default: 3 minutes). If answered locally, the timer is cancelled. If it expires, the Runner transitions to `away` mode and posts an `@mention` notification in Discord.
- **Auto-Reset on Discord Reply**: Receiving a valid answer message in a Discord thread immediately sets `presence_mode = "nearby"` in the state machine.
- **Discord Gateway Seam**: All Discord API interactions (sending messages, creating threads, listening to replies) are abstracted behind a `DiscordGateway` protocol, allowing test fixtures to simulate Discord interactions without network I/O.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that idle timers trigger mode transitions, that question signals are updated when thread replies are received, that threads are archived upon completion, and that `--local-only` disables Discord startup checks. Tests do not inspect discord.py internal event dispatchers.
- **Modules Tested**: Presence coordinator, idle escalation monitor, Discord thread manager, and notification router.
- **Seams and Test Doubles**: Tests utilize a fake `DiscordGateway` implementing the protocol in-memory, recording posted messages and simulating user replies.

## Out of Scope

- Multi-channel fan-out across multiple Discord servers.
- Voice channel alerts or audio notifications.
- Slack or Telegram adapters (architecture supports them via gateways, but initial implementation targets Discord).

## Further Notes

- The Thread-per-Ticket pattern ensures that even after hundreds of completed tickets, the main Discord channel remains completely uncluttered, with historical context cleanly archived under threads.
