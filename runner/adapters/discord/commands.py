"""Slash command definitions (/status, /pause, /mode) for Discord bot (T074, Spec 05a)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any
import discord
from discord import app_commands

from runner.domain.state import VALID_PRESENCE_MODES
from runner.ports.state_store import StateStore

if TYPE_CHECKING:
    from runner.application.presence_coordinator import PresenceCoordinator
    from runner.application.state_coordinator import StateCoordinator

OFFLINE_NOTICE = "Runner is offline (standalone bot mode). Command is unavailable."
PAUSE_CONFIRMATION = "Runner paused. Current ticket will complete verification before stopping."


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


async def handle_pause(
    interaction: discord.Interaction,
    state_coordinator: StateCoordinator | None = None,
) -> None:
    """Handler logic for /pause slash command."""
    if state_coordinator is None:
        await interaction.response.send_message(OFFLINE_NOTICE)
        return

    if hasattr(state_coordinator, "request_pause") and callable(state_coordinator.request_pause):
        state_coordinator.request_pause()
    elif hasattr(state_coordinator, "transition_to_pause_requested") and callable(
        state_coordinator.transition_to_pause_requested
    ):
        state_coordinator.transition_to_pause_requested()

    await interaction.response.send_message(PAUSE_CONFIRMATION)


async def handle_mode(
    interaction: discord.Interaction,
    mode: str | app_commands.Choice[str] = "nearby",
    presence_coordinator: PresenceCoordinator | None = None,
) -> None:
    """Handler logic for /mode slash command."""
    if presence_coordinator is None:
        await interaction.response.send_message(OFFLINE_NOTICE)
        return

    mode_val = mode.value if isinstance(mode, app_commands.Choice) else str(mode)
    if mode_val not in VALID_PRESENCE_MODES:
        valid_options = ", ".join(f"`{m}`" for m in VALID_PRESENCE_MODES)
        await interaction.response.send_message(
            f"Invalid presence mode '{mode_val}'. Valid options are: {valid_options}.",
            ephemeral=True,
        )
        return

    presence_coordinator.set_mode(mode_val)
    await interaction.response.send_message(f"Presence mode set to {mode_val}.")


def register_commands(
    tree: app_commands.CommandTree,
    state_store: StateStore | None = None,
    presence_coordinator: PresenceCoordinator | None = None,
    state_coordinator: StateCoordinator | None = None,
) -> tuple[app_commands.Command, app_commands.Command, app_commands.Command]:
    """Register /status, /pause, and /mode command handlers on the CommandTree."""
    if state_store is None and state_coordinator is not None and hasattr(state_coordinator, "state_store"):
        state_store = state_coordinator.state_store

    @tree.command(name="status", description="Show the current Ticket Runner status.")
    async def status_cmd(interaction: discord.Interaction) -> None:
        await handle_status(interaction, state_store)

    @tree.command(
        name="pause",
        description="Pause runner execution (offline notice in standalone mode).",
    )
    async def pause_cmd(interaction: discord.Interaction) -> None:
        await handle_pause(interaction, state_coordinator)

    @tree.command(
        name="mode",
        description="Switch presence mode (offline notice in standalone mode).",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name=m, value=m)
            for m in VALID_PRESENCE_MODES
        ]
    )
    async def mode_cmd(
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
    ) -> None:
        await handle_mode(interaction, mode=mode, presence_coordinator=presence_coordinator)

    return status_cmd, pause_cmd, mode_cmd


__all__ = [
    "OFFLINE_NOTICE",
    "PAUSE_CONFIRMATION",
    "format_status_response",
    "handle_status",
    "handle_pause",
    "handle_mode",
    "register_commands",
]
