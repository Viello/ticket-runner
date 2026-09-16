"""Markdown adapters (ticket parsing, serialization, queue storage, and file locking)."""

from runner.adapters.markdown.file_lock import DEFAULT_LOCK_PATH, QueueFileLock
from runner.adapters.markdown.gotchas_store import (
    DEFAULT_GOTCHAS_PATH,
    DEFAULT_SKELETON,
    GotchasStore,
    normalize_entry,
)
from runner.adapters.markdown.parser import TicketMarkdownParser
from runner.adapters.markdown.spec_parser import (
    SpecExcerpt,
    SpecMarkdownParser,
    SpecParser,
    extract_spec_excerpt,
)
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.domain.exceptions import SpecFormatError

__all__ = [
    "DEFAULT_GOTCHAS_PATH",
    "DEFAULT_LOCK_PATH",
    "DEFAULT_SKELETON",
    "DirectoryTicketStore",
    "GotchasStore",
    "QueueFileLock",
    "SpecExcerpt",
    "SpecFormatError",
    "SpecMarkdownParser",
    "SpecParser",
    "TicketMarkdownParser",
    "extract_spec_excerpt",
    "normalize_entry",
]
