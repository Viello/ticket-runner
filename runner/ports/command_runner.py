"""CommandRunner protocol and CommandResult value object."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class CommandResult:
    """Result of an executed external command."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        """Convenience property indicating zero exit code."""
        return self.exit_code == 0


@runtime_checkable
class CommandRunner(Protocol):
    """Abstract protocol for executing external CLI commands."""

    async def run(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Execute an external command asynchronously.

        Args:
            cmd: Command arguments list, starting with the binary/executable name.
            cwd: Optional working directory for the command.
            env: Optional environment variables dictionary.

        Returns:
            CommandResult containing exit_code, stdout, and stderr.

        Raises:
            CommandNotFoundError: If the binary cannot be resolved.
        """
        ...
