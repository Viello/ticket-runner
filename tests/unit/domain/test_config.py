"""Unit tests for configuration domain models and invariants."""

from dataclasses import FrozenInstanceError
import pytest

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


def test_token_budget_config_valid() -> None:
    budget = TokenBudgetConfig(warn=120000, handoff=135000, ceiling=150000)
    assert budget.warn == 120000
    assert budget.handoff == 135000
    assert budget.ceiling == 150000


@pytest.mark.parametrize(
    ("warn", "handoff", "ceiling"),
    [
        (135000, 120000, 150000),  # warn > handoff
        (120000, 120000, 150000),  # warn == handoff
        (120000, 150000, 135000),  # handoff > ceiling
        (120000, 150000, 150000),  # handoff == ceiling
        (-10, 100, 200),           # negative warn
        (0, 100, 200),             # zero warn
        (100, 0, 200),             # zero handoff
    ],
)
def test_token_budget_config_invariants_violation(
    warn: int, handoff: int, ceiling: int
) -> None:
    with pytest.raises(ConfigError, match="Token budget"):
        TokenBudgetConfig(warn=warn, handoff=handoff, ceiling=ceiling)


def test_verification_config_valid() -> None:
    cfg = VerificationConfig(
        test_cmd="pytest",
        build_cmd="npm run build",
        max_attempts=3,
        timeout_seconds=300,
        silence_window_seconds=60,
        per_test_timeout_seconds=0,
        isolation_cmd="",
        bug_escalation_at=1,
    )
    assert cfg.test_cmd == "pytest"
    assert cfg.build_cmd == "npm run build"
    assert cfg.max_attempts == 3
    assert cfg.timeout_seconds == 300
    assert cfg.silence_window_seconds == 60
    assert cfg.per_test_timeout_seconds == 0
    assert cfg.isolation_cmd == ""
    assert cfg.bug_escalation_at == 1


def test_verification_config_defaults() -> None:
    cfg = VerificationConfig(test_cmd="pytest")
    assert cfg.build_cmd == ""
    assert cfg.max_attempts == 3
    assert cfg.timeout_seconds == 300
    assert cfg.silence_window_seconds == 60
    assert cfg.per_test_timeout_seconds == 0
    assert cfg.isolation_cmd == ""
    assert cfg.bug_escalation_at == 1


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"test_cmd": ""}, "test_cmd"),
        ({"test_cmd": "   "}, "test_cmd"),
        ({"build_cmd": 123}, "build_cmd"),
        ({"max_attempts": 0}, "max_attempts"),
        ({"max_attempts": -1}, "max_attempts"),
        ({"timeout_seconds": 0}, "timeout_seconds"),
        ({"timeout_seconds": -10}, "timeout_seconds"),
        ({"silence_window_seconds": 0}, "silence_window_seconds"),
        ({"silence_window_seconds": -1}, "silence_window_seconds"),
        ({"silence_window_seconds": True}, "silence_window_seconds"),
        ({"per_test_timeout_seconds": -1}, "per_test_timeout_seconds"),
        ({"per_test_timeout_seconds": True}, "per_test_timeout_seconds"),
        ({"isolation_cmd": 123}, "isolation_cmd"),
        ({"bug_escalation_at": -2}, "bug_escalation_at"),
        ({"bug_escalation_at": True}, "bug_escalation_at"),
    ],
)
def test_verification_config_invalid(kwargs: dict[str, object], match: str) -> None:
    params: dict[str, object] = {"test_cmd": "pytest"}
    params.update(kwargs)
    with pytest.raises(ConfigError, match=match):
        VerificationConfig(**params)  # type: ignore[arg-type]


def test_presence_config_valid() -> None:
    cfg_nearby = PresenceConfig(default_mode="nearby", idle_escalation_minutes=3)
    assert cfg_nearby.default_mode == "nearby"
    cfg_away = PresenceConfig(default_mode="away", idle_escalation_minutes=5)
    assert cfg_away.default_mode == "away"


@pytest.mark.parametrize(
    ("mode", "idle_mins"),
    [
        ("invalid", 3),
        ("local", 3),
        ("nearby", 0),
        ("nearby", -1),
    ],
)
def test_presence_config_invalid(mode: str, idle_mins: int) -> None:
    with pytest.raises(ConfigError):
        PresenceConfig(default_mode=mode, idle_escalation_minutes=idle_mins)


def test_lifecycle_config_valid() -> None:
    cfg = LifecycleConfig(queue_completion="standby", clean_slate="interactive")
    assert cfg.queue_completion == "standby"
    assert cfg.clean_slate == "interactive"
    assert cfg.poll_interval == 5.0

    cfg2 = LifecycleConfig(queue_completion="terminate", clean_slate="always", poll_interval=2.5)
    assert cfg2.queue_completion == "terminate"
    assert cfg2.clean_slate == "always"
    assert cfg2.poll_interval == 2.5

    cfg3 = LifecycleConfig(queue_completion="standby", clean_slate="never", poll_interval=10)
    assert cfg3.clean_slate == "never"
    assert cfg3.poll_interval == 10.0
    assert isinstance(cfg3.poll_interval, float)


@pytest.mark.parametrize(
    ("queue_completion", "clean_slate"),
    [
        ("unknown", "interactive"),
        ("standby", "prompt"),
        ("standby", "invalid"),
    ],
)
def test_lifecycle_config_invalid(queue_completion: str, clean_slate: str) -> None:
    with pytest.raises(ConfigError):
        LifecycleConfig(queue_completion=queue_completion, clean_slate=clean_slate)


@pytest.mark.parametrize(
    "invalid_interval",
    [
        0,
        0.0,
        -1,
        -0.5,
        float("inf"),
        float("-inf"),
        float("nan"),
        "5.0",
        "invalid",
        True,
        False,
        None,
    ],
)
def test_lifecycle_config_poll_interval_invalid(invalid_interval: object) -> None:
    with pytest.raises(ConfigError, match="poll_interval"):
        LifecycleConfig(poll_interval=invalid_interval)  # type: ignore[arg-type]


def test_discord_config_valid() -> None:
    cfg = DiscordConfig(enabled=True, token_env="DISCORD_BOT_TOKEN", channel_id="12345")
    assert cfg.enabled is True
    assert cfg.token_env == "DISCORD_BOT_TOKEN"
    assert cfg.channel_id == "12345"


@pytest.mark.parametrize(
    "token_env",
    [
        "",
        "   ",
        "NOT A VALID IDENTIFIER",
        "token.with.dots",
        "MTE1MjMzNDQ1NTY2Nzc4OA.G-secret.token",
        "123_STARTS_WITH_NUMBER",
    ],
)
def test_discord_config_invalid_token_env(token_env: str) -> None:
    with pytest.raises(ConfigError):
        DiscordConfig(enabled=True, token_env=token_env, channel_id="")


def test_immutability_frozen_dataclass() -> None:
    budget = TokenBudgetConfig(warn=120000, handoff=135000, ceiling=150000)
    with pytest.raises(FrozenInstanceError):
        budget.warn = 100000  # type: ignore[misc]


def test_runner_config_composite() -> None:
    project = ProjectConfig(name="ticket-runner", branch="agent/ticket-runner", base_branch="main")
    worker = WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md")
    verification = VerificationConfig(test_cmd="pytest", build_cmd="", max_attempts=3, timeout_seconds=300)
    tokens = TokenBudgetConfig(warn=120000, handoff=135000, ceiling=150000)
    presence = PresenceConfig(default_mode="nearby", idle_escalation_minutes=3)
    discord = DiscordConfig(enabled=True, token_env="DISCORD_BOT_TOKEN", channel_id="")
    lifecycle = LifecycleConfig(queue_completion="standby", clean_slate="interactive")
    git = GitConfig(auto_push=False, commit_prefix="feat", enforce_pre_push_hook=True)

    config = RunnerConfig(
        project=project,
        worker=worker,
        verification=verification,
        tokens=tokens,
        presence=presence,
        discord=discord,
        lifecycle=lifecycle,
        git=git,
    )

    assert config.project == project
    assert config.worker == worker
    assert config.verification == verification
    assert config.tokens == tokens
    assert config.token_budget == tokens
    assert config.presence == presence
    assert config.discord == discord
    assert config.lifecycle == lifecycle
    assert config.git == git
    assert config.model == ModelConfig()


def test_model_entry_valid() -> None:
    entry = ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat")
    assert entry.id == "deepseek/deepseek-chat"
    assert entry.label == "DeepSeek Chat"


@pytest.mark.parametrize(
    ("entry_id", "label"),
    [
        ("", "Label"),
        ("   ", "Label"),
        (123, "Label"),
        (None, "Label"),
        ("id", ""),
        ("id", "   "),
        ("id", 456),
        ("id", None),
    ],
)
def test_model_entry_invalid(entry_id: object, label: object) -> None:
    with pytest.raises(ConfigError):
        ModelEntry(id=entry_id, label=label)  # type: ignore[arg-type]


def test_model_config_default() -> None:
    cfg = ModelConfig()
    assert cfg.models == ()
    assert cfg.default_reasoning == ""


def test_model_config_valid() -> None:
    e1 = ModelEntry(id="m1", label="Model 1")
    e2 = ModelEntry(id="m2", label="Model 2")
    cfg = ModelConfig(models=(e1, e2), default_reasoning="high")
    assert cfg.models == (e1, e2)
    assert cfg.default_reasoning == "high"


def test_model_config_converts_list_to_tuple() -> None:
    e1 = ModelEntry(id="m1", label="Model 1")
    cfg = ModelConfig(models=[e1])
    assert cfg.models == (e1,)
    assert isinstance(cfg.models, tuple)


def test_model_config_handles_none_default_reasoning() -> None:
    cfg = ModelConfig(default_reasoning=None)  # type: ignore[arg-type]
    assert cfg.default_reasoning == ""


@pytest.mark.parametrize(
    "invalid_reasoning",
    [123, True, False, ["high"], {"reasoning": "high"}],
)
def test_model_config_invalid_default_reasoning(invalid_reasoning: object) -> None:
    with pytest.raises(ConfigError, match="default_reasoning"):
        ModelConfig(default_reasoning=invalid_reasoning)  # type: ignore[arg-type]


def test_model_config_rejects_non_sequence_models() -> None:
    with pytest.raises(ConfigError, match="models"):
        ModelConfig(models="not-a-sequence")  # type: ignore[arg-type]


def test_model_config_rejects_non_model_entry_elements() -> None:
    with pytest.raises(ConfigError, match="ModelEntry"):
        ModelConfig(models=(ModelEntry(id="m1", label="M1"), "invalid"))  # type: ignore[arg-type]


def test_model_config_rejects_duplicate_ids() -> None:
    e1 = ModelEntry(id="deepseek/chat", label="DeepSeek Chat 1")
    e2 = ModelEntry(id="deepseek/chat", label="DeepSeek Chat 2")
    with pytest.raises(ConfigError, match="Duplicate model id"):
        ModelConfig(models=(e1, e2))


def test_runner_config_with_custom_model_config() -> None:
    model_cfg = ModelConfig(
        models=(ModelEntry(id="custom/model", label="Custom Model"),),
        default_reasoning="low",
    )
    config = RunnerConfig(
        project=ProjectConfig(name="test", branch="b", base_branch="main"),
        worker=WorkerConfig(execution_skill="s"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
        model=model_cfg,
    )
    assert config.model == model_cfg

