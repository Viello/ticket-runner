"""Unit tests for ModelSelectionInteractor."""

from __future__ import annotations

from typing import Any
import pytest

from runner.application.model_selection import ModelSelectionInteractor
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    ModelConfig,
    ModelEntry,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.exceptions import ConfigError, NonInteractiveError, StateFormatError
from tests.fakes.fake_state_store import FakeStateStore


def _make_config(
    models: tuple[ModelEntry, ...] = (
        ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),
        ModelEntry(id="qwen/qwen-plus", label="Qwen Plus"),
    )
) -> RunnerConfig:
    return RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
        model=ModelConfig(models=models),
    )


class FakePrompt:
    def __init__(self, return_entry: ModelEntry | None = None) -> None:
        self.return_entry = return_entry
        self.called = False
        self.received_models: Any = None

    def select_model(self, models: Any) -> ModelEntry | None:
        self.called = True
        self.received_models = models
        return self.return_entry


def test_explicit_model_flag_resolves_and_persists_without_prompting() -> None:
    config = _make_config()
    store = FakeStateStore(initial_state={"other_key": "preserved"})
    fake_prompt = FakePrompt()
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        prompt=fake_prompt,  # type: ignore[arg-type]
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model="qwen/qwen-plus")

    assert resolved == "qwen/qwen-plus"
    assert fake_prompt.called is False
    assert len(store.write_calls) == 1
    assert store.write_calls[0] == {
        "other_key": "preserved",
        "selected_model": "qwen/qwen-plus",
    }
    assert not any("Resuming with" in line for line in output)


def test_explicit_model_flag_invalid_raises_config_error() -> None:
    config = _make_config()
    store = FakeStateStore()
    interactor = ModelSelectionInteractor(config=config, state_store=store)

    with pytest.raises(ConfigError) as exc_info:
        interactor.resolve_and_persist(cli_model="unknown-model")
    assert "unknown-model" in str(exc_info.value).lower()


def test_restore_configured_model_prints_notice_skips_prompt() -> None:
    config = _make_config()
    store = FakeStateStore(initial_state={"selected_model": "qwen/qwen-plus", "session": 1})
    fake_prompt = FakePrompt()
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        prompt=fake_prompt,  # type: ignore[arg-type]
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved == "qwen/qwen-plus"
    assert fake_prompt.called is False
    assert any("Resuming with Qwen Plus — pass --model to override" == line for line in output)
    # Check that state preserves session: 1
    assert store.write_calls[-1]["session"] == 1
    assert store.write_calls[-1]["selected_model"] == "qwen/qwen-plus"


def test_drift_model_warns_and_falls_through_to_single_model() -> None:
    single_model = (ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),)
    config = _make_config(models=single_model)
    store = FakeStateStore(initial_state={"selected_model": "old/departed-model"})
    fake_prompt = FakePrompt()
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        prompt=fake_prompt,  # type: ignore[arg-type]
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved == "deepseek/deepseek-chat"
    assert fake_prompt.called is False
    assert any("old/departed-model" in line for line in output)
    assert any("unavailable" in line.lower() or "no longer configured" in line.lower() for line in output)
    assert store.write_calls[-1]["selected_model"] == "deepseek/deepseek-chat"


def test_drift_model_warns_and_falls_through_to_prompt() -> None:
    config = _make_config()
    store = FakeStateStore(initial_state={"selected_model": "old/departed-model"})
    fake_prompt = FakePrompt(return_entry=config.model.models[1])
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        prompt=fake_prompt,  # type: ignore[arg-type]
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved == "qwen/qwen-plus"
    assert fake_prompt.called is True
    assert store.write_calls[-1]["selected_model"] == "qwen/qwen-plus"


def test_zero_configured_models_resolves_silently_to_none_without_write() -> None:
    config = _make_config(models=())
    store = FakeStateStore()
    fake_prompt = FakePrompt()
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        prompt=fake_prompt,  # type: ignore[arg-type]
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved is None
    assert fake_prompt.called is False
    assert store.write_calls == []
    assert output == []


def test_single_configured_model_auto_selects_silently_and_persists() -> None:
    single_model = (ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),)
    config = _make_config(models=single_model)
    store = FakeStateStore()
    fake_prompt = FakePrompt()
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        prompt=fake_prompt,  # type: ignore[arg-type]
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved == "deepseek/deepseek-chat"
    assert fake_prompt.called is False
    assert output == []
    assert store.write_calls == [{"selected_model": "deepseek/deepseek-chat"}]


def test_corrupt_state_document_warns_and_treats_as_empty() -> None:
    single_model = (ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),)
    config = _make_config(models=single_model)
    store = FakeStateStore(read_error=StateFormatError("Corrupted state JSON"))
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        printer=output.append,
    )

    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved == "deepseek/deepseek-chat"
    assert any("corrupt" in line.lower() for line in output)
    assert store.write_calls == [{"selected_model": "deepseek/deepseek-chat"}]


def test_write_failure_propagates_and_prints_actionable_error() -> None:
    config = _make_config()
    store = FakeStateStore(write_error=OSError("Disk full"))
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        printer=output.append,
    )

    with pytest.raises(OSError):
        interactor.resolve_and_persist(cli_model="qwen/qwen-plus")

    assert any("failed to write" in line.lower() or "disk full" in line.lower() for line in output)
