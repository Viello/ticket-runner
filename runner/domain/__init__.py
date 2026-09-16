"""Domain entities and business rules (zero external dependencies)."""

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
from runner.domain.exceptions import (
    CleanSlateError,
    CommandNotFoundError,
    ConfigError,
    DoctorError,
    GitError,
    QueueLockError,
    SpecFormatError,
    TicketFormatError,
    TicketRunnerError,
)
from runner.domain.runtime_paths import DEFAULT_AGENT_DIR, RuntimePaths
from runner.domain.telemetry import (
    BudgetAction,
    BudgetMonitor,
    TokenUsage,
    effective_ceiling,
)
from runner.domain.ticket import Ticket, TicketStatus, parse_ticket_status

__all__ = [
    "DEFAULT_AGENT_DIR",
    "BudgetAction",
    "BudgetMonitor",
    "CleanSlateError",
    "CommandNotFoundError",
    "ConfigError",
    "DiscordConfig",
    "DoctorError",
    "GitConfig",
    "GitError",
    "LifecycleConfig",
    "PresenceConfig",
    "ProjectConfig",
    "QueueLockError",
    "RunnerConfig",
    "RuntimePaths",
    "SpecFormatError",
    "Ticket",
    "TicketFormatError",
    "TicketStatus",
    "TokenBudgetConfig",
    "TokenUsage",
    "VerificationConfig",
    "WorkerConfig",
    "effective_ceiling",
    "parse_ticket_status",
]
