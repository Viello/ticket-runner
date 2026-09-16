"""Unit tests for configuration domain models and invariants."""

from dataclasses import FrozenInstanceError
import pytest

from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
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
    )
    assert cfg.test_cmd == "pytest"
    assert cfg.build_cmd == "npm run build"
    assert cfg.max_attempts == 3
    assert cfg.timeout_seconds == 300


@pytest.mark.parametrize(
    ("test_cmd", "max_attempts", "timeout_seconds"),
    [
        ("", 3, 300),        # empty test_cmd
        ("   ", 3, 300),     # whitespace test_cmd
        ("pytest", 0, 300),  # zero max_attempts
        ("pytest", -1, 300), # negative max_attempts
        ("pytest", 3, 0),    # zero timeout
        ("pytest", 3, -10),  # negative timeout
    ],
)
def test_verification_config_invalid(
    test_cmd: str, max_attempts: int, timeout_seconds: int
) -> None:
    with pytest.raises(ConfigError):
        VerificationConfig(
            test_cmd=test_cmd,
            build_cmd="",
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )


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

    cfg2 = LifecycleConfig(queue_completion="terminate", clean_slate="always")
    assert cfg2.queue_completion == "terminate"
    assert cfg2.clean_slate == "always"

    cfg3 = LifecycleConfig(queue_completion="standby", clean_slate="never")
    assert cfg3.clean_slate == "never"


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
