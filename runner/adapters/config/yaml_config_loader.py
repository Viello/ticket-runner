"""PyYAML-based configuration loader adapter."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any
import yaml

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
from runner.domain.exceptions import ConfigError
from runner.ports.config_loader import ConfigLoader

REQUIRED_SECTIONS = (
    "project",
    "worker",
    "verification",
    "tokens",
    "presence",
    "discord",
    "lifecycle",
    "git",
)

FORBIDDEN_DISCORD_CREDENTIAL_KEYS = (
    "token",
    "bot_token",
    "secret",
    "api_key",
    "password",
)

ENV_VAR_PATTERN = re.compile(r"^[A-Z_][A-Z0-9_]*$")
DISCORD_CHANNEL_ID_PATTERN = re.compile(r"^\d+$")


class YamlConfigLoader(ConfigLoader):
    """Loads and validates runner configuration from YAML files or strings."""

    def load(self, path: Path | str) -> RunnerConfig:
        """Load and validate configuration from a YAML file.

        Args:
            path: Filepath to YAML configuration.

        Returns:
            Strongly-typed RunnerConfig domain object.

        Raises:
            ConfigError: If file not found, YAML syntax error, or schema validation failure.
        """
        file_path = Path(path)
        if not file_path.is_file():
            raise ConfigError(f"Configuration file not found: '{file_path}'")

        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Failed to read configuration file '{file_path}': {exc}") from exc

        return self.load_from_string(content)

    def load_from_string(self, content: str) -> RunnerConfig:
        """Parse and validate configuration from a YAML string.

        Args:
            content: String containing YAML content.

        Returns:
            Strongly-typed RunnerConfig domain object.

        Raises:
            ConfigError: If YAML syntax error or schema validation failure.
        """
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError as exc:
            raise ConfigError(f"YAML parsing error: {exc}") from exc

        if not isinstance(data, dict):
            raise ConfigError(
                f"Configuration root must be a mapping/dictionary, got: {type(data).__name__}"
            )

        return self.load_from_dict(data)

    def load_from_dict(self, data: dict[str, Any]) -> RunnerConfig:
        """Validate raw dictionary and construct domain RunnerConfig.

        Args:
            data: Raw dictionary loaded from YAML.

        Returns:
            Strongly-typed RunnerConfig domain object.

        Raises:
            ConfigError: If any section or field is missing or invalid.
        """
        for section in REQUIRED_SECTIONS:
            if section not in data or data[section] is None:
                raise ConfigError(f"Missing required section: '{section}'")
            if not isinstance(data[section], dict):
                raise ConfigError(
                    f"Section '{section}' must be a mapping, got: {type(data[section]).__name__}"
                )

        project_dict = data["project"]
        worker_dict = data["worker"]
        verification_dict = data["verification"]
        tokens_dict = data["tokens"]
        presence_dict = data["presence"]
        discord_dict = data["discord"]
        lifecycle_dict = data["lifecycle"]
        git_dict = data["git"]

        # 1. Project section
        for field in ("name", "branch", "base_branch"):
            if field not in project_dict:
                raise ConfigError(f"Missing required field '{field}' in section 'project'")
        project = ProjectConfig(
            name=project_dict["name"],
            branch=project_dict["branch"],
            base_branch=project_dict["base_branch"],
        )

        # 2. Worker section
        if "execution_skill" not in worker_dict:
            raise ConfigError("Missing required field 'execution_skill' in section 'worker'")
        worker = WorkerConfig(
            execution_skill=worker_dict["execution_skill"],
        )

        # 3. Verification section
        if "test_cmd" not in verification_dict:
            raise ConfigError("Missing required field 'test_cmd' in section 'verification'")
        verification = VerificationConfig(
            test_cmd=verification_dict["test_cmd"],
            build_cmd=verification_dict.get("build_cmd", ""),
            max_attempts=verification_dict.get("max_attempts", 3),
            timeout_seconds=verification_dict.get("timeout_seconds", 300),
        )

        # 4. Tokens section
        for field in ("warn", "handoff", "ceiling"):
            if field not in tokens_dict:
                raise ConfigError(f"Missing required field '{field}' in section 'tokens'")
        tokens = TokenBudgetConfig(
            warn=tokens_dict["warn"],
            handoff=tokens_dict["handoff"],
            ceiling=tokens_dict["ceiling"],
        )

        # 5. Presence section
        if "default_mode" not in presence_dict:
            raise ConfigError("Missing required field 'default_mode' in section 'presence'")
        presence = PresenceConfig(
            default_mode=presence_dict["default_mode"],
            idle_escalation_minutes=presence_dict.get("idle_escalation_minutes", 3),
        )

        # 6. Discord section
        for forbidden in FORBIDDEN_DISCORD_CREDENTIAL_KEYS:
            if forbidden in discord_dict:
                raise ConfigError(
                    f"Raw credential detected in discord configuration: '{forbidden}' is forbidden. "
                    "Use 'token_env' to specify the environment variable name instead."
                )
        if "token_env" not in discord_dict:
            raise ConfigError("Missing required field 'token_env' in section 'discord'")

        token_env_val = discord_dict["token_env"]
        if (
            not isinstance(token_env_val, str)
            or not ENV_VAR_PATTERN.match(token_env_val)
            or len(token_env_val) > 64
        ):
            raise ConfigError(
                f"Discord token_env must be a valid environment variable name "
                f"(matching '^[A-Z_][A-Z0-9_]*$', max 64 characters), got: {token_env_val!r}. "
                "Never store raw credentials or tokens in the configuration file."
            )

        channel_id_raw = discord_dict.get("channel_id", "")
        channel_id_val = str(channel_id_raw).strip() if channel_id_raw is not None else ""
        if channel_id_val and not DISCORD_CHANNEL_ID_PATTERN.match(channel_id_val):
            raise ConfigError(
                f"Field 'channel_id' in section 'discord' must be empty or a valid numeric Discord channel ID, "
                f"got: {channel_id_raw!r}"
            )

        discord = DiscordConfig(
            enabled=discord_dict.get("enabled", True),
            token_env=token_env_val,
            channel_id=channel_id_val,
        )

        # 7. Lifecycle section
        lifecycle_kwargs: dict[str, Any] = {
            "queue_completion": lifecycle_dict.get("queue_completion", "standby"),
            "clean_slate": lifecycle_dict.get("clean_slate", "interactive"),
        }
        if "poll_interval" in lifecycle_dict:
            lifecycle_kwargs["poll_interval"] = lifecycle_dict["poll_interval"]
        lifecycle = LifecycleConfig(**lifecycle_kwargs)

        # 8. Git section
        git = GitConfig(
            auto_push=git_dict.get("auto_push", False),
            commit_prefix=git_dict.get("commit_prefix", "feat"),
            enforce_pre_push_hook=git_dict.get("enforce_pre_push_hook", True),
        )

        # 9. Model section (optional)
        model_dict = data.get("model")
        if model_dict is None:
            model = ModelConfig()
        elif not isinstance(model_dict, dict):
            raise ConfigError(
                f"Section 'model' must be a mapping, got: {type(model_dict).__name__}"
            )
        else:
            raw_default_reasoning = model_dict.get("default_reasoning", "")
            if raw_default_reasoning is None:
                default_reasoning = ""
            elif not isinstance(raw_default_reasoning, str):
                raise ConfigError(
                    f"Field 'default_reasoning' in section 'model' must be a string, got: {type(raw_default_reasoning).__name__}"
                )
            else:
                default_reasoning = raw_default_reasoning

            raw_models = model_dict.get("models", ())
            if raw_models is None:
                raw_models = ()
            elif not isinstance(raw_models, (list, tuple)):
                raise ConfigError(
                    f"Field 'models' in section 'model' must be a list, got: {type(raw_models).__name__}"
                )

            model_entries: list[ModelEntry] = []
            for idx, entry in enumerate(raw_models):
                if not isinstance(entry, dict):
                    raise ConfigError(
                        f"Entry {idx} in section 'model.models' must be a mapping, got: {type(entry).__name__}"
                    )
                if "id" not in entry:
                    raise ConfigError(f"Missing required field 'id' in model entry {idx}")
                if "label" not in entry:
                    raise ConfigError(f"Missing required field 'label' in model entry {idx}")
                model_entries.append(
                    ModelEntry(
                        id=entry["id"],
                        label=entry["label"],
                    )
                )

            model = ModelConfig(
                models=tuple(model_entries),
                default_reasoning=default_reasoning,
            )

        return RunnerConfig(
            project=project,
            worker=worker,
            verification=verification,
            tokens=tokens,
            presence=presence,
            discord=discord,
            lifecycle=lifecycle,
            git=git,
            model=model,
        )

