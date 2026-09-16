"""OpenCode CLI adapter package."""

from runner.adapters.opencode.opencode_worker import (
    KNOWN_EVENT_TYPES,
    OpenCodeEvent,
    build_opencode_run_command,
    decode_event,
)

__all__ = [
    "KNOWN_EVENT_TYPES",
    "OpenCodeEvent",
    "build_opencode_run_command",
    "decode_event",
]
