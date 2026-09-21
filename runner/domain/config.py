"""Domain configuration entities and invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from runner.domain.exceptions import ConfigError

VALID_PRESENCE_MODES = frozenset({"nearby", "away"})
VALID_QUEUE_COMPLETIONS = frozenset({"standby", "terminate"})
VALID_CLEAN_SLATE_POLICIES = frozenset({"interactive", "always", "never"})


@dataclass(frozen=True)
class ProjectConfig:
    """Project-level git and repository configuration."""

    name: str
    branch: str
    base_branch: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ConfigError("Project name must be a non-empty string")
        if not isinstance(self.branch, str) or not self.branch.strip():
            raise ConfigError("Project branch must be a non-empty string")
        if not isinstance(self.base_branch, str) or not self.base_branch.strip():
            raise ConfigError("Project base_branch must be a non-empty string")


@dataclass(frozen=True)
class WorkerConfig:
    """Worker model execution configuration."""

    execution_skill: str

    def __post_init__(self) -> None:
        if not isinstance(self.execution_skill, str) or not self.execution_skill.strip():
            raise ConfigError("Worker execution_skill must be a non-empty string path")


@dataclass(frozen=True)
class VerificationConfig:
    """Gatekeeper independent verification commands and thresholds."""

    test_cmd: str
    build_cmd: str = ""
    max_attempts: int = 3
    timeout_seconds: int = 300
    silence_window_seconds: int = 60
    per_test_timeout_seconds: int = 0
    isolation_cmd: str = ""
    bug_escalation_at: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.test_cmd, str) or not self.test_cmd.strip():
            raise ConfigError("Verification test_cmd must be a non-empty string")
        if not isinstance(self.build_cmd, str):
            raise ConfigError("Verification build_cmd must be a string")
        if not isinstance(self.max_attempts, int) or self.max_attempts <= 0:
            raise ConfigError("Verification max_attempts must be a positive integer")
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ConfigError("Verification timeout_seconds must be a positive integer")
        if (
            isinstance(self.silence_window_seconds, bool)
            or not isinstance(self.silence_window_seconds, int)
            or self.silence_window_seconds <= 0
        ):
            raise ConfigError("Verification silence_window_seconds must be a positive integer (> 0)")
        if (
            isinstance(self.per_test_timeout_seconds, bool)
            or not isinstance(self.per_test_timeout_seconds, int)
            or self.per_test_timeout_seconds < 0
        ):
            raise ConfigError("Verification per_test_timeout_seconds must be a non-negative integer (>= 0)")
        if not isinstance(self.isolation_cmd, str):
            raise ConfigError("Verification isolation_cmd must be a string")
        if (
            isinstance(self.bug_escalation_at, bool)
            or not isinstance(self.bug_escalation_at, int)
            or self.bug_escalation_at < -1
        ):
            raise ConfigError("Verification bug_escalation_at must be an integer >= -1")


@dataclass(frozen=True)
class TokenBudgetConfig:
    """Token threshold boundaries for warning, handoff, and session ceiling."""

    warn: int = 120000
    handoff: int = 135000
    ceiling: int = 150000

    def __post_init__(self) -> None:
        if not isinstance(self.warn, int) or self.warn <= 0:
            raise ConfigError(f"Token budget warn threshold must be a positive integer, got: {self.warn}")
        if not isinstance(self.handoff, int) or self.handoff <= 0:
            raise ConfigError(f"Token budget handoff threshold must be a positive integer, got: {self.handoff}")
        if not isinstance(self.ceiling, int) or self.ceiling <= 0:
            raise ConfigError(f"Token budget ceiling threshold must be a positive integer, got: {self.ceiling}")
        if not (self.warn < self.handoff < self.ceiling):
            raise ConfigError(
                f"Token budget invariant violated: warn ({self.warn}) < handoff ({self.handoff}) < ceiling ({self.ceiling})"
            )


@dataclass(frozen=True)
class PresenceConfig:
    """Human-in-the-loop presence mode and escalation settings."""

    default_mode: str = "nearby"
    idle_escalation_minutes: int = 3

    def __post_init__(self) -> None:
        if self.default_mode not in VALID_PRESENCE_MODES:
            raise ConfigError(
                f"Presence default_mode must be one of {sorted(VALID_PRESENCE_MODES)}, got: '{self.default_mode}'"
            )
        if not isinstance(self.idle_escalation_minutes, int) or self.idle_escalation_minutes <= 0:
            raise ConfigError("Presence idle_escalation_minutes must be a positive integer")


@dataclass(frozen=True)
class DiscordConfig:
    """Discord remote notification and thread configuration."""

    enabled: bool = True
    token_env: str = "DISCORD_BOT_TOKEN"
    channel_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("Discord enabled must be a boolean")
        if not isinstance(self.token_env, str) or not self.token_env.strip():
            raise ConfigError("Discord token_env must be a non-empty string environment variable name")
        if not self.token_env.isidentifier():
            raise ConfigError(
                f"Discord token_env must be a valid environment variable name (alphanumeric and underscores), got: '{self.token_env}'"
            )
        if not isinstance(self.channel_id, str):
            raise ConfigError("Discord channel_id must be a string")


@dataclass(frozen=True)
class LifecycleConfig:
    """Queue completion and spec cleanup lifecycle behaviors."""

    queue_completion: str = "standby"
    clean_slate: str = "interactive"
    poll_interval: float = 5.0

    def __post_init__(self) -> None:
        if self.queue_completion not in VALID_QUEUE_COMPLETIONS:
            raise ConfigError(
                f"Lifecycle queue_completion must be one of {sorted(VALID_QUEUE_COMPLETIONS)}, got: '{self.queue_completion}'"
            )
        if self.clean_slate not in VALID_CLEAN_SLATE_POLICIES:
            raise ConfigError(
                f"Lifecycle clean_slate must be one of {sorted(VALID_CLEAN_SLATE_POLICIES)}, got: '{self.clean_slate}'"
            )
        if (
            isinstance(self.poll_interval, bool)
            or not isinstance(self.poll_interval, (int, float))
            or not math.isfinite(self.poll_interval)
            or self.poll_interval <= 0
        ):
            raise ConfigError(
                f"Lifecycle poll_interval must be a positive finite number, got: {self.poll_interval!r}"
            )
        if not isinstance(self.poll_interval, float):
            object.__setattr__(self, "poll_interval", float(self.poll_interval))


@dataclass(frozen=True)
class GitConfig:
    """Git branch, auto-push, and commit conventions."""

    auto_push: bool = False
    commit_prefix: str = "feat"
    enforce_pre_push_hook: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.auto_push, bool):
            raise ConfigError("Git auto_push must be a boolean")
        if not isinstance(self.commit_prefix, str) or not self.commit_prefix.strip():
            raise ConfigError("Git commit_prefix must be a non-empty string")
        if not isinstance(self.enforce_pre_push_hook, bool):
            raise ConfigError("Git enforce_pre_push_hook must be a boolean")


@dataclass(frozen=True)
class ModelEntry:
    """A selectable LLM option with provider/model id and human-readable label."""

    id: str
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ConfigError("ModelEntry id must be a non-empty string")
        if not isinstance(self.label, str) or not self.label.strip():
            raise ConfigError("ModelEntry label must be a non-empty string")


@dataclass(frozen=True)
class ModelConfig:
    """Configured LLM options and default reasoning variant."""

    models: tuple[ModelEntry, ...] = ()
    default_reasoning: str = ""

    def __post_init__(self) -> None:
        if self.default_reasoning is None:
            object.__setattr__(self, "default_reasoning", "")
        elif not isinstance(self.default_reasoning, str):
            raise ConfigError("ModelConfig default_reasoning must be a string")

        if not isinstance(self.models, (tuple, list)):
            raise ConfigError("ModelConfig models must be a tuple or list of ModelEntry")

        for entry in self.models:
            if not isinstance(entry, ModelEntry):
                raise ConfigError(
                    f"ModelConfig models entries must be ModelEntry, got: {type(entry).__name__}"
                )

        if not isinstance(self.models, tuple):
            object.__setattr__(self, "models", tuple(self.models))

        seen_ids: set[str] = set()
        for entry in self.models:
            if entry.id in seen_ids:
                raise ConfigError(f"Duplicate model id detected in ModelConfig: '{entry.id}'")
            seen_ids.add(entry.id)


@dataclass(frozen=True)
class UIConfig:
    """Terminal UI and session terminal configuration.

    Supported values for ``session_terminal`` include:
    - ``"auto"``: automatically sniffs the active caller terminal environment.
    - Explicit host binary: e.g. ``"wt.exe"``, ``"pwsh.exe"``, ``"powershell.exe"``, ``"cmd.exe"``.
    - Empty string ``""``: unconfigured (fallback probing in Doctor pre-flight).
    """

    session_terminal: str = ""

    def __post_init__(self) -> None:
        if self.session_terminal is None:
            object.__setattr__(self, "session_terminal", "")
        elif not isinstance(self.session_terminal, str):
            raise ConfigError("UI session_terminal must be a string")


@dataclass(frozen=True)
class RunnerConfig:
    """Authoritative composite configuration for Ticket Runner."""

    project: ProjectConfig
    worker: WorkerConfig
    verification: VerificationConfig
    tokens: TokenBudgetConfig
    presence: PresenceConfig
    discord: DiscordConfig
    lifecycle: LifecycleConfig
    git: GitConfig
    model: ModelConfig = field(default_factory=ModelConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    @property
    def token_budget(self) -> TokenBudgetConfig:
        """Convenience alias for tokens configuration."""
        return self.tokens

