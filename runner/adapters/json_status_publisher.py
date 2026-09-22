"""JsonFileStatusPublisher adapter persisting StatusEvent to .agent/status.json atomically (T067)."""

from __future__ import annotations

import json
from pathlib import Path

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.status_event import StatusEvent
from runner.ports.status_publisher import StatusPublisher


class JsonFileStatusPublisher(StatusPublisher):
    """Binds the StatusPublisher port to a status.json file via atomic replacement."""

    def __init__(self, target: RuntimePaths | Path | str | None = None) -> None:
        if isinstance(target, RuntimePaths):
            self._path = target.status_file
        elif isinstance(target, (Path, str)):
            self._path = Path(target)
        elif target is None:
            self._path = RuntimePaths().status_file
        else:
            raise TypeError(
                f"Expected RuntimePaths, Path, str, or None, got {type(target).__name__}"
            )

    @property
    def path(self) -> Path:
        """Return the target status file path."""
        return self._path

    def publish(self, event: StatusEvent) -> None:
        """Atomically persist the status event to disk as formatted JSON."""
        doc = event.to_dict()
        content = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"

        parent = self._path.parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)

        atomic_write_text(self._path, content)
