"""Domain exception hierarchy for Ticket Runner."""


class TicketRunnerError(Exception):
    """Base exception for all Ticket Runner domain errors."""
    pass


class DoctorError(TicketRunnerError):
    """Raised when pre-flight health checks fail."""
    pass


class GitError(TicketRunnerError):
    """Raised when a Git operation fails."""
    pass


class ConfigError(TicketRunnerError):
    """Raised when configuration validation or loading fails."""
    pass


class TicketFormatError(TicketRunnerError):
    """Raised when a ticket file cannot be parsed, validated, or safely updated."""
    pass


class SpecFormatError(TicketFormatError):
    """Raised when a spec file cannot be parsed or lacks required sections."""
    pass


class SignalFormatError(TicketRunnerError):
    """Raised when a signal file cannot be parsed or fails strict validation."""
    pass


class StateFormatError(TicketRunnerError):
    """Raised when a state file cannot be parsed, validated, or safely updated."""
    pass



class CommandNotFoundError(TicketRunnerError):
    """Raised when an executable command cannot be resolved or found."""

    def __init__(self, command: str, message: str | None = None) -> None:
        self.command = command
        super().__init__(message or f"Command not found: '{command}'")


class QueueLockError(TicketRunnerError):
    """Raised when the queue sentinel lock cannot be acquired or operation fails."""
    pass


class CleanSlateError(TicketRunnerError):
    """Raised when clean-slate queue or spec archival fails."""
    pass


class NonInteractiveError(TicketRunnerError):
    """Raised when human contact requires an interactive stdin that is unavailable."""
    pass


class UserAbortError(TicketRunnerError):
    """Raised when an operator aborts execution via the intervention menu."""
    pass


class DiscordGatewayError(TicketRunnerError):
    """Raised when a Discord gateway operation fails."""
    pass

