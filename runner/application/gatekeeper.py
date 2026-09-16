"""Gatekeeper command executor running configured verification commands (T028)."""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.domain.config import VerificationConfig
from runner.ports.command_runner import CommandRunner

TAIL_LINE_LIMIT: int = 100
"""Number of trailing output lines retained per command and injected as diagnostics."""

TERMINATION_GRACE_SECONDS: float = 0.5
"""Bounded grace for stream draining after a timed-out command is terminated."""

BUILD_LABEL: str = "build"
TEST_LABEL: str = "test"


def resolve_shell(platform: str | None = None) -> str:
    """Resolve the platform shell to a trusted executable path.

    Windows resolution prefers COMSPEC and the System32 directory over PATH
    lookups so a repository-local `cmd.exe` dropped into the supervised working
    tree can never shadow the real shell.
    """
    effective_platform = platform if platform is not None else sys.platform
    if effective_platform != "win32":
        return "/bin/sh"

    comspec = os.environ.get("COMSPEC", "")
    if comspec and Path(comspec).is_absolute() and Path(comspec).is_file():
        return comspec

    system_root = os.environ.get("SystemRoot", "")
    if system_root:
        candidate = Path(system_root) / "System32" / "cmd.exe"
        if candidate.is_file():
            return str(candidate)

    return "cmd.exe"


def build_shell_argv(command: str, platform: str | None = None) -> list[str]:
    """Wrap a shell command string into platform shell argv tokens (ADR 0016).

    Args:
        command: Trusted operator-authored shell command string from config.yaml.
        platform: Platform identifier; defaults to the host platform.

    Returns:
        argv tokens for cmd.exe /d /s /c on Windows, /bin/sh -c elsewhere.
    """
    effective_platform = platform if platform is not None else sys.platform
    shell = resolve_shell(effective_platform)
    if effective_platform == "win32":
        return [shell, "/d", "/s", "/c", command]
    return [shell, "-c", command]


@dataclass(frozen=True)
class CommandOutcome:
    """Outcome of a single Gatekeeper verification command.

    Attributes:
        label: Command role, "build" or "test".
        command: The operator-authored command string that was executed.
        exit_code: Process exit code, or None when the command timed out.
        timed_out: Whether the command exceeded its timeout bound.
        tail: Last TAIL_LINE_LIMIT output lines, stdout lines followed by
            drained stderr lines. Precise stdout/stderr interleaving is not
            available on the command runner port, so ordering is normalized.
    """

    label: str
    command: str
    exit_code: int | None
    timed_out: bool
    tail: str

    @property
    def passed(self) -> bool:
        """A command passes only when it exited with code 0 and never timed out."""
        return not self.timed_out and self.exit_code == 0


@dataclass(frozen=True)
class VerificationReport:
    """Consolidated Gatekeeper verification outcome for one verification cycle.

    Attributes:
        passed: True only when every executed command passed.
        results: Per-command outcomes in execution order.
        diagnostics: Injection-shaped blocks for failed and timed-out commands only.
        skipped_commands: Command strings not executed because an earlier command failed.
    """

    passed: bool
    results: tuple[CommandOutcome, ...]
    diagnostics: tuple[str, ...]
    skipped_commands: tuple[str, ...]


def _format_diagnostic(outcome: CommandOutcome, timeout_seconds: int) -> str:
    """Render one failed command block: header, status line, then the output tail."""
    if outcome.timed_out:
        status = f"timed out after {timeout_seconds}s"
    else:
        status = f"exit code {outcome.exit_code}"
    block = [f"$ {outcome.command}", status]
    if outcome.tail:
        block.append(outcome.tail)
    return "\n".join(block)


class GatekeeperCommandExecutor:
    """Runs build_cmd then test_cmd as bounded shell subprocesses and captures diagnostics."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        cwd: Path | None = None,
        platform: str | None = None,
    ) -> None:
        self._command_runner = command_runner or SubprocessRunner()
        self._cwd = cwd
        self._platform = platform if platform is not None else sys.platform

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        """Execute the configured verification commands sequentially.

        An empty build_cmd is skipped silently. A failing or timed-out build_cmd
        skips test_cmd. Each command runs under its own timeout_seconds bound.
        """
        results: list[CommandOutcome] = []
        diagnostics: list[str] = []
        skipped: list[str] = []

        if config.build_cmd.strip():
            build_outcome = await self._execute(
                BUILD_LABEL, config.build_cmd, config.timeout_seconds
            )
            results.append(build_outcome)
            if not build_outcome.passed:
                diagnostics.append(
                    _format_diagnostic(build_outcome, config.timeout_seconds)
                )
                skipped.append(config.test_cmd)
                return VerificationReport(
                    passed=False,
                    results=tuple(results),
                    diagnostics=tuple(diagnostics),
                    skipped_commands=tuple(skipped),
                )

        test_outcome = await self._execute(
            TEST_LABEL, config.test_cmd, config.timeout_seconds
        )
        results.append(test_outcome)
        if not test_outcome.passed:
            diagnostics.append(_format_diagnostic(test_outcome, config.timeout_seconds))

        return VerificationReport(
            passed=all(outcome.passed for outcome in results),
            results=tuple(results),
            diagnostics=tuple(diagnostics),
            skipped_commands=tuple(skipped),
        )

    async def _execute(
        self, label: str, command: str, timeout_seconds: int
    ) -> CommandOutcome:
        """Spawn one shell command and wait for output and exit under its timeout bound."""
        argv = build_shell_argv(command, self._platform)
        handle = await self._command_runner.spawn(argv, cwd=self._cwd)

        stdout_lines: deque[str] = deque(maxlen=TAIL_LINE_LIMIT)

        async def _consume_stdout() -> None:
            async for line in handle.stdout_lines():
                stdout_lines.append(line.rstrip("\r\n"))

        stdout_task = asyncio.ensure_future(_consume_stdout())
        wait_task = asyncio.ensure_future(handle.wait())
        exit_code: int | None = None
        timed_out = False

        _, pending = await asyncio.wait(
            {stdout_task, wait_task},
            timeout=float(timeout_seconds),
            return_when=asyncio.ALL_COMPLETED,
        )
        if pending:
            timed_out = True
            with suppress(Exception):
                await handle.terminate()
            _, pending = await asyncio.wait(
                {stdout_task, wait_task},
                timeout=TERMINATION_GRACE_SECONDS,
                return_when=asyncio.ALL_COMPLETED,
            )

        for task in (stdout_task, wait_task):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

        if not timed_out:
            exit_code = wait_task.result()
            stdout_task.result()

        tail_source = list(stdout_lines)
        tail_source.extend(handle.stderr.splitlines()[-TAIL_LINE_LIMIT:])

        return CommandOutcome(
            label=label,
            command=command,
            exit_code=exit_code,
            timed_out=timed_out,
            tail="\n".join(tail_source[-TAIL_LINE_LIMIT:]),
        )
