# Discord Developer Portal Onboarding Guide

This guide walks through configuring a Discord bot application and server settings for **Ticket Runner**. Following these steps will take you from a fresh Discord account to passing pre-flight verification with `ticket_runner doctor --live` and `ticket_runner bot --smoke`.

No prior Discord bot development experience or external documentation is required.

---

## 1. Create a Discord Application & Bot User

1. Navigate to the [Discord Developer Portal](https://discord.com/developers/applications) and log in with your Discord account.
2. Click **New Application** in the top right.
3. Enter a name (for example, `Ticket Runner`) and agree to the Developer Terms of Service, then click **Create**.
4. In the left sidebar, navigate to **Bot**.
5. Locate the **Token** section and click **Reset Token** (confirm if prompted).
6. Click **Copy** to save the generated bot token to your clipboard.
   > [!CAUTION]
   > Keep your bot token secure. Never commit it to git or paste it into public channels. Ticket Runner reads this token exclusively from an environment variable (`DISCORD_BOT_TOKEN`).

---

## 2. Enable Privileged Gateway Intents

Ticket Runner monitors ticket threads for developer replies. This requires the **Message Content Intent**:

1. While still on the **Bot** page in the Developer Portal, scroll down to the **Privileged Gateway Intents** section.
2. Toggle **Message Content Intent** to **ON**.
3. Click **Save Changes** at the bottom of the page.

---

## 3. Generate the OAuth2 Bot Invite URL

Ticket Runner adheres to least privilege and requires exactly 7 permissions:
- **Send Messages**
- **Send Messages in Threads**
- **Create Public Threads**
- **Manage Threads**
- **Manage Messages**
- **Read Message History**
- **Embed Links**

The calculated permission integer for this exact set of 7 permissions is:
```text
326417606656
```

### URL Generation Steps
1. In the Developer Portal left sidebar, navigate to **OAuth2** > **URL Generator** (or **OAuth2**).
2. Under **Scopes**, select:
   - `bot`
   - `applications.commands` (enables slash commands like `/status`, `/pause`, and `/mode`)
3. Under **Bot Permissions**, select the 7 required permissions listed above, or use the precomputed permission integer `326417606656`.
4. Copy the generated invite URL at the bottom, or assemble it directly with your Application Client ID:
   ```text
   https://discord.com/oauth2/authorize?client_id=<YOUR_CLIENT_ID>&scope=bot%20applications.commands&permissions=326417606656
   ```
   *(Find your Client ID under **General Information** > **Application ID**).*

---

## 4. Invite the Bot to Your Server

1. Paste the generated OAuth2 invite URL into your web browser.
2. Select your Discord server from the **Add to Server** dropdown.
3. Click **Continue**.
4. Review the requested permissions (verify all 7 permissions are checked).
5. Click **Authorize** (and complete the CAPTCHA if prompted).
6. Verify that the bot appears in your server's member list.

---

## 5. Enable Developer Mode & Obtain Channel ID

To copy Discord snowflake IDs (channel, server, and user IDs), you must enable Developer Mode:

1. In Discord, open **User Settings** (the gear icon next to your avatar in the bottom left).
2. Under **App Settings**, click **Advanced**.
3. Toggle **Developer Mode** to **ON**.
4. Close User Settings.

### Obtain `channel_id`
1. Locate the text channel where Ticket Runner should create ticket threads.
2. Right-click the channel in the channel list and select **Copy Channel ID**.
3. Ensure the bot has access to this channel and holds the required permissions in the channel's permission overrides.

---

## 6. (Optional) Obtain Server ID (`guild_id`) & User ID (`notify_user_id`)

### Server ID (`guild_id`)
By default, Ticket Runner automatically discovers the guild ID from `channel_id` at startup. To bypass auto-detection and force instant slash command synchronization to a specific guild:
1. Right-click your server icon in the left server list.
2. Click **Copy Server ID**.

### User ID (`notify_user_id`)
`notify_user_id` is a numeric Discord snowflake ID, **not** a username or tag (e.g. `123456789012345678`, not `@username`).
- **Why set it?** On shared servers, configuring `notify_user_id` restricts the thread listener so that only messages from your account can answer runner questions or interact with ticket prompts, preventing unauthorized inputs.
- **How to obtain it:**
  1. In your server member list or chat, right-click your profile.
  2. Click **Copy User ID**.

---

## 7. Set Environment Variable (`DISCORD_BOT_TOKEN`)

Set the bot token copied in Step 1 in your operating system environment.

### PowerShell (Windows)
```powershell
$env:DISCORD_BOT_TOKEN = "your_bot_token_here"
```

To persist across PowerShell sessions:
```powershell
[System.Environment]::SetEnvironmentVariable('DISCORD_BOT_TOKEN', 'your_bot_token_here', 'User')
```

### Bash / Zsh (Linux / macOS / WSL)
```bash
export DISCORD_BOT_TOKEN="your_bot_token_here"
```

To persist, add the export line to your `~/.bashrc` or `~/.zshrc`.

---

## 8. Update `config.yaml`

Open `config.yaml` in the repository root and configure the `discord` section with your snowflake IDs:

```yaml
discord:
  # Enable remote Discord bot integration
  enabled: true
  # Environment variable containing the bot token
  token_env: "DISCORD_BOT_TOKEN"
  # Target channel snowflake ID where threads will be created (Required)
  channel_id: "123456789012345678"
  # Guild snowflake ID for instant slash command sync (Optional, bypasses auto-detect)
  guild_id: "123456789012345678"
  # User snowflake ID authorized to answer prompts in threads (Optional)
  notify_user_id: "123456789012345678"
```

*(Note: Discord snowflake IDs can be provided as quoted numeric strings).*

---

## 9. Verification Commands

Ticket Runner provides two verification tools to validate your Discord configuration:

### 1. Doctor Pre-Flight Verification (`ticket_runner doctor --live`)
Runs pre-flight checks including an active Discord gateway ping and permission validation:
```bash
py ticket_runner.py doctor --live
```
- **Exit Code 0:** All pre-flight checks passed, including token authentication and verification of all 7 permissions in the configured channel.
- **Exit Code 1:** Failure. If permissions are missing, Doctor prints the exact missing permission names (e.g. `missing required permission(s): Create Public Threads`) along with remediation instructions.

### 2. Standalone Smoke Test (`ticket_runner bot --smoke`)
Executes an end-to-end self-cleaning verification sequence against your Discord channel:
```bash
py ticket_runner.py bot --smoke
```
- **What it does:**
  1. Authenticates with Discord.
  2. Verifies the 7 required channel permissions.
  3. Creates a temporary thread named `_smoke-test-verify`.
  4. Posts a verification message in the thread.
  5. Edits the verification message to `verified`.
  6. Archives and locks the thread.
  7. Deletes the starter announcement message from the parent channel.
- **Exit Code 0:** All operations succeeded. The channel is left completely clean with no lingering messages.
- **Exit Code 1:** Authentication error, network timeout, channel not found, or missing permissions. Specific errors are printed to stderr.

### Optional: Standalone Bot Run (`ticket_runner bot --run`)
To test slash commands (`/status`, `/pause`, `/mode`) and thread reply listening interactively without starting the ticket queue:
```bash
py ticket_runner.py bot --run
```
Press `Ctrl+C` to cleanly disconnect and stop the bot (exits with code 130).
