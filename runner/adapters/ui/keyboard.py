"""Non-blocking Windows keyboard dispatcher and hotkey event loop (T058)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from runner.application.hotkey_dispatch import HotkeyDispatcher

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]


def read_windows_key(msvcrt_module: Any = msvcrt) -> str | None:
    """Read a single keypress from Windows console using msvcrt without blocking.

    Discards two-byte special keys (arrows, function keys with prefix 0x00 or 0xE0).
    Decodes ASCII characters with lowercase normalization for case-insensitivity.
    Falls back cleanly to returning None if msvcrt is absent or no key is hit.
    """
    if msvcrt_module is None:
        return None

    try:
        if not msvcrt_module.kbhit():
            return None

        char_bytes = msvcrt_module.getch()

        # Handle 2-byte special keys (e.g. arrows, F-keys) - discard per Spec 06
        if char_bytes in (b"\x00", b"\xe0"):
            if msvcrt_module.kbhit():
                msvcrt_module.getch()
            return None

        if char_bytes == b"\x1b":
            return "esc"

        decoded = char_bytes.decode("ascii", errors="ignore").lower()
        return decoded if decoded else None
    except Exception:
        return None


def default_windows_key_reader() -> str | None:
    """Default key-reader seam reading from msvcrt on Windows."""
    return read_windows_key(msvcrt_module=msvcrt)


class KeyboardPoller:
    """Non-blocking keyboard poller scheduling an async event loop polling task."""

    def __init__(
        self,
        key_reader: Callable[[], str | None] | None = None,
        on_key: Callable[[str], Any] | None = None,
        poll_interval: float = 0.05,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self._key_reader = key_reader if key_reader is not None else default_windows_key_reader
        self._on_key = on_key
        self._poll_interval = poll_interval
        self._sleep_fn = sleep_fn or asyncio.sleep
        self._task: asyncio.Task[None] | None = None
        self._running: bool = False

    @property
    def is_running(self) -> bool:
        """Return True if background poller task is currently active."""
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> asyncio.Task[None]:
        """Start the background async polling loop on the current event loop."""
        if self._running and self._task is not None and not self._task.done():
            return self._task

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        return self._task

    async def stop(self) -> None:
        """Cancel and await the polling loop task during runner cleanup."""
        self._running = False
        if self._task is not None:
            if not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None

    async def _poll_loop(self) -> None:
        """Continuously poll for keypresses and dispatch to handler."""
        try:
            while self._running:
                try:
                    key = self._key_reader()
                    if key is not None and self._on_key is not None:
                        res = self._on_key(key)
                        if asyncio.iscoroutine(res):
                            await res
                except Exception:
                    pass

                await self._sleep_fn(self._poll_interval)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False


__all__ = [
    "HotkeyDispatcher",
    "KeyboardPoller",
    "default_windows_key_reader",
    "read_windows_key",
]
