"""Slash command definitions (/status, /pause, /mode) for Discord bot (T074, Spec 05a)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import discord
from discord import app_commands

from runner.ports.state_store import StateStore

OFFLINE_NOTICE = "Runner is offline (standalone bot mode). Command is unavailable."


def _load_state(state_store: StateStore | None) -> dict[str, Any] | None:
    """Read persisted runner state from the store using load() or read()."""
    if state_store is None:
        try:
            from runner.adapters.filesystem.json_state_store import JsonStateStore
            state_store = JsonStateStore()
        except Exception:
            return None

    if hasattr(state_store, "load") and callable(state_store.load):
        return state_store.load()
    if hasattr(state_store, "read") and callable(state_store.read):
        return state_store.read()
    return None


def format_status_response(state: Mapping[str, Any] | None) -> str:
    """Format runner state dictionary into a Discord reply string."""
    if not state:
        return "[Offline / Standalone Bot]\nNo runner state available."

    runner_status = state.get("runner_status")
    if runner_status is None:
        runner_status = state.get("status", "offline")

    is_running = str(runner_status).lower() == "running"

    lines: list[str] = []
    if not is_running:
        lines.append("[Offline / Standalone Bot]")

    lines.append(f"**Runner Status:** {runner_status}")

    # Standard well-known fields first
    standard_keys = {
        "active_ticket_id": "Active Ticket",
        "selected_model": "Selected Model",
        "presence_mode": "Presence Mode",
        "branch": "Branch",
        "verification_attempts": "Verification Attempts",
        "started_at": "Started At",
        "last_checkpoint": "Last Checkpoint",
        "last_updated": "Last Updated",
    }

    for key, label in standard_keys.items():
        if key in state and state[key] is not None:
            lines.append(f"**{label}:** {state[key]}")

    if "tokens" in state and state["tokens"] is not None:
        tok = state["tokens"]
        if isinstance(tok, Mapping) and "current" in tok:
            lines.append(f"**Tokens:** {tok['current']}")
        else:
            lines.append(f"**Tokens:** {tok}")

    # Append any extra fields
    known_fields = set(standard_keys.keys()) | {"runner_status", "status", "tokens"}
    for key, val in state.items():
        if key not in known_fields and val is not None:
            if isinstance(val, Mapping):
                val_str = ", ".join(f"{k}: {v}" for k, v in val.items())
                lines.append(f"**{key}:** {val_str}")
            else:
                lines.append(f"**{key}:** {val}")

    return "\n".join(lines)


async def handle_status(
    interaction: discord.Interaction,
    state_store: StateStore | None = None,
) -> None:
    """Handler logic for /status slash command."""
    state = _load_state(state_store)
    content = format_status_response(state)
    await interaction.response.send_message(content)


async def handle_pause(interaction: discord.Interaction) -> None:
    """Handler logic for /pause slash command."""
    await interaction.response.send_message(OFFLINE_NOTICE)


async def handle_mode(interaction: discord.Interaction) -> None:
    """Handler logic for /mode slash command."""
    await interaction.response.send_message(OFFLINE_NOTICE)


def register_commands(
    tree: app_commands.CommandTree,
    state_store: StateStore | None = None,
) -> tuple[app_commands.Command, app_commands.Command, app_commands.Command]:
    """Register /status, /pause, and /mode command handlers on the CommandTree."""

    @tree.command(name="status", description="Show the current Ticket Runner status.")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await handle_status(interaction, state_store)

    @tree.command(
        name="pause",
        description="Pause runner execution (offline notice in standalone mode).",
    )
    async def pause_cmd(interaction: discord.Interaction) -> None:
        await handle_pause(interaction)

    @tree.command(
        name="mode",
        description="Switch presence mode (offline notice in standalone mode).",
    )
    async def mode_cmd(interaction: discord.Interaction) -> None:
        await handle_mode(interaction)

    return status_cmd, pause_cmd, mode_cmd


__all__ = [
    "OFFLINE_NOTICE",
    "format_status_response",
    "handle_status",
    "handle_pause",
    "handle_mode",
    "register_commands",
]
