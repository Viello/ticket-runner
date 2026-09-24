"""Unit tests for container composition root (build_container)."""

from pathlib import Path
import tempfile
import pytest

from runner.container import build_bot_container, build_container
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


def test_build_container_wires_default_status_publisher(tmp_path: Path) -> None:
    config = _make_config()
    container = build_container(config=config, cwd=tmp_path)

    from runner.adapters.json_status_publisher import JsonFileStatusPublisher
    assert isinstance(container.status_publisher, JsonFileStatusPublisher)
    assert container.status_publisher.path == (tmp_path.resolve() / ".agent" / "status.json")


def test_build_container_allows_status_publisher_override(tmp_path: Path) -> None:
    config = _make_config()
    from tests.fakes.fake_status_publisher import FakeStatusPublisher
    fake_publisher = FakeStatusPublisher()

    container = build_container(
        config=config,
        cwd=tmp_path,
        status_publisher=fake_publisher,
    )

    assert container.status_publisher is fake_publisher


def test_build_container_instantiates_opencode_worker_by_default(tmp_path: Path) -> None:
    from runner.adapters.opencode.opencode_worker import OpenCodeWorker
    config = _make_config()
    container = build_container(config=config, cwd=tmp_path)

    assert isinstance(container.agent_worker, OpenCodeWorker)
    assert isinstance(container.supervisor.agent_worker, OpenCodeWorker)


def test_build_container_instantiates_antigravity_worker_when_configured(tmp_path: Path) -> None:
    from runner.adapters.antigravity.antigravity_worker import AntigravityWorker
    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md", provider="antigravity"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
    )
    container = build_container(config=config, cwd=tmp_path)

    assert isinstance(container.agent_worker, AntigravityWorker)
    assert isinstance(container.supervisor.agent_worker, AntigravityWorker)


def test_build_container_allows_agent_worker_override(tmp_path: Path) -> None:
    from tests.fakes.fake_agent_worker import FakeAgentWorker
    fake = FakeAgentWorker()
    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md", provider="antigravity"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
    )
    container = build_container(config=config, cwd=tmp_path, agent_worker=fake)

    assert container.agent_worker is fake
    assert container.supervisor.agent_worker is fake


def test_build_container_external_project_dir_resolution(tmp_path: Path) -> None:
    target = (tmp_path / "custom_project").resolve()
    target.mkdir(parents=True, exist_ok=True)

    container = build_container(project_dir=target)

    assert container.project_dir == target
    assert container.runtime_paths.root_dir == target / ".agent"
    assert container.ticket_store.root_dir == target / "docs" / "tickets"
    assert container.gotchas_store.path == target / "docs" / "tickets" / "gotchas.md"
    assert container.lock.lock_path == target / "docs" / "tickets" / ".queue.lock"
    assert container.git_operations.cwd == target
    assert container.executor.cwd == target
    assert container.supervisor.cwd == target
    assert container.orchestrator.cwd == target


def test_build_container_relative_project_dir_resolved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    rel_path = Path("subfolder/my_project")
    rel_path.mkdir(parents=True, exist_ok=True)

    container = build_container(project_dir=rel_path)

    expected = rel_path.resolve()
    assert container.project_dir == expected
    assert container.runtime_paths.root_dir == expected / ".agent"
    assert container.ticket_store.root_dir == expected / "docs" / "tickets"
    assert container.gotchas_store.path == expected / "docs" / "tickets" / "gotchas.md"
    assert container.lock.lock_path == expected / "docs" / "tickets" / ".queue.lock"
    assert container.git_operations.cwd == expected
    assert container.executor.cwd == expected
    assert container.supervisor.cwd == expected


def test_build_container_omitted_project_dir_backward_compatible() -> None:
    container = build_container()

    assert container.project_dir is None
    assert container.runtime_paths.root_dir == Path(".agent")
    assert container.ticket_store.root_dir == Path("docs/tickets")
    assert container.gotchas_store.path == Path("docs/tickets/gotchas.md")
    assert container.lock.lock_path == Path("docs/tickets/.queue.lock")
    assert container.git_operations.cwd is None
    assert container.executor.cwd is None
    assert container.supervisor.cwd is None


def test_build_container_cwd_fallback(tmp_path: Path) -> None:
    resolved_tmp = tmp_path.resolve()
    container = build_container(cwd=tmp_path)

    assert container.project_dir == resolved_tmp
    assert container.runtime_paths.root_dir == resolved_tmp / ".agent"
    assert container.ticket_store.root_dir == resolved_tmp / "docs" / "tickets"
    assert container.gotchas_store.path == resolved_tmp / "docs" / "tickets" / "gotchas.md"
    assert container.lock.lock_path == resolved_tmp / "docs" / "tickets" / ".queue.lock"
    assert container.git_operations.cwd == resolved_tmp
    assert container.executor.cwd == resolved_tmp
    assert container.supervisor.cwd == resolved_tmp


def test_build_bot_container_external_project_dir(tmp_path: Path) -> None:
    target = (tmp_path / "bot_project").resolve()
    target.mkdir(parents=True, exist_ok=True)

    bot_container = build_bot_container(project_dir=target)

    assert bot_container.project_dir == target
    assert bot_container.runtime_paths.root_dir == target / ".agent"


def test_build_container_approval_gateway_none_in_autonomous_mode(tmp_path: Path) -> None:
    from tests.fakes.fake_approval_gateway import FakeApprovalGateway

    fake_gw = FakeApprovalGateway()
    container = build_container(cwd=tmp_path, approval_gateway=fake_gw)

    # In autonomous mode (default), approval_gateway is None
    assert container.approval_gateway is None
    assert container.processor._approval_gateway is None


def test_build_container_approval_gateway_wired_in_human_mode(tmp_path: Path) -> None:
    from dataclasses import replace
    from runner.container import _default_config
    from runner.domain.config import LifecycleConfig
    from tests.fakes.fake_approval_gateway import FakeApprovalGateway

    base_cfg = _default_config()
    cfg = replace(base_cfg, lifecycle=LifecycleConfig(approval_mode="human"))
    fake_gw = FakeApprovalGateway()

    container = build_container(config=cfg, cwd=tmp_path, approval_gateway=fake_gw)

    assert container.approval_gateway is fake_gw
    assert container.processor._approval_gateway is fake_gw
    assert container.processor._approval_mode == "human"
