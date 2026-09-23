"""Unit tests for idle escalation timer and presence auto-reset (T085)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from runner.application.presence_coordinator import PresenceCoordinator
from runner.application.state_coordinator import StateCoordinator
from runner.domain.config import DiscordConfig
from tests.fakes.fake_discord_gateway import FakeDiscordGateway
from tests.fakes.fake_state_store import FakeStateStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(
    initial_mode: str = "nearby",
    state_store: FakeStateStore | None = None,
) -> tuple[PresenceCoordinator, StateCoordinator]:
    """Create a PresenceCoordinator wired to an in-memory StateCoordinator."""
    store = state_store or FakeStateStore()
    sc = StateCoordinator(state_store=store, presence_mode=initial_mode)
    pc = PresenceCoordinator(state_coordinator=sc)
    return pc, sc


def _make_discord_logger(
    gateway: FakeDiscordGateway,
    notify_user_id: str = "123456",
) -> Any:
    """Create a DiscordLoggerImpl backed by a FakeDiscordGateway."""
    from runner.adapters.discord.logger import DiscordLoggerImpl

    return DiscordLoggerImpl(gateway=gateway, notify_user_id=notify_user_id)


async def _immediate_timer_factory(delay_seconds: float, callback: Any) -> asyncio.Task[None]:
    """Timer factory that fires the callback immediately (0-delay) for testing."""

    async def _run() -> None:
        await asyncio.sleep(0)
        await callback()

    return asyncio.create_task(_run())


# ---------------------------------------------------------------------------
# set_mode
# ---------------------------------------------------------------------------


class TestSetMode:
    """PresenceCoordinator.set_mode explicitly assigns a mode."""

    def test_set_mode_changes_to_away(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="nearby")
        pc.set_mode("away")
        assert pc.current_mode == "away"

    def test_set_mode_changes_to_nearby(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="away")
        pc.set_mode("nearby")
        assert pc.current_mode == "nearby"

    def test_set_mode_idempotent(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="nearby")
        pc.set_mode("nearby")
        assert pc.current_mode == "nearby"

    def test_set_mode_persists_via_state_coordinator(self) -> None:
        store = FakeStateStore()
        pc, sc = _make_coordinator(initial_mode="nearby", state_store=store)
        pc.set_mode("away")
        state = sc.get_or_create_state()
        assert state.presence_mode == "away"


# ---------------------------------------------------------------------------
# schedule_escalation — fires after idle timeout
# ---------------------------------------------------------------------------


class TestEscalationFires:
    """Escalation fires after idle timeout: mode → away, mention + embed posted."""

    @pytest.mark.anyio
    async def test_escalation_fires_and_transitions_to_away(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="nearby")
        gateway = FakeDiscordGateway()
        logger = _make_discord_logger(gateway, notify_user_id="99999")

        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_immediate_timer_factory,
        )
        # Allow event loop to process the immediate task
        await asyncio.sleep(0.01)

        assert pc.current_mode == "away"

    @pytest.mark.anyio
    async def test_escalation_posts_mention_then_embed(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="nearby")
        gateway = FakeDiscordGateway()
        logger = _make_discord_logger(gateway, notify_user_id="99999")

        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_immediate_timer_factory,
        )
        await asyncio.sleep(0.01)

        post_calls = [c for c in gateway.calls if c.method == "post_message"]
        assert len(post_calls) >= 2

        # First call: plain-text mention
        mention_call = post_calls[0]
        assert "<@99999>" in mention_call.args[1]
        assert mention_call.args[0] == "thread-99"

        # Second call: yellow embed
        embed_call = post_calls[1]
        assert embed_call.args[0] == "thread-99"
        embed = embed_call.kwargs.get("embed")
        assert embed is not None
        assert embed["color"] == 0xFEE75C
        assert "Worker Question" in embed["title"] or "Question" in embed["title"]


# ---------------------------------------------------------------------------
# cancel_escalation — no Discord posts after cancellation
# ---------------------------------------------------------------------------


class TestEscalationCancelled:
    """Escalation cancelled: presence stays, zero post_message calls."""

    @pytest.mark.anyio
    async def test_cancel_prevents_posts(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="nearby")
        gateway = FakeDiscordGateway()
        logger = _make_discord_logger(gateway, notify_user_id="99999")

        # Use a non-immediate timer so we can cancel before it fires
        async def _slow_timer_factory(
            delay_seconds: float, callback: Any
        ) -> asyncio.Task[None]:
            async def _run() -> None:
                await asyncio.sleep(10)
                await callback()

            return asyncio.create_task(_run())

        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_slow_timer_factory,
        )
        pc.cancel_escalation()
        await asyncio.sleep(0.01)

        assert pc.current_mode == "nearby"
        post_calls = [c for c in gateway.calls if c.method == "post_message"]
        assert len(post_calls) == 0


# ---------------------------------------------------------------------------
# Second schedule_escalation replaces the first
# ---------------------------------------------------------------------------


class TestEscalationReplacement:
    """Second schedule_escalation replaces the first — no stacking."""

    @pytest.mark.anyio
    async def test_second_schedule_replaces_first(self) -> None:
        pc, _sc = _make_coordinator(initial_mode="nearby")
        gateway = FakeDiscordGateway()
        logger = _make_discord_logger(gateway, notify_user_id="99999")

        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_immediate_timer_factory,
        )
        # Immediately schedule again — first should be cancelled
        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_immediate_timer_factory,
        )
        await asyncio.sleep(0.01)

        post_calls = [c for c in gateway.calls if c.method == "post_message"]
        # Exactly 2 (one mention + one embed from the second schedule only)
        assert len(post_calls) == 2


# ---------------------------------------------------------------------------
# Discord answer resets presence to nearby
# ---------------------------------------------------------------------------


class TestPresenceResetOnAnswer:
    """process_thread_reply resets presence to 'nearby' after successful write_answer."""

    @pytest.mark.anyio
    async def test_process_thread_reply_resets_presence(self) -> None:
        from runner.adapters.discord.thread_listener import process_thread_reply
        from runner.domain.signal import QuestionSignal, QuestionType, SignalStatus
        from tests.fakes.fake_signal_repository import FakeSignalRepository
        from datetime import datetime, timezone

        pc, _sc = _make_coordinator(initial_mode="away")

        config = DiscordConfig(
            channel_id="1234567890",
            guild_id="9876543210",
            notify_user_id="5555555555",
        )

        sig_repo = FakeSignalRepository()
        sig_repo.seed_question(
            QuestionSignal(
                ticket_id="T042",
                question="Clarification needed?",
                type=QuestionType.TEXT,
                options=None,
                status=SignalStatus.PENDING,
                answer=None,
                created_at=datetime.now(timezone.utc),
            )
        )

        # Build mock message matching thread T042
        message = MagicMock()
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 5555555555
        message.content = "Yes, proceed with the fix."
        message.reply = AsyncMock()

        channel = MagicMock()
        channel.parent_id = 1234567890
        channel.parent = MagicMock()
        channel.parent.id = 1234567890
        channel.name = "T042-some-slug"
        channel.send = AsyncMock()
        # Make it look like a thread
        import discord

        channel.__class__ = discord.Thread
        message.channel = channel

        result = await process_thread_reply(
            message, sig_repo, config, presence_coordinator=pc
        )

        assert result is True
        assert sig_repo.write_answer_calls == [("T042", "Yes, proceed with the fix.")]
        assert pc.current_mode == "nearby"

    @pytest.mark.anyio
    async def test_process_thread_reply_does_not_reset_on_failure(self) -> None:
        """Failed write_answer must NOT reset presence."""
        from runner.adapters.discord.thread_listener import process_thread_reply
        from tests.fakes.fake_signal_repository import FakeSignalRepository
        from runner.domain.exceptions import SignalFormatError

        pc, _sc = _make_coordinator(initial_mode="away")

        config = DiscordConfig(
            channel_id="1234567890",
            guild_id="9876543210",
            notify_user_id="5555555555",
        )

        sig_repo = FakeSignalRepository()
        sig_repo.write_answer = MagicMock(side_effect=SignalFormatError("No question file"))

        message = MagicMock()
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 5555555555
        message.content = "Answer text."
        message.reply = AsyncMock()

        channel = MagicMock()
        channel.parent_id = 1234567890
        channel.parent = MagicMock()
        channel.parent.id = 1234567890
        channel.name = "T042-some-slug"
        channel.send = AsyncMock()
        import discord

        channel.__class__ = discord.Thread
        message.channel = channel

        result = await process_thread_reply(
            message, sig_repo, config, presence_coordinator=pc
        )

        assert result is False
        # Presence must remain "away" — failure must not reset
        assert pc.current_mode == "away"

    @pytest.mark.anyio
    async def test_process_thread_reply_backward_compatible_without_coordinator(self) -> None:
        """process_thread_reply works without presence_coordinator (backward compat)."""
        from runner.adapters.discord.thread_listener import process_thread_reply
        from runner.domain.signal import QuestionSignal, QuestionType, SignalStatus
        from tests.fakes.fake_signal_repository import FakeSignalRepository
        from datetime import datetime, timezone

        config = DiscordConfig(
            channel_id="1234567890",
            guild_id="9876543210",
            notify_user_id="5555555555",
        )

        sig_repo = FakeSignalRepository()
        sig_repo.seed_question(
            QuestionSignal(
                ticket_id="T042",
                question="Question?",
                type=QuestionType.TEXT,
                options=None,
                status=SignalStatus.PENDING,
                answer=None,
                created_at=datetime.now(timezone.utc),
            )
        )

        message = MagicMock()
        message.author = MagicMock()
        message.author.bot = False
        message.author.id = 5555555555
        message.content = "Answer."
        message.reply = AsyncMock()

        channel = MagicMock()
        channel.parent_id = 1234567890
        channel.parent = MagicMock()
        channel.parent.id = 1234567890
        channel.name = "T042-slug"
        channel.send = AsyncMock()
        import discord

        channel.__class__ = discord.Thread
        message.channel = channel

        # No presence_coordinator passed — should work fine
        result = await process_thread_reply(message, sig_repo, config)

        assert result is True
        assert sig_repo.write_answer_calls == [("T042", "Answer.")]


# ---------------------------------------------------------------------------
# Security: notify_user_id not logged
# ---------------------------------------------------------------------------


class TestSecurityNotifyUserId:
    """notify_user_id must not appear in any log output, console, or state file."""

    @pytest.mark.anyio
    async def test_notify_user_id_not_in_state_store(self) -> None:
        """After escalation fires, notify_user_id must not be written to state."""
        store = FakeStateStore()
        pc, _sc = _make_coordinator(initial_mode="nearby", state_store=store)
        gateway = FakeDiscordGateway()
        notify_id = "SENSITIVE_ID_12345"
        logger = _make_discord_logger(gateway, notify_user_id=notify_id)

        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_immediate_timer_factory,
        )
        await asyncio.sleep(0.01)

        # Check all writes to state store do not contain the notify_user_id
        for write_call in store.write_calls:
            serialized = str(write_call)
            assert notify_id not in serialized


class TestEscalationConfiguredDelay:
    """PresenceCoordinator respects configured idle_escalation_minutes."""

    @pytest.mark.anyio
    async def test_escalation_uses_configured_idle_escalation_minutes(self) -> None:
        pc = PresenceCoordinator(idle_escalation_minutes=5.0)
        gateway = FakeDiscordGateway()
        logger = _make_discord_logger(gateway)

        recorded_delay: list[float] = []

        async def _capture_timer_factory(
            delay_seconds: float, callback: Any
        ) -> asyncio.Task[None]:
            recorded_delay.append(delay_seconds)

            async def _run() -> None:
                pass

            return asyncio.create_task(_run())

        await pc.schedule_escalation(
            "T042",
            "thread-99",
            logger,
            timer_factory=_capture_timer_factory,
        )

        assert recorded_delay == [300.0]

