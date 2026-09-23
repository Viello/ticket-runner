"""Unit tests for DiscordLogger port, chunking engine, and severity routing (T082)."""

from __future__ import annotations

import pytest

from runner.adapters.discord.logger import (
    COLOR_RED,
    COLOR_YELLOW,
    DiscordLoggerImpl,
    chunk_payload,
    format_chunks,
    split_chunks,
)
from runner.ports.discord_logger import DiscordLogger
from tests.fakes.fake_discord_gateway import FakeDiscordGateway
from tests.fakes.fake_discord_logger import DiscordLogCall, FakeDiscordLogger


def test_discord_logger_protocol_conformance() -> None:
    """Both FakeDiscordLogger and DiscordLoggerImpl conform to DiscordLogger protocol."""
    fake_gateway = FakeDiscordGateway()
    impl = DiscordLoggerImpl(fake_gateway)
    fake_logger = FakeDiscordLogger()

    assert isinstance(impl, DiscordLogger)
    assert isinstance(fake_logger, DiscordLogger)


# ---------------------------------------------------------------------------
# Chunking Unit Tests
# ---------------------------------------------------------------------------


def test_chunking_exact_1950_chars() -> None:
    """1,950-character payload produces exactly 1 chunk."""
    payload = "A" * 1950
    chunks = chunk_payload(payload)
    assert len(chunks) == 1
    assert chunks[0] == payload


def test_chunking_1951_chars_hard_split() -> None:
    """1,951-character payload without newlines produces exactly 2 chunks."""
    payload = "B" * 1951
    chunks = chunk_payload(payload)
    assert len(chunks) == 2
    assert chunks[0] == "B" * 1950
    assert chunks[1] == "[continued 2/2]\nB"


def test_chunking_3900_chars_hard_split() -> None:
    """3,900-character payload without newlines produces exactly 2 chunks."""
    payload = "C" * 3900
    chunks = chunk_payload(payload)
    assert len(chunks) == 2
    assert chunks[0] == "C" * 1950
    assert chunks[1] == f"[continued 2/2]\n{'C' * 1950}"


def test_chunking_3901_chars_hard_split() -> None:
    """3,901-character payload without newlines produces exactly 3 chunks."""
    payload = "D" * 3901
    chunks = chunk_payload(payload)
    assert len(chunks) == 3
    assert chunks[0] == "D" * 1950
    assert chunks[1] == f"[continued 2/3]\n{'D' * 1950}"
    assert chunks[2] == "[continued 3/3]\nD"


def test_chunking_splits_on_newline_before_1950() -> None:
    """Payload splits on last newline at or before 1,950; no characters lost."""
    part1 = "Line one\n" * 100  # 900 chars
    part2 = "Middle text\n" * 80  # 960 chars -> total 1860 chars
    part3 = "Final line\n" + "Z" * 300  # newline at 1871
    full_payload = part1 + part2 + part3  # > 2100 chars

    raw_chunks = split_chunks(full_payload)
    assert len(raw_chunks) == 2
    # Combined raw chunks must equal the original payload
    assert "".join(raw_chunks) == full_payload
    # Chunk 1 must end with newline
    assert raw_chunks[0].endswith("\n")
    assert len(raw_chunks[0]) <= 1950


# ---------------------------------------------------------------------------
# Embed Limits and Chunking Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_embed_title_and_field_limits() -> None:
    """Embed title is truncated to 256 chars, field name to 256, field value to 1024."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    embed = {
        "title": "T" * 300,
        "description": "Short description",
        "fields": [
            {"name": "N" * 300, "value": "V" * 1200, "inline": True},
        ],
    }
    await logger.post_embed("thread_1", embed)

    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    sent_embed = call.kwargs["embed"]
    assert len(sent_embed["title"]) == 256
    assert len(sent_embed["fields"][0]["name"]) == 256
    assert len(sent_embed["fields"][0]["value"]) == 1024


@pytest.mark.anyio
async def test_embed_description_chunking() -> None:
    """Embed description exceeding 1,950 chars is chunked across multiple messages."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    desc = "E" * 2100
    embed = {
        "title": "Main Title",
        "description": desc,
        "color": COLOR_RED,
    }
    msg_ids = await logger.post_embed("thread_1", embed)

    assert len(msg_ids) == 2
    assert len(gateway.calls) == 2

    first_embed = gateway.calls[0].kwargs["embed"]
    assert first_embed["title"] == "Main Title"
    assert first_embed["description"] == "E" * 1950
    assert first_embed["color"] == COLOR_RED

    second_embed = gateway.calls[1].kwargs["embed"]
    assert second_embed["description"] == f"[continued 2/2]\n{'E' * 150}"
    assert second_embed["color"] == COLOR_RED


# ---------------------------------------------------------------------------
# Severity Routing & Presence Mode Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_critical_events_always_posted() -> None:
    """Critical events post in both nearby and away mode as colored embeds."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    # In nearby mode: critical event posts
    res = await logger.log("circuit_breaker_trip", "Attempt 3/3 failed", "thread_1", "nearby")
    assert len(res) == 1
    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call.kwargs["embed"]["color"] == COLOR_RED
    assert "Attempt 3/3 failed" in call.kwargs["embed"]["description"]

    # In away mode: verification failure posts
    res2 = await logger.log("verification_failed", "Test failed", "thread_1", "away")
    assert len(res2) == 1
    assert len(gateway.calls) == 2


@pytest.mark.anyio
async def test_handoff_and_question_signal_yellow_embed() -> None:
    """Handoff and question signals use yellow embeds."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway, notify_user_id="user_123")

    # Handoff -> yellow embed
    await logger.log("handoff_triggered", "135k tokens reached", "thread_1", "nearby")
    assert gateway.calls[-1].kwargs["embed"]["color"] == COLOR_YELLOW

    # Question signal with notify_user_id -> mention message then yellow embed
    gateway.calls.clear()
    await logger.log("question_signal", "Need approval", "thread_1", "nearby")
    assert len(gateway.calls) == 2
    assert gateway.calls[0].args[1] == "<@user_123>"
    assert gateway.calls[1].kwargs["embed"]["color"] == COLOR_YELLOW


@pytest.mark.anyio
async def test_routine_events_mode_gating() -> None:
    """Routine events are suppressed in nearby mode and posted with emoji prefix in away mode."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    # Nearby mode -> suppressed
    res = await logger.log("phase_transition", "Running → Reviewing", "thread_1", "nearby")
    assert res == []
    assert len(gateway.calls) == 0

    # Away mode -> posted with emoji prefix
    res2 = await logger.log("phase_transition", "Running → Reviewing", "thread_1", "away")
    assert len(res2) == 1
    assert len(gateway.calls) == 1
    assert gateway.calls[0].args[1].startswith("🔄 ")


@pytest.mark.anyio
async def test_routine_events_all_emojis() -> None:
    """All routine event types map to their expected emoji prefix."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    test_cases = [
        ("milestone_notice", "Signal emitted", "✅"),
        ("token_warning", "Approaching 120k", "⚠️"),
        ("security_review", "Scanning dependencies", "🔒"),
        ("queue_state_change", "Ticket dequeued", "📋"),
        ("ticket_committed", "Commit authored", "✅"),
        ("runner_startup", "Starting runner", "🚀"),
    ]

    for event_type, msg, expected_emoji in test_cases:
        gateway.calls.clear()
        res = await logger.log(event_type, msg, "thread_1", "away")
        assert len(res) == 1
        assert gateway.calls[0].args[1].startswith(f"{expected_emoji} ")


@pytest.mark.anyio
async def test_live_digest_critical_plain_text_always_posts() -> None:
    """Live digest is critical plain-text and always posts in nearby mode."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    res = await logger.log("live_digest", "Thinking about step 1...", "thread_1", "nearby")
    assert len(res) == 1
    assert len(gateway.calls) == 1
    assert gateway.calls[0].args[1] == "Thinking about step 1..."
    assert gateway.calls[0].kwargs.get("embed") is None


@pytest.mark.anyio
async def test_question_signal_without_notify_user_id() -> None:
    """Question signal without notify_user_id posts only the yellow embed."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway, notify_user_id=None)

    res = await logger.log("question_signal", "Clarify requirement?", "thread_1", "nearby")
    assert len(res) == 1
    assert len(gateway.calls) == 1
    assert gateway.calls[0].kwargs["embed"]["color"] == COLOR_YELLOW


@pytest.mark.anyio
async def test_explicit_severity_override() -> None:
    """Explicit severity override takes precedence over event_type default."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    # Unknown event marked critical -> posts in nearby mode
    res = await logger.log("custom_alert", "Custom payload", "thread_1", "nearby", severity="critical")
    assert len(res) == 1
    assert len(gateway.calls) == 1

    # Critical-named event forced to routine -> suppressed in nearby mode
    gateway.calls.clear()
    res2 = await logger.log(
        "circuit_breaker_trip", "Attempt failed", "thread_1", "nearby", severity="routine"
    )
    assert res2 == []
    assert len(gateway.calls) == 0


# ---------------------------------------------------------------------------
# FakeDiscordLogger Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fake_discord_logger_records_suppression_decisions() -> None:
    """FakeDiscordLogger records suppression decisions and bypasses chunking."""
    fake_logger = FakeDiscordLogger()

    # Routine in nearby -> suppressed recorded
    res1 = await fake_logger.log("phase_transition", "A" * 3000, "thread_1", "nearby")
    assert res1 == []
    assert len(fake_logger.calls) == 1
    call1 = fake_logger.calls[0]
    assert call1.suppressed is True
    assert call1.severity == "routine"

    # Routine in away -> not suppressed, chunking bypassed
    res2 = await fake_logger.log("phase_transition", "A" * 3000, "thread_1", "away")
    assert len(res2) == 1
    assert len(fake_logger.calls) == 2
    call2 = fake_logger.calls[1]
    assert call2.suppressed is False
    assert call2.payload == "A" * 3000

    # Helper properties
    assert len(fake_logger.suppressed_calls) == 1
    assert len(fake_logger.dispatched_calls) == 1
    assert fake_logger.last_call == call2

    # Post embed in fake logger
    embed_res = await fake_logger.post_embed("thread_1", {"title": "Test", "description": "Desc"})
    assert len(embed_res) == 1
    assert len(fake_logger.embed_calls) == 1
    assert fake_logger.embed_calls[0][1]["title"] == "Test"

    # Clear
    fake_logger.clear()
    assert len(fake_logger.calls) == 0
    assert len(fake_logger.embed_calls) == 0
    assert fake_logger.last_call is None


# ---------------------------------------------------------------------------
# Verbatim Smoke Scenarios from T082
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_smoke_scenario_chunking_splits_on_newline() -> None:
    """Smoke: Chunking splits on newline."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    # Build a string of 2,100 chars containing a \n at position 1,940
    # In 0-indexed string, index 1940 is the 1941st char, so payload[:1940] + "\n" + payload[1941:]
    prefix = "A" * 1940
    suffix = "B" * (2100 - 1941)
    payload = prefix + "\n" + suffix
    assert len(payload) == 2100
    assert payload[1940] == "\n"

    await logger.log("routine", payload, thread_id="T", presence_mode="away")

    assert len(gateway.calls) == 2
    chunk1_content = gateway.calls[0].args[1]
    chunk2_content = gateway.calls[1].args[1]

    assert chunk2_content.startswith("[continued 2/2]\n")
    chunk2_body = chunk2_content.removeprefix("[continued 2/2]\n")
    assert chunk1_content + chunk2_body == payload


@pytest.mark.anyio
async def test_smoke_scenario_no_newline_hard_split() -> None:
    """Smoke: No-newline hard split."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    payload = "X" * 2100
    await logger.log("routine", payload, thread_id="T", presence_mode="away")

    assert len(gateway.calls) == 2
    assert gateway.calls[0].args[1] == "X" * 1950
    assert gateway.calls[1].args[1] == f"[continued 2/2]\n{'X' * 150}"


@pytest.mark.anyio
async def test_smoke_scenario_critical_event_always_posts_in_nearby_mode() -> None:
    """Smoke: Critical event always posts in nearby mode."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    await logger.log("circuit_breaker_trip", "Attempt 3/3 failed", thread_id="T", presence_mode="nearby")

    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    embed = call.kwargs["embed"]
    assert embed is not None
    assert embed.get("color") == 0xFF0000 or embed.get("colour") == 0xFF0000


@pytest.mark.anyio
async def test_smoke_scenario_routine_event_suppressed_in_nearby_mode() -> None:
    """Smoke: Routine event suppressed in nearby mode."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    await logger.log("phase_transition", "Running → Reviewing", thread_id="T", presence_mode="nearby")

    assert len(gateway.calls) == 0


@pytest.mark.anyio
async def test_smoke_scenario_routine_event_posts_in_away_mode() -> None:
    """Smoke: Routine event posts in away mode."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)

    await logger.log("phase_transition", "Running → Reviewing", thread_id="T", presence_mode="away")

    assert len(gateway.calls) == 1
    call = gateway.calls[0]
    assert call.args[1].startswith("🔄")
