"""Unit tests for non-blocking keyboard poller and Windows msvcrt reader (T058)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from runner.adapters.ui.keyboard import (
    KeyboardPoller,
    default_windows_key_reader,
    read_windows_key,
)


def test_read_windows_key_returns_none_when_no_key_pressed() -> None:
    mock_msvcrt = MagicMock()
    mock_msvcrt.kbhit.return_value = False

    result = read_windows_key(msvcrt_module=mock_msvcrt)
    assert result is None
    mock_msvcrt.getch.assert_not_called()


def test_read_windows_key_decodes_ascii_and_lowercases() -> None:
    mock_msvcrt = MagicMock()
    mock_msvcrt.kbhit.return_value = True
    mock_msvcrt.getch.return_value = b"P"

    result = read_windows_key(msvcrt_module=mock_msvcrt)
    assert result == "p"


def test_read_windows_key_discards_special_keys_e0_prefix() -> None:
    mock_msvcrt = MagicMock()
    mock_msvcrt.kbhit.side_effect = [True, True]  # first for initial hit, second for trailing byte
    mock_msvcrt.getch.side_effect = [b"\xe0", b"H"]  # Up Arrow sequence

    result = read_windows_key(msvcrt_module=mock_msvcrt)
    assert result is None
    assert mock_msvcrt.getch.call_count == 2


def test_read_windows_key_discards_special_keys_00_prefix() -> None:
    mock_msvcrt = MagicMock()
    mock_msvcrt.kbhit.side_effect = [True, True]
    mock_msvcrt.getch.side_effect = [b"\x00", b";"]  # F1 sequence

    result = read_windows_key(msvcrt_module=mock_msvcrt)
    assert result is None
    assert mock_msvcrt.getch.call_count == 2


def test_read_windows_key_falls_back_when_msvcrt_is_none() -> None:
    result = read_windows_key(msvcrt_module=None)
    assert result is None


def test_read_windows_key_ignores_non_ascii_bytes() -> None:
    mock_msvcrt = MagicMock()
    mock_msvcrt.kbhit.return_value = True
    mock_msvcrt.getch.return_value = b"\xff"

    result = read_windows_key(msvcrt_module=mock_msvcrt)
    assert result is None


@pytest.mark.anyio
async def test_keyboard_poller_dispatches_keys_from_reader() -> None:
    keys = ["p", None, "m", None, "q"]
    key_index = 0

    def fake_reader() -> str | None:
        nonlocal key_index
        if key_index < len(keys):
            k = keys[key_index]
            key_index += 1
            return k
        return None

    received: list[str] = []

    poller = KeyboardPoller(
        key_reader=fake_reader,
        on_key=received.append,
        poll_interval=0.01,
    )

    task = poller.start()
    assert task is not None
    assert not task.done()

    # Wait for poller to consume keys
    for _ in range(20):
        if len(received) >= 3:
            break
        await asyncio.sleep(0.01)

    await poller.stop()
    assert task.done()
    assert received == ["p", "m", "q"]


@pytest.mark.anyio
async def test_keyboard_poller_supports_async_on_key() -> None:
    received: list[str] = []

    async def async_handler(key: str) -> None:
        await asyncio.sleep(0.001)
        received.append(key)

    key_queue = ["p"]

    def fake_reader() -> str | None:
        if key_queue:
            return key_queue.pop(0)
        return None

    poller = KeyboardPoller(
        key_reader=fake_reader,
        on_key=async_handler,
        poll_interval=0.01,
    )

    poller.start()
    await asyncio.sleep(0.03)
    await poller.stop()

    assert received == ["p"]


@pytest.mark.anyio
async def test_keyboard_poller_clean_cancellation_without_warnings() -> None:
    poller = KeyboardPoller(
        key_reader=lambda: None,
        poll_interval=0.05,
    )
    task = poller.start()
    assert not task.done()

    # Repeated start calls return same active task
    assert poller.start() is task

    await poller.stop()
    assert task.done()
    assert poller._task is None


@pytest.mark.anyio
async def test_keyboard_poller_survives_callback_exception() -> None:
    call_count = 0
    received: list[str] = []

    def faulty_handler(key: str) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("simulated handler error")
        received.append(key)

    keys = ["p", "m"]

    def fake_reader() -> str | None:
        if keys:
            return keys.pop(0)
        return None

    poller = KeyboardPoller(
        key_reader=fake_reader,
        on_key=faulty_handler,
        poll_interval=0.01,
    )

    poller.start()
    await asyncio.sleep(0.04)
    await poller.stop()

    assert call_count == 2
    assert received == ["m"]
