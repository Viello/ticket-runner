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
    NonInteractiveError,
    QueueLockError,
    SignalFormatError,
    SpecFormatError,
    TicketFormatError,
    TicketRunnerError,
    UserAbortError,
)
from runner.domain.runtime_paths import DEFAULT_AGENT_DIR, RuntimePaths
from runner.domain.signal import (
    QuestionSignal,
    QuestionType,
    ReadySignal,
    SignalStatus,
)
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
    "NonInteractiveError",
    "PresenceConfig",
    "ProjectConfig",
    "QueueLockError",
    "QuestionSignal",
    "QuestionType",
    "ReadySignal",
    "RunnerConfig",
    "RuntimePaths",
    "SignalFormatError",
    "SignalStatus",
    "SpecFormatError",
    "Ticket",
    "TicketFormatError",
    "TicketStatus",
    "TokenBudgetConfig",
    "TokenUsage",
    "UserAbortError",
    "VerificationConfig",
    "WorkerConfig",
    "effective_ceiling",
    "parse_ticket_status",
]
