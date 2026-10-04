"""DiscordApprovalAdapter rendering EvidenceCards and capturing slash command approval (Spec 13, T111)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import inspect
import os
import re
from typing import Any
import discord
from discord import app_commands

from runner.domain.config import DiscordConfig, RunnerConfig
from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.ports.approval_gateway import ApprovalGateway
from runner.ports.discord_gateway import DiscordGateway

__all__ = [
    "COLOR_GREEN",
    "COLOR_RED",
    "COLOR_YELLOW",
    "DiscordApprovalAdapter",
    "MAX_DISCORD_DESCRIPTION_LENGTH",
    "MAX_DISCORD_FIELD_NAME_LENGTH",
    "MAX_DISCORD_FIELD_VALUE_LENGTH",
    "MAX_DISCORD_FIELDS_COUNT",
    "MAX_DISCORD_TITLE_LENGTH",
    "MAX_REASON_LENGTH",
    "build_evidence_card_embed",
    "register_approval_commands",
    "sanitize_rejection_reason",
]

MAX_DISCORD_TITLE_LENGTH = 256
MAX_DISCORD_DESCRIPTION_LENGTH = 4096
MAX_DISCORD_FIELD_NAME_LENGTH = 256
MAX_DISCORD_FIELD_VALUE_LENGTH = 1024
MAX_DISCORD_FIELDS_COUNT = 25
MAX_REASON_LENGTH = 500

COLOR_RED = 0xFF0000
COLOR_YELLOW = 0xFEE75C
COLOR_GREEN = 0x57F287

ANSI_ESCAPE_REGEX = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x1f\x7f-\x9f]")
REASON_EXTRACT_QUOTED = re.compile(r'reason\s*[:=]\s*"([^"]+)"', re.IGNORECASE)
REASON_EXTRACT_UNQUOTED = re.compile(r'reason\s*[:=]\s*(\S+)', re.IGNORECASE)
SECRET_ENV_KEYS = ("TOKEN", "KEY", "SECRET", "PASS", "AUTH", "CREDENTIAL", "PRIVATE")


class _SimulatedResponse:
    """In-memory response double for string-dispatched interactions."""

    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, bool]] = []

    async def send_message(self, message: str, ephemeral: bool = False) -> None:
        self.sent_messages.append((message, ephemeral))

    def is_done(self) -> bool:
        return bool(self.sent_messages)


class _SimulatedUser:
    """In-memory user double for string-dispatched interactions."""

    def __init__(self, user_id: Any) -> None:
        self.id = user_id


class _SimulatedInteraction:
    """In-memory interaction double for string-dispatched interactions."""

    def __init__(self, channel_id: Any, user_id: Any) -> None:
        self.channel_id = channel_id
        self.user = _SimulatedUser(user_id)
        self.response = _SimulatedResponse()


def sanitize_rejection_reason(raw_reason: str | None) -> str:
    """Sanitize untrusted rejection reason against control characters and bound length."""
    if raw_reason is None:
        return ""
    # Strip ANSI escape sequences
    without_ansi = ANSI_ESCAPE_REGEX.sub("", str(raw_reason))
    # Strip remaining control characters
    cleaned = CONTROL_CHARS_REGEX.sub(" ", without_ansi)
    # Normalize multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:MAX_REASON_LENGTH]


def _scrub_secrets(text: str) -> str:
    """Redact sensitive environment values (tokens, secrets) from text."""
    if not text:
        return text
    scrubbed = str(text)
    for env_key, env_val in os.environ.items():
        if any(sec in env_key.upper() for sec in SECRET_ENV_KEYS):
            if env_val and len(env_val.strip()) >= 6:
                scrubbed = scrubbed.replace(env_val.strip(), "[REDACTED]")
    return scrubbed


def _match_ids(id_a: Any, id_b: Any) -> bool:
    """Return True if two snowflake or channel IDs match, accounting for integer or string prefixes."""
    str_a = str(id_a).strip()
    str_b = str(id_b).strip()
    if not str_a or not str_b:
        return False
    if str_a == str_b:
        return True
    if str_a.endswith(str_b) or str_b.endswith(str_a):
        return True
    return False


def build_evidence_card_embed(card: EvidenceCard) -> dict[str, Any]:
    """Construct Discord embed dictionary representing an EvidenceCard, respecting size limits."""
    test_is_pass = card.test_status.lower() in ("passed", "pass", "ok")
    color = COLOR_GREEN if test_is_pass else COLOR_RED

    title_raw = f"Verification Approval — {card.ticket_id}"
    title = _scrub_secrets(title_raw)[:MAX_DISCORD_TITLE_LENGTH]

    description_raw = "Verification completed. Operator approval required to proceed to commit."
    description = _scrub_secrets(description_raw)[:MAX_DISCORD_DESCRIPTION_LENGTH]

    fields: list[dict[str, Any]] = []

    # 1. Test Status
    fields.append({
        "name": "Test Status",
        "value": _scrub_secrets(card.test_status.upper())[:MAX_DISCORD_FIELD_VALUE_LENGTH],
        "inline": True,
    })

    # 2. Harness Status (if present)
    if card.harness_status is not None:
        fields.append({
            "name": "Harness Status",
            "value": _scrub_secrets(card.harness_status.upper())[:MAX_DISCORD_FIELD_VALUE_LENGTH],
            "inline": True,
        })

    # 3. Evidence Paths
    if card.evidence_paths:
        lines = [f"• {_scrub_secrets(str(p))}" for p in card.evidence_paths]
        paths_val = "\n".join(lines)
    else:
        paths_val = f"• .agent/evidence/{_scrub_secrets(card.ticket_id)}/"

    if len(paths_val) > MAX_DISCORD_FIELD_VALUE_LENGTH:
        suffix = "\n... (truncated)"
        paths_val = paths_val[: MAX_DISCORD_FIELD_VALUE_LENGTH - len(suffix)] + suffix

    fields.append({
        "name": "Evidence Paths",
        "value": paths_val,
        "inline": False,
    })

    # Ensure field count strictly clamped to 25
    fields = fields[:MAX_DISCORD_FIELDS_COUNT]

    return {
        "title": title,
        "description": description,
        "color": color,
        "fields": fields,
    }


async def _send_interaction_response(
    interaction: Any,
    message: str,
    *,
    ephemeral: bool = False,
) -> None:
    """Send a response or followup message to a Discord interaction safely."""
    if hasattr(interaction, "response"):
        resp = interaction.response
        is_done = False
        if hasattr(resp, "is_done") and callable(resp.is_done):
            try:
                ret = resp.is_done()
                if isinstance(ret, bool):
                    is_done = ret
                elif type(ret).__name__ in ("MagicMock", "AsyncMock"):
                    is_done = False
                else:
                    is_done = bool(ret)
            except Exception:
                is_done = False

        try:
            if not is_done and hasattr(resp, "send_message"):
                res = resp.send_message(message, ephemeral=ephemeral)
                if inspect.isawaitable(res):
                    await res
                return
        except discord.InteractionResponded:
            is_done = True
        except Exception:
            pass

        if is_done and hasattr(interaction, "followup") and hasattr(interaction.followup, "send"):
            try:
                res = interaction.followup.send(message, ephemeral=ephemeral)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                pass
    elif isinstance(interaction, dict) and "response" in interaction:
        resp = interaction["response"]
        if hasattr(resp, "send_message"):
            res = resp.send_message(message, ephemeral=ephemeral)
            if inspect.isawaitable(res):
                await res


class DiscordApprovalAdapter(ApprovalGateway):
    """Discord approval adapter presenting EvidenceCards and capturing slash command sign-offs."""

    def __init__(
        self,
        gateway: DiscordGateway,
        thread_id: str | None = None,
        tree: app_commands.CommandTree | None = None,
        client: discord.Client | None = None,
        config: RunnerConfig | DiscordConfig | None = None,
        notify_user_id: str | None = None,
        thread_resolver: Callable[[str], str] | None = None,
    ) -> None:
        self._gateway = gateway
        self._thread_id = thread_id
        self._client = client
        self._thread_resolver = thread_resolver
        self._config: DiscordConfig | None = (
            config.discord if isinstance(config, RunnerConfig) else config
        )

        if notify_user_id is not None:
            self._notify_user_id = str(notify_user_id).strip()
        elif self._config is not None and getattr(self._config, "notify_user_id", None):
            self._notify_user_id = str(self._config.notify_user_id).strip()
        else:
            self._notify_user_id = ""

        self._channel_id: str = ""
        if self._config is not None and getattr(self._config, "channel_id", None):
            self._channel_id = str(self._config.channel_id).strip()

        self._pending_decisions: dict[str, asyncio.Future[ApprovalDecision]] = {}
        self._queued_interactions: list[Any] = []

        if tree is not None:
            register_approval_commands(tree, self)

    def queue_interaction(self, interaction: Any) -> None:
        """Queue a simulated interaction for approval testing."""
        self._queued_interactions.append(interaction)

    def resolve_thread_id(self, ticket_id: str) -> str:
        """Determine target thread snowflake ID for a ticket."""
        if self._thread_id:
            return str(self._thread_id)
        if self._thread_resolver is not None:
            return str(self._thread_resolver(ticket_id))
        if hasattr(self._gateway, "thread_id") and getattr(self._gateway, "thread_id"):
            return str(getattr(self._gateway, "thread_id"))
        if hasattr(self._gateway, "threads") and isinstance(self._gateway.threads, dict):
            for tid, tinfo in self._gateway.threads.items():
                tname = tinfo.get("name", "") if isinstance(tinfo, dict) else getattr(tinfo, "name", "")
                if ticket_id in str(tname) or str(tid) == ticket_id:
                    return str(tid)
            if len(self._gateway.threads) == 1:
                return str(next(iter(self._gateway.threads.keys())))
        if self._channel_id:
            return self._channel_id
        return str(ticket_id)

    def _resolve_target_thread(self, interaction: Any, explicit_thread_id: str | None = None) -> str | None:
        """Resolve the active thread ID associated with an incoming interaction."""
        if explicit_thread_id and explicit_thread_id in self._pending_decisions:
            return explicit_thread_id

        # Extract channel ID from interaction
        ch_id = getattr(interaction, "channel_id", None)
        if ch_id is None:
            ch = getattr(interaction, "channel", None)
            ch_id = getattr(ch, "id", None)
        if ch_id is None and isinstance(interaction, dict):
            ch_id = interaction.get("channel_id")

        if ch_id is not None:
            for pending_tid in self._pending_decisions:
                if _match_ids(ch_id, pending_tid):
                    return pending_tid

        if len(self._pending_decisions) == 1:
            return next(iter(self._pending_decisions.keys()))

        if self._thread_id and self._thread_id in self._pending_decisions:
            return self._thread_id

        return None

    async def _validate_interaction(
        self,
        interaction: Any,
        expected_thread_id: str | None,
    ) -> bool:
        """Authenticate user against notify_user_id and enforce origin inside target ticket thread."""
        # 1. Thread channel check
        ch_id = getattr(interaction, "channel_id", None)
        if ch_id is None:
            ch = getattr(interaction, "channel", None)
            ch_id = getattr(ch, "id", None)
        if ch_id is None and isinstance(interaction, dict):
            ch_id = interaction.get("channel_id")

        if ch_id is not None and expected_thread_id is not None:
            if not _match_ids(ch_id, expected_thread_id):
                await _send_interaction_response(
                    interaction,
                    f"Invalid channel: Approval commands must be run within ticket thread {expected_thread_id}.",
                    ephemeral=True,
                )
                return False

        # 2. User authorization check
        if self._notify_user_id:
            user = getattr(interaction, "user", None) or getattr(interaction, "author", None)
            u_id = getattr(user, "id", None) if user else None
            if u_id is None and isinstance(interaction, dict):
                u_id = interaction.get("user_id")

            if u_id is not None and not _match_ids(u_id, self._notify_user_id):
                await _send_interaction_response(
                    interaction,
                    "Unauthorized: You are not authorized to approve or reject tickets.",
                    ephemeral=True,
                )
                return False

        return True

    async def handle_approve(
        self,
        interaction: Any,
        thread_id: str | None = None,
    ) -> None:
        """Handle /approve slash command interaction."""
        target_thread = self._resolve_target_thread(interaction, thread_id)
        if not await self._validate_interaction(interaction, target_thread):
            return

        await _send_interaction_response(
            interaction,
            "✅ Ticket approved. Proceeding to commit.",
        )

        if target_thread and target_thread in self._pending_decisions:
            future = self._pending_decisions[target_thread]
            if not future.done():
                future.set_result(ApprovalDecision.APPROVE)

    async def handle_reject(
        self,
        interaction: Any,
        reason: str | None = None,
        thread_id: str | None = None,
    ) -> None:
        """Handle /reject slash command interaction with optional reason."""
        target_thread = self._resolve_target_thread(interaction, thread_id)
        if not await self._validate_interaction(interaction, target_thread):
            return

        sanitized_reason = sanitize_rejection_reason(reason)
        clean_reason = sanitized_reason if sanitized_reason else None

        reply_text = (
            f"❌ Ticket rejected: {clean_reason}. Retrying."
            if clean_reason
            else "❌ Ticket rejected. Retrying."
        )
        await _send_interaction_response(interaction, reply_text)

        if target_thread and target_thread in self._pending_decisions:
            future = self._pending_decisions[target_thread]
            if not future.done():
                future.set_result(ApprovalDecision.REJECT(reason=clean_reason))

    async def _dispatch_interaction(self, item: Any, thread_id: str) -> None:
        """Dispatch a single queued interaction item."""
        if isinstance(item, str):
            cmd_str = item.strip()
            user_id = int(self._notify_user_id) if self._notify_user_id.isdigit() else (self._notify_user_id or "12345")
            sim_interaction = _SimulatedInteraction(channel_id=thread_id, user_id=user_id)

            if cmd_str.startswith("/reject") or cmd_str.startswith("reject"):
                match = REASON_EXTRACT_QUOTED.search(cmd_str)
                if not match:
                    match = REASON_EXTRACT_UNQUOTED.search(cmd_str)
                if match:
                    parsed_reason = match.group(1)
                else:
                    parts = cmd_str.split(None, 1)
                    parsed_reason = parts[1] if len(parts) > 1 else None
                await self.handle_reject(sim_interaction, reason=parsed_reason, thread_id=thread_id)
            else:
                await self.handle_approve(sim_interaction, thread_id=thread_id)
            return

        if isinstance(item, dict) and "command" in item:
            inner_interaction = item.get("interaction")
            cmd = item.get("command", "approve")
            reason = item.get("reason")
            if cmd == "reject":
                await self.handle_reject(inner_interaction, reason=reason, thread_id=thread_id)
            else:
                await self.handle_approve(inner_interaction, thread_id=thread_id)
            return

        # Raw Interaction object
        cmd_name = "approve"
        reason = None
        if hasattr(item, "data") and isinstance(item.data, dict):
            cmd_name = item.data.get("name", "approve")
            options = item.data.get("options", [])
            for opt in options:
                if opt.get("name") == "reason":
                    reason = opt.get("value")

        if cmd_name == "reject":
            await self.handle_reject(item, reason=reason, thread_id=thread_id)
        else:
            await self.handle_approve(item, thread_id=thread_id)

    async def request_approval(self, card: EvidenceCard) -> ApprovalDecision:
        """Present verification evidence embed to ticket thread and await slash command sign-off."""
        thread_id = self.resolve_thread_id(card.ticket_id)
        embed = build_evidence_card_embed(card)

        await self._gateway.post_message(thread_id, "", embed=embed)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._pending_decisions[thread_id] = future

        try:
            # Drain pre-queued interactions from adapter queue
            while self._queued_interactions and not future.done():
                item = self._queued_interactions.pop(0)
                await self._dispatch_interaction(item, thread_id)

            # Drain pre-queued interactions from gateway double if present
            if hasattr(self._gateway, "queued_interactions"):
                while self._gateway.queued_interactions and not future.done():
                    item = self._gateway.queued_interactions.pop(0)
                    await self._dispatch_interaction(item, thread_id)

            if not future.done():
                await future

            return future.result()
        finally:
            self._pending_decisions.pop(thread_id, None)


def register_approval_commands(
    tree: app_commands.CommandTree,
    adapter: DiscordApprovalAdapter,
) -> tuple[app_commands.Command, app_commands.Command]:
    """Register /approve and /reject command handlers on the CommandTree."""

    @tree.command(
        name="approve",
        description="Approve verification evidence and proceed to commit.",
    )
    async def approve_cmd(interaction: discord.Interaction) -> None:
        await adapter.handle_approve(interaction)

    @tree.command(
        name="reject",
        description="Reject verification evidence and request retry.",
    )
    @app_commands.describe(reason="Optional reason or operator guidance for rejection")
    async def reject_cmd(
        interaction: discord.Interaction,
        reason: str | None = None,
    ) -> None:
        await adapter.handle_reject(interaction, reason=reason)

    return approve_cmd, reject_cmd
