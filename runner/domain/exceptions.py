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

