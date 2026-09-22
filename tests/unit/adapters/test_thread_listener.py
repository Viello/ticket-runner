"""Unit tests for Discord thread reply listener (T074, Spec 05a)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from datetime import datetime, timezone

from runner.adapters.discord.thread_listener import (
    is_thread_channel,
    process_thread_reply,
)
from runner.domain.config import DiscordConfig
from runner.domain.exceptions import SignalFormatError
from runner.domain.signal import QuestionSignal, QuestionType, SignalStatus
from tests.fakes.fake_signal_repository import FakeSignalRepository


def _make_pending_question(ticket_id: str) -> QuestionSignal:
    return QuestionSignal(
        ticket_id=ticket_id,
        question="Clarification needed?",
        type=QuestionType.TEXT,
        options=None,
        status=SignalStatus.PENDING,
        answer=None,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def base_discord_config() -> DiscordConfig:
    """Fixture providing DiscordConfig with configured channel and user."""
    return DiscordConfig(
        channel_id="1234567890",
        guild_id="9876543210",
        notify_user_id="5555555555",
    )


@pytest.fixture
def mock_thread() -> MagicMock:
    """Fixture providing a mock discord.Thread channel."""
    thread = MagicMock(spec=discord.Thread)
    thread.parent_id = 1234567890
    thread.parent = MagicMock()
    thread.parent.id = 1234567890
    thread.name = "T042-test-ticket-slug"
    thread.send = AsyncMock()
    return thread


@pytest.fixture
def mock_message(mock_thread: MagicMock) -> MagicMock:
    """Fixture providing a mock discord.Message inside a thread."""
    message = MagicMock(spec=discord.Message)
    message.channel = mock_thread
    message.author = MagicMock()
    message.author.bot = False
    message.author.id = 5555555555
    message.content = "This is the answer from developer."
    message.reply = AsyncMock()
    return message


def test_is_thread_channel_detection() -> None:
    """is_thread_channel correctly distinguishes threads from text channels."""
    thread_mock = MagicMock(spec=discord.Thread)
    assert is_thread_channel(thread_mock) is True

    text_mock = MagicMock(spec=discord.TextChannel)
    text_mock.type = discord.ChannelType.text
    text_mock.parent_id = None
    assert is_thread_channel(text_mock) is False


@pytest.mark.anyio
async def test_process_thread_reply_skips_bot_authors(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """process_thread_reply skips messages sent by bot accounts."""
    mock_message.author.bot = True
    sig_repo = FakeSignalRepository()

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is False
    assert len(sig_repo.write_answer_calls) == 0
    mock_message.reply.assert_not_awaited()


@pytest.mark.anyio
async def test_process_thread_reply_skips_non_thread_channels(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """process_thread_reply skips messages in non-thread channels."""
    non_thread = MagicMock(spec=discord.TextChannel)
    non_thread.type = discord.ChannelType.text
    non_thread.parent_id = None
    mock_message.channel = non_thread
    sig_repo = FakeSignalRepository()

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is False
    assert len(sig_repo.write_answer_calls) == 0
    mock_message.reply.assert_not_awaited()


@pytest.mark.anyio
async def test_process_thread_reply_skips_wrong_parent_channel(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """process_thread_reply skips messages whose thread parent ID differs from config."""
    mock_message.channel.parent_id = 9999999999
    mock_message.channel.parent.id = 9999999999
    sig_repo = FakeSignalRepository()

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is False
    assert len(sig_repo.write_answer_calls) == 0
    mock_message.reply.assert_not_awaited()


@pytest.mark.anyio
async def test_process_thread_reply_skips_unauthorized_user(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """process_thread_reply skips messages when author ID != notify_user_id."""
    mock_message.author.id = 1111111111  # different from config's 5555555555
    sig_repo = FakeSignalRepository()

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is False
    assert len(sig_repo.write_answer_calls) == 0
    mock_message.reply.assert_not_awaited()


@pytest.mark.anyio
async def test_process_thread_reply_accepts_any_user_when_notify_user_id_empty(
    mock_message: MagicMock,
) -> None:
    """When notify_user_id is empty, any user's reply is processed."""
    config = DiscordConfig(channel_id="1234567890", notify_user_id="")
    mock_message.author.id = 9988776655
    sig_repo = FakeSignalRepository()
    sig_repo.seed_question(_make_pending_question("T042"))

    result = await process_thread_reply(mock_message, sig_repo, config)

    assert result is True
    assert sig_repo.write_answer_calls == [("T042", "This is the answer from developer.")]
    mock_message.reply.assert_awaited_once()
    assert "T042" in mock_message.reply.await_args.args[0]


@pytest.mark.anyio
async def test_process_thread_reply_skips_invalid_ticket_id_in_thread_name(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """process_thread_reply skips threads whose name does not start with ^([A-Z]\\d{3,})."""
    mock_message.channel.name = "_smoke-test-verify"
    sig_repo = FakeSignalRepository()

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is False
    assert len(sig_repo.write_answer_calls) == 0


@pytest.mark.anyio
async def test_process_thread_reply_successful_write(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """Valid reply calls write_answer with parsed ticket_id and posts confirmation."""
    mock_message.channel.name = "T074-slash-commands-and-thread-listener"
    mock_message.content = "Approved, continue with next ticket."
    sig_repo = FakeSignalRepository()
    sig_repo.seed_question(_make_pending_question("T074"))

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is True
    assert sig_repo.write_answer_calls == [("T074", "Approved, continue with next ticket.")]
    mock_message.reply.assert_awaited_once()
    assert "T074" in mock_message.reply.await_args.args[0]


@pytest.mark.anyio
async def test_process_thread_reply_handles_write_error_gracefully(
    mock_message: MagicMock,
    base_discord_config: DiscordConfig,
) -> None:
    """When write_answer raises an exception, an error reply is posted in the thread."""
    sig_repo = FakeSignalRepository()
    sig_repo.write_answer = MagicMock(side_effect=SignalFormatError("No question file"))

    result = await process_thread_reply(mock_message, sig_repo, base_discord_config)

    assert result is False
    mock_message.reply.assert_awaited_once()
    assert "Failed" in mock_message.reply.await_args.args[0]
    assert "T042" in mock_message.reply.await_args.args[0]
