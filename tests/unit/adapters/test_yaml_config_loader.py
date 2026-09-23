"""Unit tests for YamlConfigLoader adapter."""

from pathlib import Path
import pytest

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.domain.config import ModelConfig, ModelEntry, RunnerConfig, UIConfig
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
    assert config.lifecycle.poll_interval == 5.0
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
    assert config.verification.silence_window_seconds == 60
    assert config.verification.per_test_timeout_seconds == 0
    assert config.verification.isolation_cmd == ""
    assert config.verification.bug_escalation_at == 1
    assert config.presence.idle_escalation_minutes == 3
    assert config.discord.enabled is True
    assert config.discord.channel_id == ""
    assert config.lifecycle.queue_completion == "standby"
    assert config.lifecycle.clean_slate == "interactive"
    assert config.lifecycle.poll_interval == 5.0
    assert config.git.auto_push is False
    assert config.git.commit_prefix == "feat"
    assert config.git.enforce_pre_push_hook is True
    assert config.worker.provider == "opencode"


def test_load_worker_provider_honored() -> None:
    yaml_content = VALID_CONFIG_YAML.replace(
        '  execution_skill: ".agents/skills/implement/SKILL.md"',
        '  execution_skill: ".agents/skills/implement/SKILL.md"\n  provider: "antigravity"',
    )
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_content)
    assert config.worker.provider == "antigravity"

    dumped = loader.dump(config)
    reloaded = loader.load_from_string(dumped)
    assert reloaded.worker.provider == "antigravity"


@pytest.mark.parametrize(
    "invalid_provider",
    ["unsupported", "claude", "", 123, True],
)
def test_load_worker_provider_invalid(invalid_provider: object) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["worker"]["provider"] = invalid_provider

    with pytest.raises(ConfigError, match="provider"):
        loader.load_from_dict(data)



def test_load_lifecycle_poll_interval_honored() -> None:
    yaml_content = VALID_CONFIG_YAML.replace(
        '  clean_slate: "interactive"',
        '  clean_slate: "interactive"\n  poll_interval: 2.5',
    )
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_content)
    assert config.lifecycle.poll_interval == 2.5


@pytest.mark.parametrize(
    "invalid_poll_interval",
    [-1, 0, 0.0, -0.5, "fast", None, True],
)
def test_load_lifecycle_poll_interval_invalid(invalid_poll_interval: object) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["lifecycle"]["poll_interval"] = invalid_poll_interval

    with pytest.raises(ConfigError, match="poll_interval"):
        loader.load_from_dict(data)


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


def test_load_verification_custom_values() -> None:
    yaml_custom_verification = VALID_CONFIG_YAML + """
verification:
  test_cmd: "pytest"
  build_cmd: "make build"
  max_attempts: 5
  timeout_seconds: 600
  silence_window_seconds: 90
  per_test_timeout_seconds: 15
  isolation_cmd: "pytest {test_id} -x"
  bug_escalation_at: 2
"""
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_custom_verification)
    assert config.verification.silence_window_seconds == 90
    assert config.verification.per_test_timeout_seconds == 15
    assert config.verification.isolation_cmd == "pytest {test_id} -x"
    assert config.verification.bug_escalation_at == 2


@pytest.mark.parametrize(
    ("invalid_override", "expected_match"),
    [
        ({"silence_window_seconds": 0}, "silence_window_seconds"),
        ({"silence_window_seconds": -1}, "silence_window_seconds"),
        ({"silence_window_seconds": "invalid"}, "silence_window_seconds"),
        ({"per_test_timeout_seconds": -1}, "per_test_timeout_seconds"),
        ({"per_test_timeout_seconds": "invalid"}, "per_test_timeout_seconds"),
        ({"bug_escalation_at": -2}, "bug_escalation_at"),
        ({"bug_escalation_at": "invalid"}, "bug_escalation_at"),
        ({"isolation_cmd": 123}, "isolation_cmd"),
    ],
)
def test_load_verification_invalid_fields(invalid_override: dict[str, object], expected_match: str) -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["verification"].update(invalid_override)

    with pytest.raises(ConfigError, match=expected_match):
        loader.load_from_dict(data)


def test_verification_dump_round_trip() -> None:
    yaml_custom = VALID_CONFIG_YAML + """
verification:
  test_cmd: "pytest"
  build_cmd: ""
  max_attempts: 3
  timeout_seconds: 300
  silence_window_seconds: 45
  per_test_timeout_seconds: 10
  isolation_cmd: "python -m pytest {test_id}"
  bug_escalation_at: -1
"""
    loader = YamlConfigLoader()
    config1 = loader.load_from_string(yaml_custom)
    dumped = loader.dump(config1)
    config2 = loader.load_from_string(dumped)

    assert config1.verification == config2.verification
    assert config2.verification.silence_window_seconds == 45
    assert config2.verification.per_test_timeout_seconds == 10
    assert config2.verification.isolation_cmd == "python -m pytest {test_id}"
    assert config2.verification.bug_escalation_at == -1


def test_load_config_example_yaml() -> None:
    loader = YamlConfigLoader()
    example_path = Path("config.example.yaml")
    config = loader.load(example_path)

    assert isinstance(config, RunnerConfig)
    assert config.project.name == "ticket-runner"
    assert config.project.branch == "agent/ticket-runner"
    assert config.worker.execution_skill == ".agents/skills/implement/SKILL.md"
    assert config.verification.test_cmd == "python -m pytest"
    assert config.verification.silence_window_seconds == 60
    assert config.verification.per_test_timeout_seconds == 0
    assert config.verification.isolation_cmd == ""
    assert config.verification.bug_escalation_at == 1
    assert config.tokens.warn == 120000
    assert config.tokens.handoff == 135000
    assert config.tokens.ceiling == 150000
    assert config.lifecycle.poll_interval == 5.0


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


def test_load_discord_snowflakes_valid() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["guild_id"] = "123456789012345678"
    data["discord"]["notify_user_id"] = "987654321098765432"

    config = loader.load_from_dict(data)
    assert config.discord.guild_id == "123456789012345678"
    assert config.discord.notify_user_id == "987654321098765432"


def test_load_discord_snowflakes_numeric_as_int() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["guild_id"] = 123456789012345678
    data["discord"]["notify_user_id"] = 987654321098765432

    config = loader.load_from_dict(data)
    assert config.discord.guild_id == "123456789012345678"
    assert config.discord.notify_user_id == "987654321098765432"


def test_load_discord_invalid_guild_id() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["guild_id"] = "not-a-snowflake"

    with pytest.raises(ConfigError, match="guild_id"):
        loader.load_from_dict(data)


def test_load_discord_invalid_notify_user_id() -> None:
    loader = YamlConfigLoader()
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["notify_user_id"] = "bad!"

    with pytest.raises(ConfigError, match="notify_user_id"):
        loader.load_from_dict(data)


def test_discord_snowflakes_round_trip() -> None:
    loader = YamlConfigLoader()
    yaml_text = VALID_CONFIG_YAML + """
discord:
  enabled: true
  token_env: "DISCORD_BOT_TOKEN"
  channel_id: "987654321"
  guild_id: "123456789012345678"
  notify_user_id: "987654321098765432"
"""
    # Note: yaml safe_load with duplicate key 'discord' will take the last one or load_from_dict
    import yaml
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["discord"]["guild_id"] = "123456789012345678"
    data["discord"]["notify_user_id"] = "987654321098765432"
    config1 = loader.load_from_dict(data)
    dumped = loader.dump(config1)
    config2 = loader.load_from_string(dumped)

    assert config2.discord.guild_id == "123456789012345678"
    assert config2.discord.notify_user_id == "987654321098765432"
    assert config1 == config2


def test_load_config_without_model_section_defaults() -> None:
    loader = YamlConfigLoader()
    config = loader.load_from_string(VALID_CONFIG_YAML)
    assert isinstance(config.model, ModelConfig)
    assert config.model.models == ()
    assert config.model.default_reasoning == ""


def test_load_config_with_valid_model_section() -> None:
    yaml_with_model = VALID_CONFIG_YAML + """
model:
  default_reasoning: "medium"
  models:
    - id: "deepseek/deepseek-chat"
      label: "DeepSeek Chat"
    - id: "qwen/qwen-plus"
      label: "Qwen Plus"
"""
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_with_model)
    assert config.model.default_reasoning == "medium"
    assert len(config.model.models) == 2
    assert config.model.models[0] == ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat")
    assert config.model.models[1] == ModelEntry(id="qwen/qwen-plus", label="Qwen Plus")


def test_load_config_example_yaml_model_section() -> None:
    example_path = Path("config.example.yaml")
    loader = YamlConfigLoader()
    config = loader.load(example_path)
    assert len(config.model.models) == 2
    assert config.model.models[0] == ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat")
    assert config.model.models[1] == ModelEntry(id="qwen/qwen-plus", label="Qwen Plus")
    assert config.model.default_reasoning == ""


def test_load_model_section_null() -> None:
    yaml_null_model = VALID_CONFIG_YAML + "\nmodel: null\n"
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_null_model)
    assert config.model == ModelConfig()


def test_load_model_section_not_dict() -> None:
    yaml_invalid_model = VALID_CONFIG_YAML + "\nmodel: 'not a mapping'\n"
    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Section 'model' must be a mapping"):
        loader.load_from_string(yaml_invalid_model)


def test_load_model_models_not_list() -> None:
    yaml_invalid = VALID_CONFIG_YAML + """
model:
  models: "not-a-list"
"""
    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Field 'models' in section 'model' must be a list"):
        loader.load_from_string(yaml_invalid)


def test_load_model_models_entry_not_dict() -> None:
    yaml_invalid = VALID_CONFIG_YAML + """
model:
  models:
    - "just-a-string"
"""
    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="must be a mapping"):
        loader.load_from_string(yaml_invalid)


@pytest.mark.parametrize(
    "bad_entry",
    [
        {"label": "No ID"},
        {"id": "", "label": "Empty ID"},
        {"id": "   ", "label": "Whitespace ID"},
    ],
)
def test_load_model_models_invalid_id(bad_entry: dict[str, str]) -> None:
    import yaml
    loader = YamlConfigLoader()
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["model"] = {"models": [bad_entry]}
    with pytest.raises(ConfigError):
        loader.load_from_dict(data)


@pytest.mark.parametrize(
    "bad_entry",
    [
        {"id": "valid/id"},
        {"id": "valid/id", "label": ""},
        {"id": "valid/id", "label": "   "},
    ],
)
def test_load_model_models_invalid_label(bad_entry: dict[str, str]) -> None:
    import yaml
    loader = YamlConfigLoader()
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["model"] = {"models": [bad_entry]}
    with pytest.raises(ConfigError):
        loader.load_from_dict(data)


def test_load_model_models_duplicate_id() -> None:
    import yaml
    loader = YamlConfigLoader()
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["model"] = {
        "models": [
            {"id": "provider/model", "label": "Model 1"},
            {"id": "provider/model", "label": "Model 2"},
        ]
    }
    with pytest.raises(ConfigError, match="Duplicate model id"):
        loader.load_from_dict(data)


def test_load_model_default_reasoning_null() -> None:
    yaml_content = VALID_CONFIG_YAML + """
model:
  default_reasoning:
  models:
    - id: "deepseek/chat"
      label: "DeepSeek Chat"
"""
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_content)
    assert config.model.default_reasoning == ""


@pytest.mark.parametrize("invalid_reasoning", [123, True, ["low"]])
def test_load_model_default_reasoning_invalid(invalid_reasoning: object) -> None:
    import yaml
    loader = YamlConfigLoader()
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["model"] = {"default_reasoning": invalid_reasoning}
    with pytest.raises(ConfigError, match="default_reasoning"):
        loader.load_from_dict(data)


def test_load_config_without_ui_section_defaults() -> None:
    loader = YamlConfigLoader()
    config = loader.load_from_string(VALID_CONFIG_YAML)
    assert isinstance(config.ui, UIConfig)
    assert config.ui.session_terminal == ""


def test_load_config_with_valid_ui_section() -> None:
    yaml_with_ui = VALID_CONFIG_YAML + """
ui:
  session_terminal: "wt.exe"
"""
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_with_ui)
    assert isinstance(config.ui, UIConfig)
    assert config.ui.session_terminal == "wt.exe"


def test_load_ui_section_null() -> None:
    yaml_null_ui = VALID_CONFIG_YAML + "\nui: null\n"
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_null_ui)
    assert config.ui == UIConfig(session_terminal="")


def test_load_ui_section_not_dict() -> None:
    yaml_invalid_ui = VALID_CONFIG_YAML + "\nui: 'not a mapping'\n"
    loader = YamlConfigLoader()
    with pytest.raises(ConfigError, match="Section 'ui' must be a mapping"):
        loader.load_from_string(yaml_invalid_ui)


@pytest.mark.parametrize("invalid_terminal", [123, True, ["wt.exe"]])
def test_load_ui_session_terminal_invalid(invalid_terminal: object) -> None:
    import yaml
    loader = YamlConfigLoader()
    data = yaml.safe_load(VALID_CONFIG_YAML)
    data["ui"] = {"session_terminal": invalid_terminal}
    with pytest.raises(ConfigError, match="session_terminal"):
        loader.load_from_dict(data)


def test_config_dump_and_round_trip() -> None:
    loader = YamlConfigLoader()
    original_yaml = VALID_CONFIG_YAML + """
model:
  default_reasoning: ""
  models:
    - id: "deepseek/deepseek-chat"
      label: "DeepSeek Chat"
ui:
  session_terminal: "wt.exe"
"""
    config1 = loader.load_from_string(original_yaml)
    dumped = loader.dump(config1)
    config2 = loader.load_from_string(dumped)

    assert config1.ui.session_terminal == "wt.exe"
    assert config2.ui.session_terminal == "wt.exe"
    assert config1 == config2


def test_persist_session_terminal_appends_to_config_preserving_content(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    initial_content = "# Comment at top\n" + VALID_CONFIG_YAML + "\n# Comment at bottom\n"
    config_file.write_text(initial_content, encoding="utf-8")

    loader = YamlConfigLoader()
    loader.persist_session_terminal(config_file, "pwsh.exe")

    updated_text = config_file.read_text(encoding="utf-8")
    assert "# Comment at top" in updated_text
    assert "# Comment at bottom" in updated_text
    assert "token_env: \"DISCORD_BOT_TOKEN\"" in updated_text
    assert 'session_terminal: "pwsh.exe"' in updated_text

    # Verify that the file loads cleanly as a valid RunnerConfig
    loaded = loader.load(config_file)
    assert loaded.ui.session_terminal == "pwsh.exe"


def test_persist_session_terminal_updates_existing_ui_block(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    initial_content = (
        VALID_CONFIG_YAML
        + "\nui:\n  # Terminal host comment\n  session_terminal: \"old_term.exe\"\n"
    )
    config_file.write_text(initial_content, encoding="utf-8")

    loader = YamlConfigLoader()
    loader.persist_session_terminal(config_file, "wt.exe")

    updated_text = config_file.read_text(encoding="utf-8")
    assert "old_term.exe" not in updated_text
    assert 'session_terminal: "wt.exe"' in updated_text

    loaded = loader.load(config_file)
    assert loaded.ui.session_terminal == "wt.exe"


def test_load_config_with_auto_session_terminal() -> None:
    yaml_with_auto = VALID_CONFIG_YAML + """
ui:
  session_terminal: "auto"
"""
    loader = YamlConfigLoader()
    config = loader.load_from_string(yaml_with_auto)
    assert isinstance(config.ui, UIConfig)
    assert config.ui.session_terminal == "auto"


def test_config_dump_and_round_trip_with_auto() -> None:
    loader = YamlConfigLoader()
    yaml_with_auto = VALID_CONFIG_YAML + """
ui:
  session_terminal: "auto"
"""
    config1 = loader.load_from_string(yaml_with_auto)
    dumped = loader.dump(config1)
    config2 = loader.load_from_string(dumped)

    assert config1.ui.session_terminal == "auto"
    assert config2.ui.session_terminal == "auto"
    assert config1 == config2


def test_persist_session_terminal_updates_auto_to_concrete_host(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    initial_content = (
        VALID_CONFIG_YAML
        + "\nui:\n  # Auto detection comment\n  session_terminal: \"auto\"\n"
    )
    config_file.write_text(initial_content, encoding="utf-8")

    loader = YamlConfigLoader()
    loader.persist_session_terminal(config_file, "pwsh.exe")

    updated_text = config_file.read_text(encoding="utf-8")
    assert '"auto"' not in updated_text
    assert 'session_terminal: "pwsh.exe"' in updated_text

    loaded = loader.load(config_file)
    assert loaded.ui.session_terminal == "pwsh.exe"


