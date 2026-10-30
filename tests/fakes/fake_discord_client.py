"""In-memory test double for DiscordClient lifecycle (T130)."""

from __future__ import annotations

import asyncio
from typing import Any


class FakeDiscordClient:
    """Stand-in exposing the lifecycle surface the Runner drives.

    `client` and `tree` are plain sentinels: DiscordPyGateway only touches the
    wrapped client lazily, so constructing the gateway against this double is safe.
    """

    def __init__(self, ready: bool = True, ready_error: Exception | None = None) -> None:
        self.ready_event = asyncio.Event()
        self.ready_error: Exception | None = ready_error
        self.started = False
        self.closed = False
        self.client: Any = object()
        self.tree: Any = None
        self._ready = ready

    async def start(self, token: str | None = None) -> None:
        self.started = True
        if self._ready and self.ready_error is None:
            self.ready_event.set()

    async def close(self) -> None:
        self.closed = True
        self.ready_event.clear()
