"""Filesystem-backed StateStore persisting documents as UTF-8 JSON via atomic replacement."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.domain.exceptions import StateFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.ports.state_store import StateStore

DEFAULT_MAX_BYTES = 1024 * 1024  # 1 MiB


class JsonStateStore(StateStore):
    """Binds the StateStore port to a filesystem path using bounded reads and atomic writes."""

    def __init__(
        self,
        target: RuntimePaths | Path | str | None = None,
        *,
        path: Path | str | None = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        if path is not None:
            self._path = Path(path)
        elif isinstance(target, RuntimePaths):
            self._path = target.state_path
        elif isinstance(target, (Path, str)):
            self._path = Path(target)
        elif target is None:
            self._path = RuntimePaths().state_path
        else:
            raise TypeError(f"Expected RuntimePaths, Path, or str, got {type(target).__name__}")
        self._max_bytes = max_bytes

    @property
    def path(self) -> Path:
        """Return the underlying state file path."""
        return self._path

    def read(self) -> dict[str, Any] | None:
        """Read and parse the persisted state document.

        Returns:
            The parsed state document as a dictionary, or None if the file is absent.

        Raises:
            StateFormatError: If the file exists but exceeds the byte cap, is not valid
                UTF-8, contains malformed JSON, has a non-object root, or cannot be read.
        """
        if not self._path.is_file():
            return None

        try:
            if self._path.stat().st_size > self._max_bytes:
                raise StateFormatError(
                    f"State file '{self._path}' exceeds byte cap of {self._max_bytes} bytes "
                    f"({self._path.stat().st_size} bytes)"
                )
        except StateFormatError:
            raise
        except (OSError, AttributeError):
            pass

        try:
            with self._path.open("rb") as handle:
                raw_bytes = handle.read(self._max_bytes + 1)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise StateFormatError(f"Cannot read state file '{self._path}': {exc}") from exc

        if len(raw_bytes) > self._max_bytes:
            raise StateFormatError(
                f"State file '{self._path}' exceeds byte cap of {self._max_bytes} bytes"
            )

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise StateFormatError(f"State file '{self._path}' is not valid UTF-8: {exc}") from exc

        if not text.strip():
            raise StateFormatError(f"State file '{self._path}' is empty or whitespace")

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise StateFormatError(f"State file '{self._path}' contains malformed JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise StateFormatError(
                f"Malformed state file '{self._path}': expected JSON object root, got {type(data).__name__}"
            )

        return data

    def write(self, document: Mapping[str, Any]) -> None:
        """Atomically write the exact supplied document to disk.

        Callers own any merge semantics. Leaves no .tmp file behind on any failure path.

        Args:
            document: Key-value mapping representing the state document to persist.

        Raises:
            TypeError: If document is not a Mapping.
            OSError: If writing or atomic replacement fails.
        """
        if not isinstance(document, Mapping):
            raise TypeError(f"Expected document to be a Mapping, got {type(document).__name__}")

        content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"

        parent = self._path.parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        atomic_write_text(self._path, content)
