"""CommandRunner protocol and CommandResult value object."""

from __future__ import annotations

from collections.abc import AsyncIterator
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
class ProcessHandle(Protocol):
    """Handle to a running external process supporting streaming output and supervision."""

    @property
    def pid(self) -> int:
        """Process identifier."""
        ...

    @property
    def stderr(self) -> str:
        """Captured stderr output accumulated so far."""
        ...

    def stdout_lines(self) -> AsyncIterator[str]:
        """Asynchronously iterate over stripped stdout lines."""
        ...

    def __aiter__(self) -> AsyncIterator[str]:
        """Asynchronously iterate over stripped stdout lines."""
        ...

    async def wait(self) -> int:
        """Wait for process completion and return the exit code."""
        ...

    async def terminate(self) -> None:
        """Terminate the process within a bounded wait."""
        ...


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

    async def spawn(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessHandle:
        """Spawn an external command asynchronously for streaming execution.

        Args:
            cmd: Command arguments list, starting with the binary/executable name.
            cwd: Optional working directory for the command.
            env: Optional environment variables dictionary.

        Returns:
            ProcessHandle for streaming stdout, draining stderr, and controlling lifecycle.

        Raises:
            ValueError: If cmd is empty or invalid.
            CommandNotFoundError: If the binary cannot be resolved.
        """
        ...
