"""Model selection interactor managing startup model resolution and state persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from runner.adapters.ui.model_prompt import ModelPrompt
from runner.domain.config import ModelEntry, RunnerConfig
from runner.domain.exceptions import ConfigError, StateFormatError
from runner.ports.state_store import StateStore


class ModelSelectionInteractor:
    """Application interactor driving startup model selection and persistence.

    Resolves the model for the session according to Spec 07 precedence:
    1. Explicit `--model` CLI flag (validated against configured list).
    2. Persisted `selected_model` from state store (if still configured).
    3. Zero configured models -> None silently.
    4. Exactly one configured model -> auto-select silently.
    5. Multiple configured models -> interactive prompt.
    """

    def __init__(
        self,
        config: RunnerConfig,
        state_store: StateStore,
        prompt: ModelPrompt | None = None,
        printer: Callable[[str], None] | None = None,
    ) -> None:
        self._config = config
        self._state_store = state_store
        self._prompt = prompt or ModelPrompt()
        self._printer = printer or print

    def _read_existing_state(self) -> dict[str, Any]:
        """Read state document safely, warning on corruption and defaulting to empty dict."""
        try:
            document = self._state_store.read()
            if document is None:
                return {}
            return dict(document)
        except StateFormatError as exc:
            self._printer(f"[Runner] Warning: State file is corrupted ({exc}); treating as empty.")
            return {}
        except Exception as exc:
            self._printer(f"[Runner] Warning: Failed to read state ({exc}); treating as empty.")
            return {}

    def resolve(self, cli_model: str | None = None) -> str | None:
        """Resolve model identity according to precedence order without persisting."""
        configured_models = self._config.model.models
        valid_by_id: dict[str, ModelEntry] = {m.id: m for m in configured_models}

        # 1. Explicit CLI flag
        if cli_model is not None:
            if valid_by_id and cli_model not in valid_by_id:
                configured_ids = ", ".join(valid_by_id.keys())
                raise ConfigError(
                    f"Unknown model '{cli_model}'. Configured model IDs: {configured_ids}"
                )
            return cli_model

        # 2. Persisted selection from state store
        existing_state = self._read_existing_state()
        recorded_id = existing_state.get("selected_model")

        if recorded_id is not None:
            if recorded_id in valid_by_id:
                label = valid_by_id[recorded_id].label
                self._printer(f"Resuming with {label} — pass --model to override")
                return recorded_id
            self._printer(
                f"[Runner] Warning: Recorded model '{recorded_id}' is no longer configured and unavailable."
            )

        # 3. Fall-through based on configured models count
        if len(configured_models) == 0:
            return None
        if len(configured_models) == 1:
            return configured_models[0].id

        # Multiple models -> prompt
        selected = self._prompt.select_model(configured_models)
        return selected.id if selected is not None else None

    def resolve_and_persist(self, cli_model: str | None = None) -> str | None:
        """Resolve model identity and persist selected_model to state store."""
        model_id = self.resolve(cli_model=cli_model)
        if model_id is None:
            return None

        # Read existing document to preserve all unrelated keys
        existing_state = self._read_existing_state()
        new_state = dict(existing_state)
        new_state["selected_model"] = model_id

        try:
            self._state_store.write(new_state)
        except Exception as exc:
            self._printer(f"[Runner] Error: Failed to write state: {exc}")
            raise

        return model_id
