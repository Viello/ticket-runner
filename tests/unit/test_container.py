"""Unit tests for container composition root (build_container)."""

from pathlib import Path
import pytest

from runner.container import build_container
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    ModelConfig,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)


def _make_config(default_reasoning: str = "") -> RunnerConfig:
    return RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
        model=ModelConfig(default_reasoning=default_reasoning),
    )


def test_build_container_wires_default_reasoning(tmp_path: Path) -> None:
    config = _make_config(default_reasoning="high")
    container = build_container(config=config, cwd=tmp_path)

    assert container.supervisor.default_reasoning == "high"


def test_build_container_default_reasoning_empty_by_default(tmp_path: Path) -> None:
    config = _make_config()
    container = build_container(config=config, cwd=tmp_path)

    assert container.supervisor.default_reasoning == ""


def test_build_container_wires_model_id(tmp_path: Path) -> None:
    config = _make_config()
    container = build_container(config=config, cwd=tmp_path, model_id="qwen/qwen-plus")

    assert container.supervisor.model_id == "qwen/qwen-plus"


def test_build_container_model_id_none_by_default(tmp_path: Path) -> None:
    config = _make_config()
    container = build_container(config=config, cwd=tmp_path)

    assert container.supervisor.model_id is None

