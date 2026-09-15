"""FakeCommandRunner test double for deterministic in-memory command execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runner.ports.command_runner import CommandResult, CommandRunner


@dataclass(frozen=True)
class CommandInvocation:
    """Record of an executed command invocation."""

    cmd: list[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None


class FakeCommandRunner:
    """In-memory test double implementing CommandRunner protocol."""

    def __init__(
        self,
        default_result: CommandResult | None = None,
    ) -> None:
        self.invocations: list[CommandInvocation] = []
        self._registrations: dict[str, CommandResult] = {}
        self.default_result = default_result or CommandResult(
            exit_code=0,
            stdout="",
            stderr="",
        )

    @property
    def commands(self) -> list[list[str]]:
        """List of command token lists executed so far."""
        return [inv.cmd for inv in self.invocations]

    def _normalize_key(self, cmd: list[str] | str) -> str:
        if isinstance(cmd, str):
            return cmd.strip()
        return " ".join(cmd).strip()

    def register(
        self,
        cmd: list[str] | str,
        exit_code: int = 0,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        """Register a scripted command result for a specific command string or token list."""
        key = self._normalize_key(cmd)
        self._registrations[key] = CommandResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )

    def register_result(
        self,
        cmd: list[str] | str,
        result: CommandResult,
    ) -> None:
        """Register a pre-built CommandResult for a specific command."""
        key = self._normalize_key(cmd)
        self._registrations[key] = result

    async def run(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Record the invocation and return the registered result or default."""
        self.invocations.append(CommandInvocation(cmd=list(cmd), cwd=cwd, env=env))
        key = self._normalize_key(cmd)
        if key in self._registrations:
            return self._registrations[key]
        return self.default_result
