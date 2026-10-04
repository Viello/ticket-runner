"""Unit tests for DiscordApprovalAdapter (T111, Spec 13)."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest
import discord
from discord import app_commands

from runner.adapters.discord.approval import (
    MAX_DISCORD_DESCRIPTION_LENGTH,
    MAX_DISCORD_FIELD_NAME_LENGTH,
    MAX_DISCORD_FIELD_VALUE_LENGTH,
    MAX_DISCORD_FIELDS_COUNT,
    MAX_DISCORD_TITLE_LENGTH,
    MAX_REASON_LENGTH,
    DiscordApprovalAdapter,
    build_evidence_card_embed,
    register_approval_commands,
    sanitize_rejection_reason,
)
from runner.domain.config import DiscordConfig, RunnerConfig
from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.ports.approval_gateway import ApprovalGateway
from tests.fakes.fake_discord_gateway import FakeDiscordGateway


@pytest.fixture
def fake_gateway() -> FakeDiscordGateway:
    return FakeDiscordGateway(thread_id="thread-111")


@pytest.fixture
def passing_card() -> EvidenceCard:
    return EvidenceCard(
        ticket_id="T111",
        test_status="passed",
        harness_status="passed",
        evidence_paths=(".agent/evidence/T111/log.txt", ".agent/evidence/T111/trace.png"),
    )


def test_conformance(fake_gateway: FakeDiscordGateway) -> None:
    """DiscordApprovalAdapter satisfies ApprovalGateway protocol."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")
    assert isinstance(adapter, ApprovalGateway)


@pytest.mark.anyio
async def test_embed_contains_required_fields(
    fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard
) -> None:
    """Evidence card embed contains ticket ID, test status, harness status, and evidence paths without smoke scenarios."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")
    adapter.queue_interaction("/approve")

    decision = await adapter.request_approval(passing_card)
    assert decision == ApprovalDecision.APPROVE

    assert len(fake_gateway.calls) == 1
    call = fake_gateway.calls[0]
    assert call.method == "post_message"
    assert call.channel_or_thread_id == "thread-111"
    embed = call.embed
    assert embed is not None

    # Title check
    assert "T111" in embed.get("title", "")
    # Check fields
    fields = embed.get("fields", [])
    field_names = [f["name"] for f in fields]
    field_values = {f["name"]: f["value"] for f in fields}

    assert any("Test" in name for name in field_names)
    assert "PASSED" in str(field_values.get("Test Status", ""))
    assert "PASSED" in str(field_values.get("Harness Status", ""))

    assert "Evidence Paths" in field_values
    assert ".agent/evidence/T111/log.txt" in field_values["Evidence Paths"]

    assert not any("Smoke" in name for name in field_names)
    assert "Smoke Scenarios" not in field_values


@pytest.mark.anyio
async def test_approve_interaction_flow(
    fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard
) -> None:
    """Simulated /approve interaction returns ApprovalDecision.APPROVE."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")
    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.channel_id = 111
    mock_interaction.user = MagicMock()
    mock_interaction.user.id = 12345
    mock_interaction.response = MagicMock()
    mock_interaction.response.send_message = AsyncMock()

    # Queue interaction on fake gateway
    fake_gateway.queue_interaction(mock_interaction)

    decision = await adapter.request_approval(passing_card)
    assert decision == ApprovalDecision.APPROVE
    mock_interaction.response.send_message.assert_awaited_once()


@pytest.mark.anyio
async def test_reject_interaction_with_reason(
    fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard
) -> None:
    """Simulated /reject with reason returns ApprovalDecision.REJECT with reason."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")
    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.channel_id = 111
    mock_interaction.user = MagicMock()
    mock_interaction.user.id = 12345
    mock_interaction.response = MagicMock()
    mock_interaction.response.send_message = AsyncMock()

    # Pre-queue reject interaction with reason
    adapter.queue_interaction({
        "interaction": mock_interaction,
        "command": "reject",
        "reason": "flaky tests",
    })

    decision = await adapter.request_approval(passing_card)
    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "flaky tests"
    mock_interaction.response.send_message.assert_awaited_once()


@pytest.mark.anyio
async def test_reject_string_command_parsing(
    fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard
) -> None:
    """Simulated string command '/reject reason:\"Tests look flaky\"' returns REJECT with parsed reason."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")
    fake_gateway.queue_interaction('/reject reason:"Tests look flaky"')

    decision = await adapter.request_approval(passing_card)
    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "Tests look flaky"


@pytest.mark.anyio
async def test_reason_sanitization_and_length_bounding() -> None:
    """Untrusted reason input is sanitized against control chars and bounded in length."""
    # Control chars (null, escape, backspace, bell) and whitespace
    malicious_reason = "  Error in \x00test\x1b[31m harness\x08 \a "
    sanitized = sanitize_rejection_reason(malicious_reason)
    assert "\x00" not in sanitized
    assert "\x1b" not in sanitized
    assert "\x08" not in sanitized
    assert sanitized == "Error in test harness"

    # Extreme length
    huge_reason = "A" * (MAX_REASON_LENGTH + 200)
    sanitized_huge = sanitize_rejection_reason(huge_reason)
    assert len(sanitized_huge) == MAX_REASON_LENGTH


@pytest.mark.anyio
async def test_unauthorized_user_rejected_ephemerally(
    fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard
) -> None:
    """Interactions from non-matching notify_user_id are rejected with ephemeral error."""
    adapter = DiscordApprovalAdapter(
        fake_gateway, thread_id="thread-111", notify_user_id="12345"
    )

    unauthorized_interaction = MagicMock(spec=discord.Interaction)
    unauthorized_interaction.channel_id = 111
    unauthorized_interaction.user = MagicMock()
    unauthorized_interaction.user.id = 99999  # unauthorized!
    unauthorized_interaction.response = MagicMock()
    unauthorized_interaction.response.send_message = AsyncMock()

    authorized_interaction = MagicMock(spec=discord.Interaction)
    authorized_interaction.channel_id = 111
    authorized_interaction.user = MagicMock()
    authorized_interaction.user.id = 12345  # authorized!
    authorized_interaction.response = MagicMock()
    authorized_interaction.response.send_message = AsyncMock()

    adapter.queue_interaction(unauthorized_interaction)
    adapter.queue_interaction(authorized_interaction)

    decision = await adapter.request_approval(passing_card)
    assert decision == ApprovalDecision.APPROVE

    # Unauthorized interaction received ephemeral error
    unauthorized_interaction.response.send_message.assert_awaited_once()
    kwargs = unauthorized_interaction.response.send_message.await_args.kwargs
    assert kwargs.get("ephemeral") is True
    reply = unauthorized_interaction.response.send_message.await_args.args[0]
    assert "unauthorized" in reply.lower()


@pytest.mark.anyio
async def test_interaction_outside_target_thread_rejected_ephemerally(
    fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard
) -> None:
    """Interactions outside target ticket thread are rejected with ephemeral error."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")

    wrong_channel_interaction = MagicMock(spec=discord.Interaction)
    wrong_channel_interaction.channel_id = 9999  # wrong channel!
    wrong_channel_interaction.user = MagicMock()
    wrong_channel_interaction.user.id = 12345
    wrong_channel_interaction.response = MagicMock()
    wrong_channel_interaction.response.send_message = AsyncMock()

    right_channel_interaction = MagicMock(spec=discord.Interaction)
    right_channel_interaction.channel_id = 111  # matching channel
    right_channel_interaction.user = MagicMock()
    right_channel_interaction.user.id = 12345
    right_channel_interaction.response = MagicMock()
    right_channel_interaction.response.send_message = AsyncMock()

    adapter.queue_interaction(wrong_channel_interaction)
    adapter.queue_interaction(right_channel_interaction)

    decision = await adapter.request_approval(passing_card)
    assert decision == ApprovalDecision.APPROVE

    wrong_channel_interaction.response.send_message.assert_awaited_once()
    kwargs = wrong_channel_interaction.response.send_message.await_args.kwargs
    assert kwargs.get("ephemeral") is True
    reply = wrong_channel_interaction.response.send_message.await_args.args[0]
    assert "channel" in reply.lower() or "thread" in reply.lower()


def test_embed_limits_clamping() -> None:
    """Embed description, field values, and field count enforce Discord limits."""
    huge_paths = tuple(f".agent/evidence/long_path_{i}/" + ("p" * 200) for i in range(30))

    card = EvidenceCard(
        ticket_id="T111",
        test_status="passed",
        harness_status="passed",
        evidence_paths=huge_paths,
    )

    embed = build_evidence_card_embed(card)

    assert len(embed["title"]) <= MAX_DISCORD_TITLE_LENGTH
    if "description" in embed and embed["description"]:
        assert len(embed["description"]) <= MAX_DISCORD_DESCRIPTION_LENGTH

    fields = embed.get("fields", [])
    assert len(fields) <= MAX_DISCORD_FIELDS_COUNT

    for f in fields:
        assert len(f["name"]) <= MAX_DISCORD_FIELD_NAME_LENGTH
        assert len(f["value"]) <= MAX_DISCORD_FIELD_VALUE_LENGTH


def test_secrets_are_redacted_from_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bot token and environment secrets are never leaked into embed fields or descriptions."""
    secret_val = "ghp_VerySecretToken123456789"
    monkeypatch.setenv("DISCORD_BOT_TOKEN", secret_val)

    card = EvidenceCard(
        ticket_id="T111",
        test_status=f"passed with token {secret_val}",
        evidence_paths=(f".agent/evidence/{secret_val}/log.txt",),
    )

    embed = build_evidence_card_embed(card)
    embed_str = str(embed)

    assert secret_val not in embed_str
    assert "[REDACTED]" in embed_str


def test_register_approval_commands_on_command_tree() -> None:
    """register_approval_commands registers /approve and /reject on app_commands.CommandTree."""
    mock_client = MagicMock()
    mock_client._connection._command_tree = None
    tree = app_commands.CommandTree(mock_client)
    fake_gw = FakeDiscordGateway(thread_id="thread-111")
    adapter = DiscordApprovalAdapter(fake_gw, thread_id="thread-111")

    approve_cmd, reject_cmd = register_approval_commands(tree, adapter)
    assert approve_cmd.name == "approve"
    assert reject_cmd.name == "reject"

    registered = {cmd.name for cmd in tree.get_commands()}
    assert {"approve", "reject"}.issubset(registered)

    # Check that reject has optional reason parameter
    assert len(reject_cmd.parameters) == 1
    assert reject_cmd.parameters[0].name == "reason"
    assert reject_cmd.parameters[0].required is False


@pytest.mark.anyio
async def test_async_interaction_arrival(fake_gateway: FakeDiscordGateway, passing_card: EvidenceCard) -> None:
    """Interaction arriving asynchronously while request_approval is awaiting resolves properly."""
    adapter = DiscordApprovalAdapter(fake_gateway, thread_id="thread-111")

    task = asyncio.create_task(adapter.request_approval(passing_card))
    await asyncio.sleep(0.01)

    mock_interaction = MagicMock(spec=discord.Interaction)
    mock_interaction.channel_id = 111
    mock_interaction.user = MagicMock()
    mock_interaction.user.id = 12345
    mock_interaction.response = MagicMock()
    mock_interaction.response.send_message = AsyncMock()

    await adapter.handle_approve(mock_interaction)
    decision = await task

    assert decision == ApprovalDecision.APPROVE
