"""FakeCommandRunner test double for deterministic in-memory command execution."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

from runner.ports.command_runner import CommandResult, CommandRunner, ProcessHandle


@dataclass(frozen=True)
class CommandInvocation:
    """Record of an executed command invocation."""

    cmd: list[str]
    cwd: Path | None = None
    env: dict[str, str] | None = None


class FakeProcessHandle:
    """Test double for ProcessHandle supporting scripted output and lifecycle recording."""

    def __init__(
        self,
        stdout_lines: list[str] | None = None,
        stderr: str = "",
        exit_code: int = 0,
        pid: int = 12345,
        delay: float = 0.0,
    ) -> None:
        self._raw_lines = list(stdout_lines or [])
        self._stderr = stderr
        self._exit_code = exit_code
        self._pid = pid
        self._delay = delay
        self.terminated = False

    @property
    def pid(self) -> int:
        """Scripted process identifier."""
        return self._pid

    @property
    def stderr(self) -> str:
        """Scripted stderr output."""
        return self._stderr

    async def stdout_lines(self) -> AsyncIterator[str]:
        """Yield scripted stdout lines with line endings stripped."""
        for line in self._raw_lines:
            if self.terminated:
                break
            if self._delay > 0:
                await asyncio.sleep(self._delay)
            yield line.rstrip("\r\n")

    def __aiter__(self) -> AsyncIterator[str]:
        """Asynchronously iterate over stripped stdout lines."""
        return self.stdout_lines()

    async def wait(self) -> int:
        """Return scripted exit code."""
        return self._exit_code

    async def terminate(self) -> None:
        """Mark handle as terminated within bounded wait."""
        self.terminated = True


class FakeCommandRunner:
    """In-memory test double implementing CommandRunner protocol."""

    def __init__(
        self,
        default_result: CommandResult | None = None,
        default_spawn_handle: FakeProcessHandle | None = None,
    ) -> None:
        self.invocations: list[CommandInvocation] = []
        self.spawn_invocations: list[CommandInvocation] = []
        self._registrations: dict[str, CommandResult] = {}
        self._spawn_registrations: dict[str, FakeProcessHandle] = {}
        self._spawn_sequences: dict[str, list[FakeProcessHandle]] = {}
        self.default_result = default_result or CommandResult(
            exit_code=0,
            stdout="",
            stderr="",
        )
        self.default_spawn_handle = default_spawn_handle

    @property
    def commands(self) -> list[list[str]]:
        """List of command token lists executed via run() so far."""
        return [inv.cmd for inv in self.invocations]

    @property
    def spawns(self) -> list[list[str]]:
        """List of command token lists executed via spawn() so far."""
        return [inv.cmd for inv in self.spawn_invocations]

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

    def register_spawn(
        self,
        cmd: list[str] | str,
        stdout_lines: list[str] | None = None,
        stderr: str = "",
        exit_code: int = 0,
        pid: int = 12345,
        delay: float = 0.0,
    ) -> FakeProcessHandle:
        """Register scripted spawn outputs for a command."""
        key = self._normalize_key(cmd)
        handle = FakeProcessHandle(
            stdout_lines=stdout_lines,
            stderr=stderr,
            exit_code=exit_code,
            pid=pid,
            delay=delay,
        )
        self._spawn_registrations[key] = handle
        self._spawn_sequences.setdefault(key, []).append(handle)
        return handle

    def register_spawn_handle(
        self,
        cmd: list[str] | str,
        handle: FakeProcessHandle,
    ) -> None:
        """Register an existing FakeProcessHandle for a command."""
        key = self._normalize_key(cmd)
        self._spawn_registrations[key] = handle
        self._spawn_sequences.setdefault(key, []).append(handle)

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

    async def spawn(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessHandle:
        """Record the spawn invocation and return the registered or default handle."""
        if isinstance(cmd, str):
            raise TypeError("Command must be a list of strings, not a string")
        if not cmd:
            raise ValueError("Command list cannot be empty")

        self.spawn_invocations.append(CommandInvocation(cmd=list(cmd), cwd=cwd, env=env))
        key = self._normalize_key(cmd)
        if key in self._spawn_sequences and self._spawn_sequences[key]:
            if len(self._spawn_sequences[key]) > 1:
                return self._spawn_sequences[key].pop(0)
            return self._spawn_sequences[key][0]
        if key in self._spawn_registrations:
            return self._spawn_registrations[key]
        if self.default_spawn_handle is not None:
            return self.default_spawn_handle
        return FakeProcessHandle(stdout_lines=[], stderr="", exit_code=0)
