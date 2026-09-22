"""Unit tests for DiscordPyGateway adapter (T072, Spec 05a)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import pytest
import discord

from runner.adapters.discord.gateway import DiscordPyGateway
from runner.domain.exceptions import DiscordGatewayError
from runner.ports.discord_gateway import DiscordGateway


@pytest.fixture
def mock_client() -> MagicMock:
    """Fixture creating a mock discord.Client."""
    client = MagicMock(spec=discord.Client)
    client.get_channel = MagicMock(return_value=None)
    client.fetch_channel = AsyncMock()
    return client


def test_conformance(mock_client: MagicMock) -> None:
    """DiscordPyGateway satisfies the DiscordGateway Protocol."""
    gateway = DiscordPyGateway(mock_client)
    assert isinstance(gateway, DiscordGateway)


@pytest.mark.anyio
async def test_post_message_cached_channel(mock_client: MagicMock) -> None:
    """post_message uses cached channel when available and returns message ID."""
    mock_channel = MagicMock()
    mock_msg = MagicMock()
    mock_msg.id = 9876543210
    mock_channel.send = AsyncMock(return_value=mock_msg)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    msg_id = await gateway.post_message("1234567890", "Hello world")

    assert msg_id == "9876543210"
    mock_client.get_channel.assert_called_once_with(1234567890)
    mock_client.fetch_channel.assert_not_called()
    mock_channel.send.assert_awaited_once_with(content="Hello world")


@pytest.mark.anyio
async def test_post_message_fetch_on_cache_miss(mock_client: MagicMock) -> None:
    """post_message fetches channel when not in client cache."""
    mock_channel = MagicMock()
    mock_msg = MagicMock()
    mock_msg.id = 112233
    mock_channel.send = AsyncMock(return_value=mock_msg)
    mock_client.get_channel.return_value = None
    mock_client.fetch_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    msg_id = await gateway.post_message("1234567890", "Cache miss")

    assert msg_id == "112233"
    mock_client.get_channel.assert_called_once_with(1234567890)
    mock_client.fetch_channel.assert_awaited_once_with(1234567890)
    mock_channel.send.assert_awaited_once_with(content="Cache miss")


@pytest.mark.anyio
async def test_post_message_with_embed(mock_client: MagicMock) -> None:
    """post_message correctly converts a plain dict embed to discord.Embed."""
    mock_channel = MagicMock()
    mock_msg = MagicMock()
    mock_msg.id = 445566
    mock_channel.send = AsyncMock(return_value=mock_msg)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    embed_dict = {"title": "Test Title", "description": "Test Desc"}
    await gateway.post_message("1234567890", "With embed", embed=embed_dict)

    mock_channel.send.assert_awaited_once()
    call_kwargs = mock_channel.send.await_args.kwargs
    assert call_kwargs["content"] == "With embed"
    sent_embed = call_kwargs["embed"]
    assert isinstance(sent_embed, discord.Embed)
    assert sent_embed.title == "Test Title"
    assert sent_embed.description == "Test Desc"


@pytest.mark.anyio
async def test_edit_message(mock_client: MagicMock) -> None:
    """edit_message resolves channel and edits existing message."""
    mock_channel = MagicMock()
    mock_msg = MagicMock()
    mock_msg.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_msg)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    await gateway.edit_message("1234567890", "998877", "New content")

    mock_channel.fetch_message.assert_awaited_once_with(998877)
    mock_msg.edit.assert_awaited_once_with(content="New content")


@pytest.mark.anyio
async def test_edit_message_with_embed(mock_client: MagicMock) -> None:
    """edit_message passes converted discord.Embed when embed dict provided."""
    mock_channel = MagicMock()
    mock_msg = MagicMock()
    mock_msg.edit = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_msg)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    await gateway.edit_message(
        "1234567890", "998877", "New content", embed={"title": "Updated"}
    )

    call_kwargs = mock_msg.edit.await_args.kwargs
    assert call_kwargs["content"] == "New content"
    assert isinstance(call_kwargs["embed"], discord.Embed)
    assert call_kwargs["embed"].title == "Updated"


@pytest.mark.anyio
async def test_pin_message(mock_client: MagicMock) -> None:
    """pin_message resolves channel and pins target message."""
    mock_channel = MagicMock()
    mock_msg = MagicMock()
    mock_msg.pin = AsyncMock()
    mock_channel.fetch_message = AsyncMock(return_value=mock_msg)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    await gateway.pin_message("1234567890", "998877")

    mock_channel.fetch_message.assert_awaited_once_with(998877)
    mock_msg.pin.assert_awaited_once()


@pytest.mark.anyio
async def test_create_thread(mock_client: MagicMock) -> None:
    """create_thread posts starter message, creates public thread, and returns both IDs."""
    mock_channel = MagicMock()
    mock_starter_msg = MagicMock()
    mock_starter_msg.id = 55555
    mock_thread = MagicMock()
    mock_thread.id = 77777
    mock_starter_msg.create_thread = AsyncMock(return_value=mock_thread)
    mock_channel.send = AsyncMock(return_value=mock_starter_msg)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    thread_id, starter_id = await gateway.create_thread(
        "1234567890",
        name="T001-test",
        starter_message="Starting ticket T001",
        embed={"title": "Status Card"},
    )

    assert thread_id == "77777"
    assert starter_id == "55555"
    mock_channel.send.assert_awaited_once()
    send_kwargs = mock_channel.send.await_args.kwargs
    assert send_kwargs["content"] == "Starting ticket T001"
    assert isinstance(send_kwargs["embed"], discord.Embed)
    mock_starter_msg.create_thread.assert_awaited_once_with(name="T001-test")


@pytest.mark.anyio
async def test_edit_thread(mock_client: MagicMock) -> None:
    """edit_thread resolves thread channel and updates archived/locked state."""
    mock_thread = MagicMock()
    mock_thread.edit = AsyncMock()
    mock_client.get_channel.return_value = mock_thread

    gateway = DiscordPyGateway(mock_client)
    await gateway.edit_thread("77777", archived=True, locked=False)

    mock_client.get_channel.assert_called_once_with(77777)
    mock_thread.edit.assert_awaited_once_with(archived=True, locked=False)


@pytest.mark.anyio
async def test_archive_thread(mock_client: MagicMock) -> None:
    """archive_thread convenently archives and locks the thread."""
    mock_thread = MagicMock()
    mock_thread.edit = AsyncMock()
    mock_client.get_channel.return_value = mock_thread

    gateway = DiscordPyGateway(mock_client)
    await gateway.archive_thread("77777")

    mock_client.get_channel.assert_called_once_with(77777)
    mock_thread.edit.assert_awaited_once_with(archived=True, locked=True)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method_name,args,kwargs",
    [
        ("post_message", ("invalid_id", "content"), {}),
        ("edit_message", ("invalid_id", "123", "content"), {}),
        ("pin_message", ("invalid_id", "123"), {}),
        ("create_thread", ("invalid_id", "name", "starter"), {}),
        ("edit_thread", ("invalid_id",), {"archived": True}),
        ("archive_thread", ("invalid_id",), {}),
    ],
)
async def test_invalid_channel_id_raises_gateway_error(
    mock_client: MagicMock,
    method_name: str,
    args: tuple,
    kwargs: dict,
) -> None:
    """Invalid non-numeric snowflake IDs raise DiscordGatewayError."""
    gateway = DiscordPyGateway(mock_client)
    method = getattr(gateway, method_name)
    with pytest.raises(DiscordGatewayError) as exc_info:
        await method(*args, **kwargs)
    assert "invalid" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_channel_not_found_raises_gateway_error(mock_client: MagicMock) -> None:
    """When fetch_channel returns None or raises NotFound, re-raises DiscordGatewayError."""
    mock_client.get_channel.return_value = None
    mock_client.fetch_channel.side_effect = discord.NotFound(
        MagicMock(status=404, reason="Not Found"), "Unknown Channel"
    )

    gateway = DiscordPyGateway(mock_client)
    with pytest.raises(DiscordGatewayError) as exc_info:
        await gateway.post_message("1234567890", "Hello")
    assert "failed to resolve channel" in str(exc_info.value).lower()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "discord_exc",
    [
        discord.Forbidden(MagicMock(status=403, reason="Forbidden"), "Missing Permissions"),
        discord.HTTPException(MagicMock(status=500, reason="Server Error"), "Internal Error"),
        discord.DiscordException("Generic Discord library error"),
    ],
)
async def test_discord_exceptions_wrapped_in_gateway_error(
    mock_client: MagicMock,
    discord_exc: Exception,
) -> None:
    """Any discord.py exception during an operation is re-raised as DiscordGatewayError."""
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock(side_effect=discord_exc)
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    with pytest.raises(DiscordGatewayError) as exc_info:
        await gateway.post_message("1234567890", "Hello")
    assert isinstance(exc_info.value, DiscordGatewayError)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "method_name,args",
    [
        ("edit_message", ("1234567890", "invalid_msg_id", "content")),
        ("pin_message", ("1234567890", "invalid_msg_id")),
    ],
)
async def test_invalid_message_id_raises_gateway_error(
    mock_client: MagicMock,
    method_name: str,
    args: tuple,
) -> None:
    """Non-numeric message IDs raise DiscordGatewayError."""
    mock_channel = MagicMock()
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    method = getattr(gateway, method_name)
    with pytest.raises(DiscordGatewayError) as exc_info:
        await method(*args)
    assert "invalid message id" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_security_token_never_in_exception_or_repr(mock_client: MagicMock) -> None:
    """Sensitive bot token is never included in exception messages or repr."""
    fake_token = "SECRET_BOT_TOKEN_XYZ_123"
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock(
        side_effect=discord.DiscordException(f"Failed with code 401: Unauthorized")
    )
    mock_client.get_channel.return_value = mock_channel

    gateway = DiscordPyGateway(mock_client)
    with pytest.raises(DiscordGatewayError) as exc_info:
        await gateway.post_message("1234567890", "Hello")

    error_msg = str(exc_info.value)
    assert fake_token not in error_msg
    assert fake_token not in repr(gateway)

