# T077 — Developer Portal onboarding guide (docs/discord-setup.md)
Status: completed
Completed: 2026-09-22T15:17:00Z
Spec: docs/specs/05a-discord-bot-and-gateway.md
Blocked by: T070

### Requirements
- Create `docs/discord-setup.md` covering the complete bot onboarding flow a developer must perform manually in the Discord Developer Portal and server settings, so they can go from zero to a passing `ticket_runner bot --smoke` without consulting any external Discord documentation.
- The guide must cover, in order:
  1. Creating a Discord Application and Bot User in the Developer Portal.
  2. Enabling `Message Content Intent` under Privileged Gateway Intents.
  3. Generating the OAuth2 invite URL with scopes `bot,applications.commands` and the correct permission integer for all 7 required permissions (Send Messages, Send Messages in Threads, Create Public Threads, Manage Threads, Manage Messages, Read Message History, Embed Links).
  4. Inviting the bot to the server using the generated URL.
  5. Obtaining the `channel_id` (right-click channel > Copy Channel ID, with Developer Mode enabled).
  6. Optionally obtaining the `guild_id` (right-click server icon > Copy Server ID) to bypass auto-detect.
  7. Setting `DISCORD_BOT_TOKEN` in the environment (PowerShell and bash variants).
  8. Updating `config.yaml` with `discord.channel_id`, and optionally `discord.guild_id` and `discord.notify_user_id`.
  9. Running `ticket_runner bot --smoke` to verify; interpreting the exit code and any error output.
- The guide is documentation only — no code changes.
- Jump-start: `docs/discord-setup.md` (new file). Reference the `DiscordConfig` field names added in T070 and the CLI flags added in T075–T076 so the guide stays in sync with the implementation.

### Acceptance Criteria
- `docs/discord-setup.md` exists and is readable.
- All 7 required permissions are named in the guide.
- The OAuth2 URL generation step includes the correct permission integer (computable from the 7 permissions via the Discord Permissions Calculator).
- The guide references `ticket_runner bot --smoke` and `ticket_runner doctor --live` as the two verification commands.
- The guide mentions `notify_user_id` and explains when and why to set it.
- A developer new to Discord bot setup can follow the guide start-to-finish and obtain a passing smoke run.

### Smoke Scenarios
**Scenario: Guide is self-contained**
- Setup: A fresh Discord account with no existing bots; a server the developer controls.
- Steps: Follow `docs/discord-setup.md` from step 1 to step 9 without opening any external URL except the Discord Developer Portal and the OAuth2 invite URL generated in step 3.
- Expected: `ticket_runner bot --smoke` exits 0 at the end of the guide.

### Gotchas
- The permission integer must be computed from the exact 7 permissions listed in the spec — include the integer value explicitly in the guide so developers can paste it directly into the OAuth2 URL without using a calculator.
- Discord Developer Mode (required to copy IDs) is toggled under User Settings > Advanced — mention this before the channel ID step.
- `notify_user_id` is a Discord user ID (snowflake), not a username — clarify the distinction and explain how to obtain it (Developer Mode > right-click user > Copy User ID).
- This guide must be written after T070 locks in the `DiscordConfig` field names and after T075–T076 lock in the CLI flags; if written before those tickets land, the field names or command flags may drift.
