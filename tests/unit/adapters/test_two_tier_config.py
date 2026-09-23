"""Unit tests for YamlConfigLoader two-tier configuration overlay loading (T101)."""

from __future__ import annotations

from pathlib import Path
import pytest

from runner.adapters.config.yaml_config_loader import (
    DEFAULT_GLOBAL_CONFIG_PATH,
    DEFAULT_MACHINE_CONFIG,
    YamlConfigLoader,
)
from runner.domain.exceptions import ConfigError
from runner.ports.config_loader import ConfigLoader


def test_yaml_config_loader_implements_protocol() -> None:
    loader = YamlConfigLoader()
    assert isinstance(loader, ConfigLoader)
    assert hasattr(loader, "load_two_tier")


def test_load_two_tier_deep_merges_global_and_project_overlay(tmp_path: Path) -> None:
    global_file = tmp_path / "global_config.yaml"
    global_file.write_text(
        """
tokens:
  warn: 90000
  handoff: 100000
  ceiling: 110000
discord:
  enabled: true
  token_env: "GLOBAL_DISCORD_TOKEN"
  channel_id: "123456789"
presence:
  default_mode: "away"
  idle_escalation_minutes: 7
worker:
  provider: "antigravity"
""",
        encoding="utf-8",
    )

    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        """
project:
  name: "my-app"
  base_branch: "develop"
verification:
  test_cmd: "pytest -q"
tokens:
  ceiling: 115000
worker:
  provider: "opencode"
""",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(project_dir=project_dir, global_path=global_file)

    # Project overrides
    assert cfg.project.name == "my-app"
    assert cfg.project.base_branch == "develop"
    assert cfg.project.branch == "agent/ticket-runner"
    assert cfg.verification.test_cmd == "pytest -q"
    assert cfg.tokens.ceiling == 115000
    assert cfg.worker.provider == "opencode"

    # Preserved global values
    assert cfg.tokens.warn == 90000
    assert cfg.tokens.handoff == 100000
    assert cfg.discord.enabled is True
    assert cfg.discord.token_env == "GLOBAL_DISCORD_TOKEN"
    assert cfg.discord.channel_id == "123456789"
    assert cfg.presence.default_mode == "away"
    assert cfg.presence.idle_escalation_minutes == 7

    # Machine defaults
    assert cfg.worker.execution_skill == ".agents/skills/implement/SKILL.md"
    assert cfg.lifecycle.queue_completion == "standby"
    assert cfg.git.auto_push is False


def test_load_two_tier_minimal_project_overlay_under_15_lines(tmp_path: Path) -> None:
    project_dir = tmp_path / "minimal_project"
    project_dir.mkdir()
    overlay_content = """project:
  name: minimal-app
  base_branch: main
verification:
  test_cmd: npm test
"""
    assert len(overlay_content.strip().splitlines()) < 15
    (project_dir / "ticket-runner.yaml").write_text(overlay_content, encoding="utf-8")

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(
        project_dir=project_dir,
        global_path=tmp_path / "nonexistent_global.yaml",
    )

    assert cfg.project.name == "minimal-app"
    assert cfg.project.branch == "agent/ticket-runner"
    assert cfg.project.base_branch == "main"
    assert cfg.verification.test_cmd == "npm test"
    assert cfg.tokens.warn == 120000
    assert cfg.tokens.handoff == 135000
    assert cfg.tokens.ceiling == 150000
    assert cfg.presence.default_mode == "nearby"
    assert cfg.presence.idle_escalation_minutes == 3
    assert cfg.discord.enabled is False
    assert cfg.discord.token_env == "DISCORD_BOT_TOKEN"
    assert cfg.lifecycle.queue_completion == "standby"
    assert cfg.lifecycle.clean_slate == "interactive"
    assert cfg.git.auto_push is False
    assert cfg.worker.provider == "opencode"
    assert cfg.worker.execution_skill == ".agents/skills/implement/SKILL.md"


def test_load_two_tier_missing_global_file_fallback(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        """
project:
  name: test-app
  base_branch: main
verification:
  test_cmd: pytest
""",
        encoding="utf-8",
    )

    missing_global = tmp_path / "does_not_exist.yaml"
    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(project_dir=project_dir, global_path=missing_global)

    assert cfg.project.name == "test-app"
    assert cfg.tokens.ceiling == 150000
    assert cfg.discord.enabled is False


def test_load_two_tier_missing_project_file_handling(tmp_path: Path) -> None:
    empty_project_dir = tmp_path / "empty_project"
    empty_project_dir.mkdir()

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Project configuration file not found"):
        loader.load_two_tier(project_dir=empty_project_dir)


def test_load_two_tier_backward_compatible_config_yaml_fallback(tmp_path: Path) -> None:
    project_dir = tmp_path / "legacy_project"
    project_dir.mkdir()
    (project_dir / "config.yaml").write_text(
        """
project:
  name: legacy-app
  base_branch: main
verification:
  test_cmd: pytest -v
""",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(
        project_dir=project_dir,
        global_path=tmp_path / "nonexistent_global.yaml",
    )

    assert cfg.project.name == "legacy-app"
    assert cfg.verification.test_cmd == "pytest -v"


def test_load_two_tier_ticket_runner_yaml_precedence_over_config_yaml(tmp_path: Path) -> None:
    project_dir = tmp_path / "dual_config_project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        """
project:
  name: primary-app
  base_branch: main
verification:
  test_cmd: pytest primary
""",
        encoding="utf-8",
    )
    (project_dir / "config.yaml").write_text(
        """
project:
  name: secondary-app
  base_branch: main
verification:
  test_cmd: pytest secondary
""",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(
        project_dir=project_dir,
        global_path=tmp_path / "nonexistent_global.yaml",
    )

    assert cfg.project.name == "primary-app"
    assert cfg.verification.test_cmd == "pytest primary"


def test_load_two_tier_explicit_project_config_path(tmp_path: Path) -> None:
    project_dir = tmp_path / "explicit_project"
    project_dir.mkdir()
    (project_dir / "custom.yaml").write_text(
        """
project:
  name: custom-app
  base_branch: main
verification:
  test_cmd: custom test
""",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(
        project_dir=project_dir,
        project_config_path="custom.yaml",
        global_path=tmp_path / "nonexistent_global.yaml",
    )

    assert cfg.project.name == "custom-app"
    assert cfg.verification.test_cmd == "custom test"


def test_load_two_tier_explicit_project_config_path_missing(tmp_path: Path) -> None:
    project_dir = tmp_path / "explicit_missing_project"
    project_dir.mkdir()

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Project configuration file not found"):
        loader.load_two_tier(
            project_dir=project_dir,
            project_config_path="missing.yaml",
            global_path=tmp_path / "nonexistent_global.yaml",
        )


def test_load_two_tier_deep_merge_list_replacement_not_append(tmp_path: Path) -> None:
    global_file = tmp_path / "global_models.yaml"
    global_file.write_text(
        """
model:
  default_reasoning: "low"
  models:
    - id: "global-1"
      label: "Global 1"
    - id: "global-2"
      label: "Global 2"
""",
        encoding="utf-8",
    )

    project_dir = tmp_path / "models_project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        """
project:
  name: models-app
  base_branch: main
verification:
  test_cmd: pytest
model:
  models:
    - id: "project-1"
      label: "Project 1"
""",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(project_dir=project_dir, global_path=global_file)

    assert cfg.model.default_reasoning == "low"
    assert len(cfg.model.models) == 1
    assert cfg.model.models[0].id == "project-1"
    assert cfg.model.models[0].label == "Project 1"


def test_security_path_traversal_project_config_escaping_project_dir(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    outside_file = tmp_path / "secret.yaml"
    outside_file.write_text("evil: true\n", encoding="utf-8")

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Path traversal detected"):
        loader.load_two_tier(
            project_dir=project_dir,
            project_config_path="../secret.yaml",
            global_path=tmp_path / "nonexistent.yaml",
        )


def test_security_path_traversal_global_path_escaping(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        "project:\n  name: p\n  base_branch: m\nverification:\n  test_cmd: t\n",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Path traversal detected"):
        loader.load_two_tier(
            project_dir=project_dir,
            global_path="../../etc/shadow",
        )


def test_security_null_byte_rejection(tmp_path: Path) -> None:
    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="null byte"):
        loader.load_two_tier(project_dir=f"{tmp_path}\0evil")

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        "project:\n  name: p\n  base_branch: m\nverification:\n  test_cmd: t\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="null byte"):
        loader.load_two_tier(project_dir=project_dir, global_path="global\0evil")

    with pytest.raises(ConfigError, match="null byte"):
        loader.load_two_tier(project_dir=project_dir, project_config_path="cfg\0evil")


def test_security_project_dir_must_exist_and_be_directory(tmp_path: Path) -> None:
    loader = YamlConfigLoader()
    nonexistent = tmp_path / "nonexistent_dir"
    with pytest.raises(ConfigError, match="Project directory not found"):
        loader.load_two_tier(project_dir=nonexistent)

    regular_file = tmp_path / "regular_file.txt"
    regular_file.write_text("hello", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a directory"):
        loader.load_two_tier(project_dir=regular_file)


def test_security_global_path_cannot_be_directory(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        "project:\n  name: p\n  base_branch: m\nverification:\n  test_cmd: t\n",
        encoding="utf-8",
    )

    global_dir = tmp_path / "global_dir"
    global_dir.mkdir()

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="directory"):
        loader.load_two_tier(project_dir=project_dir, global_path=global_dir)


def test_security_forbidden_discord_tokens_rejected_in_two_tier(tmp_path: Path) -> None:
    global_file = tmp_path / "global_with_secret.yaml"
    global_file.write_text(
        """
discord:
  token: "my-secret-bot-token"
""",
        encoding="utf-8",
    )

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "ticket-runner.yaml").write_text(
        "project:\n  name: p\n  base_branch: m\nverification:\n  test_cmd: t\n",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Raw credential detected in discord configuration"):
        loader.load_two_tier(project_dir=project_dir, global_path=global_file)


def test_smoke_scenario_repro(tmp_path: Path) -> None:
    td = tmp_path / "smoke_project"
    td.mkdir()
    (td / "ticket-runner.yaml").write_text(
        "project:\n  name: demo\n  branch: agent/ticket-runner\n  base_branch: main\n"
        "verification:\n  test_cmd: pytest -v\n",
        encoding="utf-8",
    )
    cfg = YamlConfigLoader().load_two_tier(
        project_dir=td,
        global_path=tmp_path / "nonexistent.yaml",
    )
    assert cfg.project.name == "demo"
    assert cfg.verification.test_cmd == "pytest -v"
    assert cfg.tokens.ceiling == 150000
