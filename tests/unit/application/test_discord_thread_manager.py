"""Unit tests for DiscordThreadManager application service (T084)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest

from runner.adapters.discord.logger import COLOR_GREEN, DiscordLoggerImpl
from runner.application.discord_thread_manager import DiscordThreadManager
from runner.domain.exceptions import DiscordGatewayError
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_discord_gateway import FakeDiscordGateway
from tests.fakes.fake_discord_logger import FakeDiscordLogger


def make_test_ticket(
    ticket_id: str = "T042",
    title: str = "defer-clean-slate",
    slug: str = "defer-clean-slate",
) -> Ticket:
    """Helper to create a valid domain Ticket."""
    return Ticket(
        id=ticket_id,
        title=title,
        slug=slug,
        status=TicketStatus.PENDING,
        spec_path="docs/specs/05-presence-mode-and-discord.md",
        requirements=(),
        acceptance_criteria=(),
        gotchas=(),
        path=Path(f"docs/tickets/05-presence-mode-and-discord/{ticket_id}-{slug}.md"),
    )


@pytest.mark.anyio
async def test_smoke_scenario_1_open_ticket_thread_on_start() -> None:
    """Smoke Scenario 1: Thread opened on ticket start.

    Setup: FakeDiscordGateway configured to return ("thread-id-99", "msg-id-1") for create_thread.
           discord_enabled=True.
    Steps:
      1. Call open_ticket_thread(ticket, channel_id="channel-1").
      2. Inspect all gateway calls.
    Expected:
      create_thread called with name="T042-defer-clean-slate".
      pin_message called with ("thread-id-99", "msg-id-1").
      A second post_message (Live Digest placeholder) called in thread-id-99.
      Returns ("thread-id-99", "msg-id-1").
    """
    gateway = FakeDiscordGateway(create_thread_return=("thread-id-99", "msg-id-1"))
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    ticket = make_test_ticket()
    res = await manager.open_ticket_thread(ticket, channel_id="channel-1")

    # Return value matches expected tuple
    assert res == ("thread-id-99", "msg-id-1")

    # Verify calls on gateway
    assert len(gateway.calls) >= 3

    create_calls = [c for c in gateway.calls if c.method == "create_thread"]
    assert len(create_calls) == 1
    assert create_calls[0].channel_id == "channel-1"
    assert create_calls[0].name == "T042-defer-clean-slate"
    # Embed is Status Card embed
    assert create_calls[0].embed is not None
    assert "T042 · defer-clean-slate" in create_calls[0].embed["description"]

    pin_calls = [c for c in gateway.calls if c.method == "pin_message"]
    assert len(pin_calls) == 1
    assert pin_calls[0].channel_or_thread_id == "thread-id-99"
    assert pin_calls[0].message_id == "msg-id-1"

    post_calls = [c for c in gateway.calls if c.method == "post_message"]
    assert len(post_calls) == 1
    assert post_calls[0].channel_or_thread_id == "thread-id-99"


@pytest.mark.anyio
async def test_smoke_scenario_2_close_ticket_thread_on_commit() -> None:
    """Smoke Scenario 2: Thread closed on ticket commit.

    Setup: FakeDiscordGateway, known thread_id="thread-99", message_id="msg-1".
    Steps:
      1. Call close_ticket_thread("thread-99", "msg-1", commit_summary="feat(discord): add logger").
      2. Inspect calls.
    Expected:
      post_message call with green commit embed.
      edit_message call updating Status Card to ✅ Committed.
      archive_thread("thread-99") called last.
      No additional post_message calls after archive_thread.
    """
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    await manager.close_ticket_thread(
        "thread-99", "msg-1", commit_summary="feat(discord): add logger"
    )

    # Inspect calls sequence
    methods = [c.method for c in gateway.calls]
    assert methods == ["post_message", "edit_message", "archive_thread"]

    # 1. post_message with green commit embed
    post_call = gateway.calls[0]
    assert post_call.channel_or_thread_id == "thread-99"
    embed = post_call.embed
    assert embed is not None
    assert embed["title"] == "✅ Committed"
    assert embed["description"] == "feat(discord): add logger"
    assert embed["color"] == COLOR_GREEN
    assert embed["color"] == 0x57F287

    # 2. edit_message updating Status Card to ✅ Committed
    edit_call = gateway.calls[1]
    assert edit_call.channel_or_thread_id == "thread-99"
    assert edit_call.message_id == "msg-1"
    card_embed = edit_call.embed
    assert card_embed is not None
    assert "✅ Committed" in card_embed["description"]

    # 3. archive_thread called last
    archive_call = gateway.calls[2]
    assert archive_call.thread_id == "thread-99"


@pytest.mark.anyio
async def test_smoke_scenario_3_local_only_mode_zero_calls() -> None:
    """Smoke Scenario 3: No gateway calls in local-only mode.

    Setup: discord_enabled=False.
    Steps:
      1. Call open_ticket_thread(ticket, channel_id="channel-1").
      2. Call close_ticket_thread("x", "y", "summary").
    Expected:
      Zero calls to any FakeDiscordGateway method.
    """
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=False)

    ticket = make_test_ticket()
    res = await manager.open_ticket_thread(ticket, channel_id="channel-1")
    assert res == ("", "")

    await manager.close_ticket_thread("x", "y", "summary")
    await manager.update_status_card("x", "y", status="🟡 Working")

    assert len(gateway.calls) == 0


@pytest.mark.anyio
async def test_update_status_card_delegates_to_logger() -> None:
    """update_status_card delegates to logger.update_status_card."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    await manager.update_status_card(
        "thread-1",
        "msg-1",
        status="🟡 Reviewing",
        attempt=2,
        tokens_current=85000,
        started_at="10:00 UTC",
    )

    edit_calls = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(edit_calls) == 1
    embed = edit_calls[0].embed
    assert embed is not None
    assert "🟡 Reviewing" in embed["description"]
    assert "Attempt:      2 / 3" in embed["description"]
    assert "~85k / 150k" in embed["description"]


@pytest.mark.anyio
async def test_archive_thread_gateway_error_handled_gracefully() -> None:
    """archive_thread error on already-locked thread must not raise (Gotcha 3)."""
    gateway = FakeDiscordGateway(raise_on_archive_thread=DiscordGatewayError("Already locked"))
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    # Should not raise DiscordGatewayError
    await manager.close_ticket_thread("thread-99", "msg-1", commit_summary="feat: done")

    archive_calls = [c for c in gateway.calls if c.method == "archive_thread"]
    assert len(archive_calls) == 1


@pytest.mark.anyio
async def test_thread_name_formatting_variations() -> None:
    """Thread name is exactly {ticket_id}-{slug}, avoiding duplicate prefixes."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    # 1. Normal slug without prefix
    t1 = make_test_ticket("T042", "defer-clean-slate", "defer-clean-slate")
    await manager.open_ticket_thread(t1, channel_id="c1")
    assert gateway.calls[-3].name == "T042-defer-clean-slate"

    # 2. Slug already prefixed with ticket_id
    t2 = make_test_ticket("T043", "T043-my-feature", "T043-my-feature")
    await manager.open_ticket_thread(t2, channel_id="c1")
    assert gateway.calls[-3].name == "T043-my-feature"

    # 3. Dict-like ticket
    t3 = {"id": "T044", "slug": "dict-ticket", "spec": "05-presence"}
    await manager.open_ticket_thread(t3, channel_id="c1")
    assert gateway.calls[-3].name == "T044-dict-ticket"


@pytest.mark.anyio
async def test_routing_with_fake_discord_logger() -> None:
    """DiscordThreadManager works seamlessly with FakeDiscordLogger test double."""
    gateway = FakeDiscordGateway()
    logger = FakeDiscordLogger()
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    ticket = make_test_ticket("T084", "thread-manager", "thread-manager")
    res = await manager.open_ticket_thread(ticket, channel_id="c-main")

    assert len(res) == 2
    assert len(logger.live_digest_starts) == 1
    assert logger.live_digest_starts[0][0] == res[0]

    await manager.close_ticket_thread(res[0], res[1], commit_summary="test commit")
    assert len(logger.embed_calls) == 1
    assert logger.embed_calls[0][1]["title"] == "✅ Committed"
    assert len(logger.status_card_updates) == 1
    assert logger.status_card_updates[0]["status"] == "✅ Committed"


@pytest.mark.anyio
async def test_open_ticket_thread_populates_logger_status_cards() -> None:
    """open_ticket_thread populates logger._status_cards so subsequent updates retain metadata."""
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    ticket = make_test_ticket("T099", "custom-slug-feature", "custom-slug-feature")
    thread_id, msg_id = await manager.open_ticket_thread(ticket, channel_id="c-main")

    # Update without passing ticket or spec
    await manager.update_status_card(thread_id, msg_id, status="🟡 Verifying")

    edit_calls = [c for c in gateway.calls if c.method == "edit_message"]
    assert len(edit_calls) == 1
    card_desc = edit_calls[0].embed["description"]
    assert "T099 · custom-slug-feature" in card_desc
    assert "05-presence-mode-and-discord" in card_desc
    assert "🟡 Verifying" in card_desc


@pytest.mark.anyio
async def test_live_digest_forwarding_methods() -> None:
    """update_live_digest and finish_live_digest forward to logger or no-op when disabled."""
    gateway = FakeDiscordGateway()
    logger = FakeDiscordLogger()
    manager = DiscordThreadManager(gateway, logger, discord_enabled=True)

    await manager.update_live_digest("chunk 1", thread_id="t-1")
    await manager.finish_live_digest(thread_id="t-1")

    assert ("chunk 1", "t-1") in logger.live_digest_updates
    assert "t-1" in logger.live_digest_finishes

    # Disabled mode
    disabled_manager = DiscordThreadManager(gateway, logger, discord_enabled=False)
    await disabled_manager.update_live_digest("chunk 2", thread_id="t-2")
    await disabled_manager.finish_live_digest(thread_id="t-2")

    assert ("chunk 2", "t-2") not in logger.live_digest_updates
    assert "t-2" not in logger.live_digest_finishes


@pytest.mark.anyio
async def test_default_logger_instantiation() -> None:
    """DiscordThreadManager instantiates DiscordLoggerImpl by default if logger is omitted."""
    gateway = FakeDiscordGateway()
    manager = DiscordThreadManager(gateway)
    assert isinstance(manager._logger, DiscordLoggerImpl)


@pytest.mark.anyio
async def test_close_ticket_thread_fallback_when_logger_lacks_post_embed() -> None:
    """If logger lacks post_embed, close_ticket_thread falls back to gateway.post_message."""
    gateway = FakeDiscordGateway()

    class _MinimalLogger:
        async def update_status_card(self, *args: Any, **kwargs: Any) -> None:
            pass

    manager = DiscordThreadManager(gateway, logger=_MinimalLogger(), discord_enabled=True)  # type: ignore
    await manager.close_ticket_thread("t-1", "m-1", commit_summary="minimal commit")

    post_calls = [c for c in gateway.calls if c.method == "post_message"]
    assert len(post_calls) == 1
    assert post_calls[0].embed["title"] == "✅ Committed"
    assert post_calls[0].embed["description"] == "minimal commit"

