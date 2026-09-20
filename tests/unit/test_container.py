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
    UIConfig,
    VerificationConfig,
    WorkerConfig,
)


def _make_config(default_reasoning: str = "", ui: UIConfig | None = None) -> RunnerConfig:
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
        ui=ui or UIConfig(),
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


def test_build_container_wires_state_coordinator(tmp_path: Path) -> None:
    config = _make_config()
    container = build_container(config=config, cwd=tmp_path, model_id="qwen/qwen-plus")

    assert container.state_coordinator is not None
    assert container.state_store is not None
    assert container.orchestrator.state_coordinator is container.state_coordinator
    assert container.supervisor.state_coordinator is container.state_coordinator
    assert container.processor.state_coordinator is container.state_coordinator


def test_build_container_resolves_auto_session_terminal(tmp_path: Path) -> None:
    config = _make_config(ui=UIConfig(session_terminal="auto"))
    container = build_container(
        config=config,
        cwd=tmp_path,
        terminal_detector=lambda **kw: "pwsh.exe",
    )

    assert container.tui_coordinator is not None
    assert container.tui_coordinator.terminal_host == "pwsh.exe"
    assert container.tui_coordinator.terminal_host != "auto"


def test_build_container_preserves_explicit_session_terminal(tmp_path: Path) -> None:
    config = _make_config(ui=UIConfig(session_terminal="powershell.exe"))
    container = build_container(config=config, cwd=tmp_path)

    assert container.tui_coordinator is not None
    assert container.tui_coordinator.terminal_host == "powershell.exe"


def test_build_container_auto_session_terminal_fallback_when_unresolved(tmp_path: Path) -> None:
    config = _make_config(ui=UIConfig(session_terminal="auto"))
    container = build_container(
        config=config,
        cwd=tmp_path,
        terminal_detector=lambda **kw: None,
    )

    assert container.tui_coordinator is not None
    assert container.tui_coordinator.terminal_host == "wt.exe"


