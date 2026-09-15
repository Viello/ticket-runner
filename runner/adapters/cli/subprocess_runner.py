"""SubprocessRunner adapter executing CLI commands via asyncio."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import shutil

from runner.domain.exceptions import CommandNotFoundError
from runner.ports.command_runner import CommandResult, CommandRunner


class SubprocessRunner:
    """Concrete CommandRunner adapter wrapping asyncio.create_subprocess_exec."""

    async def run(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Execute an external command asynchronously with executable path resolution.

        Args:
            cmd: Command tokens list, starting with the binary or command name.
            cwd: Optional working directory path.
            env: Optional dictionary of environment variables to set/override.

        Returns:
            CommandResult containing exit_code, stdout, and stderr.

        Raises:
            ValueError: If cmd is empty.
            CommandNotFoundError: If the binary cannot be resolved or executed.
        """
        if not cmd:
            raise ValueError("Command list cannot be empty")

        raw_cmd = cmd[0]
        executable = shutil.which(raw_cmd)

        # If not found on PATH, check if it's a direct file path or relative to cwd
        if executable is None and cwd is not None:
            local_path = Path(cwd) / raw_cmd
            if local_path.is_file():
                executable = str(local_path.resolve())

        if executable is None:
            raise CommandNotFoundError(raw_cmd)

        # Merge environment variables if overrides provided
        proc_env: dict[str, str] | None = None
        if env is not None:
            proc_env = os.environ.copy()
            proc_env.update(env)

        cwd_str = str(cwd) if cwd is not None else None

        try:
            proc = await asyncio.create_subprocess_exec(
                executable,
                *cmd[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd_str,
                env=proc_env,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
        except FileNotFoundError as exc:
            raise CommandNotFoundError(raw_cmd, str(exc)) from exc

        exit_code = proc.returncode if proc.returncode is not None else -1
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        return CommandResult(exit_code=exit_code, stdout=stdout, stderr=stderr)
