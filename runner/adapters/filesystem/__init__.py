"""Filesystem adapters (runtime artifact stores under .agent/)."""

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository

__all__ = [
    "FilesystemSignalRepository",
]
