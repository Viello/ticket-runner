"""Unit tests for Status Card, Live Digest, and Token Bar formatting (T083)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from runner.adapters.discord.logger import (
    COLOR_BLURPLE,
    BREADCRUMB_TRAIL,
    DiscordLoggerImpl,
    build_status_card_description,
    build_status_card_embed,
    build_token_bar,
    format_token_bar,
)
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.discord_logger import DiscordLogger
from tests.fakes.fake_discord_gateway import FakeDiscordGateway
from tests.fakes.fake_discord_logger import FakeDiscordLogger


# ---------------------------------------------------------------------------
# Token Bar Pure Function Tests
# ---------------------------------------------------------------------------


def test_build_token_bar_pure_function() -> None:
    """Token bar pure function verified for 0k, 80k, 120k, 135k, 150k."""
    # 0k -> all ░
    assert build_token_bar(0) == "░░░░░░░░░░"
    assert len(build_token_bar(0)) == 10

    # 80k -> 6 blocks
    assert build_token_bar(80_000) == "██████░░░░"
    assert len(build_token_bar(80_000)) == 10

    # 120k -> 9th block filled (warning threshold)
    assert build_token_bar(120_000) == "█████████░"
    assert len(build_token_bar(120_000)) == 10

    # 135k -> 10th block filled (handoff threshold)
    assert build_token_bar(135_000) == "██████████"
    assert len(build_token_bar(135_000)) == 10

    # 150k -> all █ (ceiling)
    assert build_token_bar(150_000) == "██████████"
    assert len(build_token_bar(150_000)) == 10


def test_build_token_bar_clamping() -> None:
    """Negative values clamp to 0; over-ceiling values clamp to 10."""
    assert build_token_bar(-500) == "░░░░░░░░░░"
    assert build_token_bar(200_000) == "██████████"


def test_format_token_bar_layout() -> None:
    """format_token_bar matches ~{round(current/1000)}k / 150k  {bar} {pct}%."""
    # 0k
    assert format_token_bar(0) == "~0k / 150k  ░░░░░░░░░░ 0%"

    # 80k
    assert format_token_bar(80_000) == "~80k / 150k  ██████░░░░ 53%"

    # 118.2k (verbatim spec example)
    assert format_token_bar(118_200) == "~118k / 150k  ████████░░ 79%"

    # 120k
    assert format_token_bar(120_000) == "~120k / 150k  █████████░ 80%"

    # 135k
    assert format_token_bar(135_000) == "~135k / 150k  ██████████ 90%"

    # 150k
    assert format_token_bar(150_000) == "~150k / 150k  ██████████ 100%"


# ---------------------------------------------------------------------------
# Status Card Description and Embed Tests
# ---------------------------------------------------------------------------


def test_build_status_card_description_column_14_alignment() -> None:
    """Field label column is right-padded with spaces so colons align at column 14."""
    desc = build_status_card_description(
        ticket_id="T042",
        slug="defer-clean-slate-prompt-until-exit",
        spec="05-presence-mode-and-discord",
        status="🟡 Verifying",
        attempt="2 / 3",
        tokens_current=118_200,
        started_at="13:04 UTC",
        last_updated="13:11 UTC",
    )

    # Monospace code block wrapper
    assert desc.startswith("```\n")
    assert desc.endswith("\n```")

    inner_lines = desc.strip("`").strip("\n").splitlines()
    assert len(inner_lines) == 7

    labels = [
        "Ticket:       ",
        "Spec:         ",
        "Status:       ",
        "Attempt:      ",
        "Tokens:       ",
        "Started:      ",
        "Last updated: ",
    ]

    for line, label in zip(inner_lines, labels):
        assert line.startswith(label), f"Line {line!r} does not start with {label!r}"
        assert len(label) == 14

    # Breadcrumb trail check
    assert "🟡 Verifying   (Running → Reviewing → Verifying → ✅ Committed)" in inner_lines[2]
    # Tokens line check
    assert "~118k / 150k  ████████░░ 79%" in inner_lines[4]
    # Timestamps
    assert inner_lines[5] == "Started:      13:04 UTC"
    assert inner_lines[6] == "Last updated: 13:11 UTC"


def test_build_status_card_embed_properties() -> None:
    """Status card embed has blurple color (0x5865F2) and monospace description."""
    embed = build_status_card_embed(
        ticket_id="T042",
        slug="defer-clean-slate",
        spec="05-presence-mode-and-discord",
        status="Running",
        attempt=1,
        tokens_current=0,
        started_at="10:00 UTC",
    )
    assert embed["color"] == COLOR_BLURPLE
    assert embed["color"] == 0x5865F2
    assert "T042 · defer-clean-slate" in embed["description"]
    assert BREADCRUMB_TRAIL in embed["description"]


# ---------------------------------------------------------------------------
# DiscordLoggerImpl Status Card Tests (Smoke Scenarios 1 & 2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_post_status_card_posts_and_pins() -> None:
    """Smoke Scenario 1: Status Card posted and pinned on ticket start."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    ticket = Ticket(
        id="T042",
        title="defer-clean-slate",
        slug="defer-clean-slate",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/05-presence-mode-and-discord.md",
        requirements=(),
        acceptance_criteria=(),
        gotchas=(),
        path=Path("docs/tickets/05-presence-mode-and-discord/T042-defer-clean-slate.md"),
    )

    msg_id = await logger.post_status_card(ticket, thread_id="999")

    # One post_message call with embed containing T042 · defer-clean-slate
    post_calls = [c for c in gateway.calls if c.method == "post_message"]
    assert len(post_calls) == 1
    call = post_calls[0]
    assert call.channel_or_thread_id == "999"
    embed = call.embed
    assert embed is not None
    assert "T042 · defer-clean-slate" in embed["description"]
    assert embed["color"] == 0x5865F2

    # One pin_message call with the returned message ID
    pin_calls = [c for c in gateway.calls if c.method == "pin_message"]
    assert len(pin_calls) == 1
    assert pin_calls[0].channel_or_thread_id == "999"
    assert pin_calls[0].message_id == msg_id


@pytest.mark.anyio
async def test_update_status_card_in_place() -> None:
    """Smoke Scenario 2: Status Card edited in-place on phase change."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    status_card_message_id = "111"

    await logger.update_status_card(
        "999",
        status_card_message_id,
        status="🟡 Reviewing",
        attempt=2,
        tokens_current=80000,
        started_at="13:04 UTC",
    )

    # Exactly 1 edit_message call (no new post_message)
    post_calls = [c for c in gateway.calls if c.method == "post_message"]
    assert len(post_calls) == 0

    edit_calls = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(edit_calls) == 1
    edit_call = edit_calls[0]
    assert edit_call.channel_or_thread_id == "999"
    assert edit_call.message_id == "111"

    embed = edit_call.embed
    assert embed is not None
    assert "🟡 Reviewing" in embed["description"]
    assert f"({BREADCRUMB_TRAIL})" in embed["description"]
    assert "Attempt:      2 / 3" in embed["description"]
    assert "~80k / 150k" in embed["description"]
    assert "Started:      13:04 UTC" in embed["description"]
    assert "Last updated: " in embed["description"]
    assert embed["color"] == 0x5865F2


# ---------------------------------------------------------------------------
# Live Digest Tests (Smoke Scenarios 3 & 4)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_live_digest_rolling_500_char_window() -> None:
    """Live digest window retains last 500 characters, not tokens."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    logger.live_digest_rate_limit_floor = 0.0  # bypass rate limit for window test

    await logger.start_live_digest("thread_10")

    # Send 600 characters
    chunk = "A" * 300 + "B" * 300
    await logger.update_live_digest(chunk)

    edit_calls = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(edit_calls) >= 1
    last_content = edit_calls[-1].content
    assert len(last_content) == 500
    assert last_content == chunk[-500:]


@pytest.mark.anyio
async def test_live_digest_rate_limit_floor() -> None:
    """Smoke Scenario 3: Live Digest rate-limit floor.
    
    Submit 20 updates rapidly; at most 1 edit_message fired during burst;
    final edit fires after floor.
    """
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    logger.live_digest_rate_limit_floor = 0.1  # 100ms floor

    await logger.start_live_digest("thread_999")

    # 20 updates in rapid succession (< 50ms)
    for i in range(20):
        await logger.update_live_digest(f"chunk_{i}\n")

    burst_edits = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(burst_edits) <= 1, f"Expected <= 1 edit during burst, got {len(burst_edits)}"

    # Wait 200ms (> 100ms floor) for scheduled delayed flush
    await asyncio.sleep(0.2)

    total_edits = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(total_edits) == 2, f"Expected 2 edits total (1 burst + 1 delayed), got {len(total_edits)}"
    assert "chunk_19" in total_edits[-1].content


@pytest.mark.anyio
async def test_live_digest_finish_done_marker() -> None:
    """Smoke Scenario 4: Live Digest [done] marker on session end."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    await logger.start_live_digest("thread_999")
    await logger.update_live_digest("last chunk")
    await logger.finish_live_digest()

    edit_calls = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(edit_calls) >= 1
    last_edit = edit_calls[-1]
    assert last_edit.content.endswith("\n[done]")
    assert "last chunk\n[done]" in last_edit.content

    # No further edits after finish_live_digest() call
    call_count_before = len(gateway.calls)
    await logger.update_live_digest("should be ignored")
    assert len(gateway.calls) == call_count_before


@pytest.mark.anyio
async def test_live_digest_finish_empty_buffer_appends_done() -> None:
    """finish_live_digest() appends exactly \n[done] even if buffer is empty."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    await logger.start_live_digest("thread_empty")
    await logger.finish_live_digest()

    edit_calls = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(edit_calls) == 1
    assert edit_calls[0].content == "\n[done]"



# ---------------------------------------------------------------------------
# Protocol Conformance Test
# ---------------------------------------------------------------------------


def test_protocol_conformance_with_new_methods() -> None:
    """Both FakeDiscordLogger and DiscordLoggerImpl conform to extended DiscordLogger protocol."""
    gateway = FakeDiscordGateway()
    impl = DiscordLoggerImpl(gateway)
    fake = FakeDiscordLogger()

    assert isinstance(impl, DiscordLogger)
    assert isinstance(fake, DiscordLogger)
