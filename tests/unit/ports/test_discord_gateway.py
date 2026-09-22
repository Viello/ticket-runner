"""Unit tests for DiscordGateway port and FakeDiscordGateway test double (T071)."""

from __future__ import annotations

import pytest

from runner.ports import DiscordGateway, DiscordGatewayError
from runner.domain.exceptions import TicketRunnerError
from tests.fakes import DiscordCall, FakeDiscordGateway


class _ConformingAdapterShell:
    """Mock/shell of a real adapter conforming to DiscordGateway."""

    async def post_message(
        self, channel_or_thread_id: str, content: str, *, embed: dict | None = None
    ) -> str:
        return "msg-shell-1"

    async def edit_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
        content: str,
        *,
        embed: dict | None = None,
    ) -> None:
        pass

    async def pin_message(self, channel_or_thread_id: str, message_id: str) -> None:
        pass

    async def create_thread(
        self,
        channel_id: str,
        name: str,
        starter_message: str,
        *,
        embed: dict | None = None,
    ) -> tuple[str, str]:
        return ("thread-shell-1", "msg-shell-starter")

    async def edit_thread(
        self, thread_id: str, *, archived: bool = False, locked: bool = False
    ) -> None:
        pass

    async def archive_thread(self, thread_id: str) -> None:
        pass

    async def delete_message(self, channel_or_thread_id: str, message_id: str) -> None:
        pass



class _MissingMethodAdapterShell:
    """Non-conforming shell missing archive_thread."""

    async def post_message(
        self, channel_or_thread_id: str, content: str, *, embed: dict | None = None
    ) -> str:
        return "msg-1"

    async def edit_message(
        self,
        channel_or_thread_id: str,
        message_id: str,
        content: str,
        *,
        embed: dict | None = None,
    ) -> None:
        pass

    async def pin_message(self, channel_or_thread_id: str, message_id: str) -> None:
        pass

    async def create_thread(
        self,
        channel_id: str,
        name: str,
        starter_message: str,
        *,
        embed: dict | None = None,
    ) -> tuple[str, str]:
        return ("t1", "m1")

    async def edit_thread(
        self, thread_id: str, *, archived: bool = False, locked: bool = False
    ) -> None:
        pass


def test_ports_reexports() -> None:
    """DiscordGateway and DiscordGatewayError are exported from runner.ports."""
    assert issubclass(DiscordGatewayError, TicketRunnerError)
    assert hasattr(DiscordGateway, "post_message")
    assert hasattr(DiscordGateway, "edit_message")
    assert hasattr(DiscordGateway, "pin_message")
    assert hasattr(DiscordGateway, "create_thread")
    assert hasattr(DiscordGateway, "edit_thread")
    assert hasattr(DiscordGateway, "archive_thread")
    assert hasattr(DiscordGateway, "delete_message")



def test_protocol_conformance_checks() -> None:
    """runtime_checkable protocol verifies FakeDiscordGateway and conforming shells."""
    fake = FakeDiscordGateway()
    assert isinstance(fake, DiscordGateway)

    shell = _ConformingAdapterShell()
    assert isinstance(shell, DiscordGateway)

    incomplete = _MissingMethodAdapterShell()
    assert not isinstance(incomplete, DiscordGateway)

    assert not isinstance(object(), DiscordGateway)


@pytest.mark.anyio
async def test_fake_gateway_post_message() -> None:
    """post_message returns auto-incremented string ID and appends DiscordCall."""
    fake = FakeDiscordGateway()
    msg_id_1 = await fake.post_message("chan-1", "First message")
    assert msg_id_1 == "1"

    embed = {"title": "Test Embed", "color": 0x00FF00}
    msg_id_2 = await fake.post_message("chan-1", "Second message", embed=embed)
    assert msg_id_2 == "2"

    assert len(fake.calls) == 2

    call1 = fake.calls[0]
    assert call1.method == "post_message"
    assert call1.args == ("chan-1", "First message")
    assert call1.kwargs == {"embed": None}
    assert call1.channel_or_thread_id == "chan-1"
    assert call1.content == "First message"
    assert call1.embed is None

    call2 = fake.calls[1]
    assert call2.method == "post_message"
    assert call2.args == ("chan-1", "Second message")
    assert call2.kwargs == {"embed": embed}
    assert call2.embed == embed

    assert fake.messages["1"]["content"] == "First message"
    assert fake.messages["2"]["embed"] == embed


@pytest.mark.anyio
async def test_fake_gateway_create_thread() -> None:
    """create_thread returns (thread_id, starter_message_id) tuple of strings and records call."""
    fake = FakeDiscordGateway()
    thread_id, starter_msg_id = await fake.create_thread(
        "chan-1", "T001-test", "Starting thread", embed={"description": "detail"}
    )

    assert isinstance(thread_id, str)
    assert isinstance(starter_msg_id, str)
    assert thread_id != starter_msg_id

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.method == "create_thread"
    assert call.channel_id == "chan-1"
    assert call.name == "T001-test"
    assert call.starter_message == "Starting thread"
    assert call.embed == {"description": "detail"}

    assert thread_id in fake.threads
    thread = fake.threads[thread_id]
    assert thread["name"] == "T001-test"
    assert thread["starter_message_id"] == starter_msg_id
    assert thread["archived"] is False
    assert thread["locked"] is False

    assert starter_msg_id in fake.messages
    assert fake.messages[starter_msg_id]["content"] == "Starting thread"


@pytest.mark.anyio
async def test_fake_gateway_edit_message() -> None:
    """edit_message records DiscordCall and updates in-memory message."""
    fake = FakeDiscordGateway()
    msg_id = await fake.post_message("chan-1", "Initial content")

    await fake.edit_message("chan-1", msg_id, "Updated content", embed={"key": "val"})

    assert len(fake.calls) == 2
    call = fake.calls[1]
    assert call.method == "edit_message"
    assert call.channel_or_thread_id == "chan-1"
    assert call.message_id == msg_id
    assert call.content == "Updated content"
    assert call.embed == {"key": "val"}

    assert fake.messages[msg_id]["content"] == "Updated content"
    assert fake.messages[msg_id]["embed"] == {"key": "val"}


@pytest.mark.anyio
async def test_fake_gateway_pin_message() -> None:
    """pin_message records DiscordCall and marks message as pinned in-memory."""
    fake = FakeDiscordGateway()
    msg_id = await fake.post_message("chan-1", "Pin this")

    await fake.pin_message("chan-1", msg_id)

    assert len(fake.calls) == 2
    call = fake.calls[1]
    assert call.method == "pin_message"
    assert call.channel_or_thread_id == "chan-1"
    assert call.message_id == msg_id

    assert fake.messages[msg_id]["pinned"] is True
    assert msg_id in fake.pinned_messages


@pytest.mark.anyio
async def test_fake_gateway_edit_thread() -> None:
    """edit_thread records DiscordCall and updates thread archived and locked status."""
    fake = FakeDiscordGateway()
    thread_id, _ = await fake.create_thread("chan-1", "T002-test", "Starter")

    await fake.edit_thread(thread_id, archived=True, locked=False)

    call = fake.calls[-1]
    assert call.method == "edit_thread"
    assert call.thread_id == thread_id
    assert call.archived is True
    assert call.locked is False

    assert fake.threads[thread_id]["archived"] is True
    assert fake.threads[thread_id]["locked"] is False


@pytest.mark.anyio
async def test_fake_gateway_archive_thread_equivalent_to_edit_thread() -> None:
    """archive_thread records call and sets archived=True, locked=True equivalent to edit_thread."""
    fake = FakeDiscordGateway()
    thread_id, _ = await fake.create_thread("chan-1", "T003-test", "Starter")

    await fake.archive_thread(thread_id)

    call = fake.calls[-1]
    assert call.method == "archive_thread"
    assert call.thread_id == thread_id

    # Functional state is equivalent to edit_thread(thread_id, archived=True, locked=True)
    assert fake.threads[thread_id]["archived"] is True
    assert fake.threads[thread_id]["locked"] is True


@pytest.mark.anyio
async def test_fake_gateway_delete_message() -> None:
    """delete_message records DiscordCall and removes message from in-memory store."""
    fake = FakeDiscordGateway()
    msg_id = await fake.post_message("chan-1", "To be deleted")
    await fake.pin_message("chan-1", msg_id)

    assert msg_id in fake.messages
    assert msg_id in fake.pinned_messages

    await fake.delete_message("chan-1", msg_id)

    assert len(fake.calls) == 3
    call = fake.calls[-1]
    assert call.method == "delete_message"
    assert call.channel_or_thread_id == "chan-1"
    assert call.message_id == msg_id

    assert msg_id not in fake.messages
    assert msg_id not in fake.pinned_messages


@pytest.mark.anyio
async def test_all_seven_call_types_produce_correct_discord_calls() -> None:
    """Verifies all seven call types append distinct, well-formed DiscordCall instances."""
    fake = FakeDiscordGateway()

    m_id = await fake.post_message("chan-1", "hello")
    await fake.edit_message("chan-1", m_id, "hello world")
    await fake.pin_message("chan-1", m_id)
    t_id, _ = await fake.create_thread("chan-1", "thread", "starter")
    await fake.edit_thread(t_id, archived=False, locked=True)
    await fake.archive_thread(t_id)
    await fake.delete_message("chan-1", m_id)

    assert len(fake.calls) == 7
    methods = [call.method for call in fake.calls]
    assert methods == [
        "post_message",
        "edit_message",
        "pin_message",
        "create_thread",
        "edit_thread",
        "archive_thread",
        "delete_message",
    ]



def test_pending_replies_list() -> None:
    """FakeDiscordGateway exposes pending_replies list for test orchestration."""
    fake = FakeDiscordGateway()
    assert fake.pending_replies == []
    fake.pending_replies.append("Yes, proceed.")
    assert fake.pending_replies == ["Yes, proceed."]


def test_discord_call_namedtuple_behavior() -> None:
    """DiscordCall is a NamedTuple supporting unpacking, index access, and properties."""
    call = DiscordCall(
        method="post_message",
        args=("chan-42", "hello"),
        kwargs={"embed": {"title": "info"}},
    )
    method, args, kwargs = call
    assert method == "post_message"
    assert args == ("chan-42", "hello")
    assert kwargs == {"embed": {"title": "info"}}
    assert call[0] == "post_message"
    assert call.channel_or_thread_id == "chan-42"
    assert call.content == "hello"
    assert call.embed == {"title": "info"}
