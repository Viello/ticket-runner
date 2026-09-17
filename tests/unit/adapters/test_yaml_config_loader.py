"""Unit tests for YamlConfigLoader adapter."""

from pathlib import Path
import pytest

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.domain.config import RunnerConfig
from runner.domain.exceptions import ConfigError
from runner.ports.config_loader import ConfigLoader

VALID_CONFIG_YAML = """
project:
  name: "ticket-runner"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pytest"
  build_cmd: "npm run build"
  max_attempts: 3
  timeout_seconds: 300

tokens:
  warn: 120000
  handoff: 135000
  ceiling: 150000

presence:
  default_mode: "nearby"
  idle_escalation_minutes: 3

discord:
  enabled: true
  token_env: "DISCORD_BOT_TOKEN"
  channel_id: "987654321"

lifecycle:
  queue_completion: "standby"
  clean_slate: "interactive"

git:
  auto_push: false
  commit_prefix: "feat"
  enforce_pre_push_hook: true
"""


def test_implements_config_loader_protocol() -> None:
    loader = YamlConfigLoader()
    assert isinstance(loader, ConfigLoader)


def test_load_valid_yaml_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(VALID_CONFIG_YAML, encoding="utf-8")

    loader = YamlConfigLoader()
    config = loader.load(config_file)

    assert isinstance(config, RunnerConfig)
    assert config.project.name == "ticket-runner"
    assert config.project.branch == "agent/ticket-runner"
    assert config.project.base_branch == "main"
    assert config.worker.execution_skill == ".agents/skills/implement/SKILL.md"
    assert config.verification.test_cmd == "pytest"
    assert config.verification.build_cmd == "npm run build"
    assert config.verification.max_attempts == 3
    assert config.verification.timeout_seconds == 300
    assert config.tokens.warn == 120000
    assert config.tokens.handoff == 135000
    assert config.tokens.ceiling == 150000
    assert config.presence.default_mode == "nearby"
    assert config.presence.idle_escalation_minutes == 3
    assert config.discord.enabled is True
    assert config.discord.token_env == "DISCORD_BOT_TOKEN"
    assert config.discord.channel_id == "987654321"
    assert config.lifecycle.queue_completion == "standby"
    assert config.lifecycle.clean_slate == "interactive"
    assert config.git.auto_push is False
    assert config.git.commit_prefix == "feat"
    assert config.git.enforce_pre_push_hook is True


def test_load_from_string() -> None:
    loader = YamlConfigLoader()
    config = loader.load_from_string(VALID_CONFIG_YAML)
    assert isinstance(config, RunnerConfig)
    assert config.project.name == "ticket-runner"


def test_load_missing_file(tmp_path: Path) -> None:
    loader = YamlConfigLoader()
    missing_file = tmp_path / "non_existent.yaml"
    with pytest.raises(ConfigError, match="not found"):
        loader.load(missing_file)


def test_load_invalid_yaml_syntax(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("project: [unclosed list", encoding="utf-8")

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="YAML parsing error"):
        loader.load(bad_yaml)


def test_load_non_mapping_root(tmp_path: Path) -> None:
    list_yaml = tmp_path / "list.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")

    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Configuration root must be a mapping"):
        loader.load(list_yaml)


@pytest.mark.parametrize(
    "missing_section",
    [
        "project",
        "worker",
        "verification",
        "tokens",
        "presence",
        "discord",
        "lifecycle",
        "git",
    ],
)
def test_load_missing_required_section(missing_section: str) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    del data[missing_section]

    with pytest.raises(ConfigError, match=f"Missing required section: '{missing_section}'"):
        loader.load_from_dict(data)


def test_load_section_not_a_mapping() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["project"] = "not a mapping"

    with pytest.raises(ConfigError, match="Section 'project' must be a mapping"):
        loader.load_from_dict(data)


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("project", "name"),
        ("project", "branch"),
        ("project", "base_branch"),
        ("worker", "execution_skill"),
        ("verification", "test_cmd"),
        ("tokens", "warn"),
        ("tokens", "handoff"),
        ("tokens", "ceiling"),
        ("presence", "default_mode"),
        ("discord", "token_env"),
    ],
)
def test_load_missing_required_field(section: str, field: str) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    del data[section][field]

    with pytest.raises(ConfigError, match=f"Missing required field '{field}' in section '{section}'"):
        loader.load_from_dict(data)


def test_load_defaults_applied() -> None:
    minimal_yaml = """
project:
  name: "ticket-runner"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pytest"

tokens:
  warn: 100000
  handoff: 120000
  ceiling: 140000

presence:
  default_mode: "nearby"

discord:
  token_env: "DISCORD_BOT_TOKEN"

lifecycle: {}

git: {}
"""
    loader = YamlConfigLoader()
    config = loader.load_from_string(minimal_yaml)

    assert config.verification.build_cmd == ""
    assert config.verification.max_attempts == 3
    assert config.verification.timeout_seconds == 300
    assert config.presence.idle_escalation_minutes == 3
    assert config.discord.enabled is True
    assert config.discord.channel_id == ""
    assert config.lifecycle.queue_completion == "standby"
    assert config.lifecycle.clean_slate == "interactive"
    assert config.git.auto_push is False
    assert config.git.commit_prefix == "feat"
    assert config.git.enforce_pre_push_hook is True


def test_load_token_budget_invariant_violation() -> None:
    bad_yaml = VALID_CONFIG_YAML.replace("warn: 120000\n  handoff: 135000", "warn: 140000\n  handoff: 135000")
    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Token budget"):
        loader.load_from_string(bad_yaml)


@pytest.mark.parametrize(
    "forbidden_key",
    ["token", "bot_token", "secret", "api_key"],
)
def test_load_discord_raw_token_keys_forbidden(forbidden_key: str) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"][forbidden_key] = "some-raw-secret"

    with pytest.raises(ConfigError, match="Raw credential detected in discord configuration"):
        loader.load_from_dict(data)


def test_load_discord_raw_token_in_token_env() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["token_env"] = "MTE1MjMzNDQ1.G-secret.dot"

    with pytest.raises(ConfigError, match="Discord token_env must be a valid environment variable name"):
        loader.load_from_dict(data)


def test_load_config_example_yaml() -> None:
    loader = YamlConfigLoader()
    example_path = Path("config.example.yaml")
    config = loader.load(example_path)

    assert isinstance(config, RunnerConfig)
    assert config.project.name == "ticket-runner"
    assert config.project.branch == "agent/ticket-runner"
    assert config.worker.execution_skill == ".agents/skills/implement/SKILL.md"
    assert config.verification.test_cmd == "pytest"
    assert config.tokens.warn == 120000
    assert config.tokens.handoff == 135000
    assert config.tokens.ceiling == 150000


def test_load_root_config_yaml() -> None:
    root_config_path = Path("config.yaml")
    if not root_config_path.is_file():
        pytest.skip("config.yaml is untracked and not present; skipping local config test.")

    loader = YamlConfigLoader()
    config = loader.load(root_config_path)
    example = loader.load(Path("config.example.yaml"))

    assert isinstance(config, RunnerConfig)
    assert config.project.name == example.project.name
    assert config.project.branch == example.project.branch
    assert config.worker.execution_skill == example.worker.execution_skill
    assert config.tokens.warn == example.tokens.warn
    assert config.tokens.handoff == example.tokens.handoff
    assert config.tokens.ceiling == example.tokens.ceiling


@pytest.mark.parametrize(
    "invalid_channel_id",
    ["letters_only", "12345-channel", "token.secret.value", "channel#1"],
)
def test_load_discord_invalid_channel_id(invalid_channel_id: str) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["channel_id"] = invalid_channel_id

    with pytest.raises(ConfigError, match="Field 'channel_id' in section 'discord' must be empty or a valid numeric Discord channel ID"):
        loader.load_from_dict(data)


def test_load_discord_numeric_channel_id_as_int() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["channel_id"] = 123456789012345678

    config = loader.load_from_dict(data)
    assert config.discord.channel_id == "123456789012345678"

