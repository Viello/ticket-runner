"""Model selection prompt adapter rendering interactive plain-text menu."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import sys

from runner.domain.config import ModelEntry
from runner.domain.exceptions import NonInteractiveError


def _default_read_key() -> str:
    """Read a single raw key from console; raises NonInteractiveError if unavailable."""
    if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        raise NonInteractiveError(
            "Cannot prompt for model selection: stdin is not interactive; "
            "specify model with --model"
        )
    try:
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()  # Consume multi-byte prefix
            return ""
        return ch
    except (ImportError, AttributeError, OSError, ValueError) as exc:
        raise NonInteractiveError(
            "Cannot prompt for model selection: raw console input is unavailable; "
            "specify model with --model"
        ) from exc


class ModelPrompt:
    """Renders plain-text model menu and reads raw keystrokes to select a model."""

    def __init__(
        self,
        read_key: Callable[[], str] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._read_key = read_key if read_key is not None else _default_read_key
        self._output_fn = output_fn if output_fn is not None else print

    def render_menu(self, models: Sequence[ModelEntry]) -> str:
        """Render the plain-text menu lines according to Spec 07 format."""
        max_label_len = max((len(m.label) for m in models), default=0)
        lines = ["Select model for this session:"]
        for index, model in enumerate(models, start=1):
            lines.append(f"  [{index}] {model.label.ljust(max_label_len)}    ({model.id})")
        lines.append("> _")
        return "\n".join(lines)

    def select_model(self, models: Sequence[ModelEntry]) -> ModelEntry | None:
        """Present menu and loop reading keys until a valid model is confirmed.

        - 0 models: returns None silently.
        - 1 model: auto-selects silently without prompting.
        - >1 models: prints menu, reads keys until digit selects and Enter confirms.
        """
        if not models:
            return None
        if len(models) == 1:
            return models[0]

        menu = self.render_menu(models)
        self._output_fn(menu)

        selected_entry: ModelEntry | None = None
        while True:
            try:
                key = self._read_key()
            except (OSError, EOFError) as exc:
                raise NonInteractiveError(
                    "Cannot prompt for model selection: stdin is not interactive; "
                    "specify model with --model"
                ) from exc

            if not key:
                raise NonInteractiveError(
                    "Cannot prompt for model selection: stdin is not interactive; "
                    "specify model with --model"
                )

            if key in ("\r", "\n"):
                if selected_entry is not None:
                    return selected_entry
                continue

            if key.isdigit():
                idx = int(key)
                if 1 <= idx <= len(models):
                    selected_entry = models[idx - 1]
                    continue

            selected_entry = None
            continue
