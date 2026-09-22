"""Discord smoke verification sequence and permission validation (T075, Spec 05a)."""

from __future__ import annotations

from typing import Any
import discord

from runner.domain.exceptions import DiscordGatewayError
from runner.ports.discord_gateway import DiscordGateway

# The 7 least-privilege Discord permissions required by Ticket Runner
REQUIRED_DISCORD_PERMISSIONS: dict[str, str] = {
    "send_messages": "Send Messages",
    "send_messages_in_threads": "Send Messages in Threads",
    "create_public_threads": "Create Public Threads",
    "manage_threads": "Manage Threads",
    "manage_messages": "Manage Messages",
    "read_message_history": "Read Message History",
    "embed_links": "Embed Links",
}


async def verify_channel_permissions(channel: Any, client: Any) -> list[str]:
    """Verify that the bot holds all 7 required permissions in the target channel.

    Args:
        channel: The discord channel object.
        client: The discord client instance.

    Returns:
        A list of human-readable names of missing permissions (empty if all granted).
    """
    guild = getattr(channel, "guild", None)
    if guild is None:
        return []

    user = getattr(client, "user", None)
    user_id = getattr(user, "id", None) if user else None

    me = getattr(guild, "me", None)
    if me is None and user_id is not None:
        if hasattr(guild, "get_member"):
            me = guild.get_member(user_id)
        if me is None and hasattr(guild, "fetch_member"):
            try:
                me = await guild.fetch_member(user_id)
            except Exception:
                me = None

    if me is None:
        return []

    if not hasattr(channel, "permissions_for"):
        return []

    permissions = channel.permissions_for(me)
    missing: list[str] = []
    for attr, name in REQUIRED_DISCORD_PERMISSIONS.items():
        if not getattr(permissions, attr, False):
            missing.append(name)
    return missing


async def run_smoke(gateway: DiscordGateway, channel_id: str) -> None:
    """Execute the self-cleaning smoke verification sequence.

    Steps:
    1. Create a temporary thread named '_smoke-test-verify' with a starter message.
    2. Post a verification message in the thread.
    3. Edit the verification message to 'verified'.
    4. Archive and lock the thread.
    5. Delete the starter announcement message from the parent channel.

    Args:
        gateway: Conforming DiscordGateway implementation.
        channel_id: Parent channel snowflake ID.

    Raises:
        DiscordGatewayError: If any gateway operation fails.
    """
    thread_id, starter_msg_id = await gateway.create_thread(
        channel_id=channel_id,
        name="_smoke-test-verify",
        starter_message="[Smoke Test] Verification thread created by ticket_runner bot --smoke.",
    )
    verification_msg_id = await gateway.post_message(
        channel_or_thread_id=thread_id,
        content="[Smoke Test] Verifying thread message posting...",
    )
    await gateway.edit_message(
        channel_or_thread_id=thread_id,
        message_id=verification_msg_id,
        content="verified",
    )
    await gateway.archive_thread(thread_id=thread_id)
    await gateway.delete_message(
        channel_or_thread_id=channel_id,
        message_id=starter_msg_id,
    )
