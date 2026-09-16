"""Atomic text file replacement via sibling temporary files."""

from __future__ import annotations

import os
from pathlib import Path

TEMP_SUFFIX = ".tmp"


def atomic_write_text(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    """Write text to a sibling temporary file, then atomically replace the target.

    The temporary file is removed on any failure, so a stray ``.tmp`` artifact
    is never left behind. Errors propagate to the caller after cleanup.

    Args:
        path: Destination file path.
        content: Text to write, including the original line endings.
        encoding: Text encoding used for the temporary file.
    """
    target = Path(path)
    temp_path = target.with_name(target.name + TEMP_SUFFIX)
    try:
        with temp_path.open("w", encoding=encoding, newline="") as handle:
            handle.write(content)
        os.replace(temp_path, target)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
