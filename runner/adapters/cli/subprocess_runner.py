"""SubprocessRunner adapter executing CLI commands via asyncio."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
from pathlib import Path
import shutil
import sys

from runner.adapters.cli.windows_job import WindowsJobObject
from runner.domain.exceptions import CommandNotFoundError
from runner.ports.command_runner import CommandResult, CommandRunner, ProcessHandle

DEFAULT_STREAM_LIMIT: int = 16 * 1024 * 1024  # 16 MiB buffer limit for stream reader pipe flow control


class SubprocessProcessHandle:
    """Concrete ProcessHandle wrapping an asyncio.subprocess.Process with concurrent stderr draining and Job Object reaping."""

    def __init__(
        self,
        proc: asyncio.subprocess.Process,
        job: WindowsJobObject | None = None,
    ) -> None:
        self._proc = proc
        self._job = job
        self._stderr_chunks: list[str] = []
        self._stderr_drain_task: asyncio.Task[None] | None = None
        if self._proc.stderr is not None:
            self._stderr_drain_task = asyncio.create_task(self._drain_stderr())

    @property
    def pid(self) -> int:
        """Process identifier of the spawned child."""
        return self._proc.pid

    @property
    def stderr(self) -> str:
        """Accumulated decoded stderr output."""
        return "".join(self._stderr_chunks)

    @property
    def job(self) -> WindowsJobObject | None:
        """Windows Job Object instance associated with this process, if active."""
        return self._job

    def close(self) -> None:
        """Close the Windows Job Object handle if open, releasing or reaping the process tree."""
        if self._job is not None:
            job = self._job
            self._job = None
            try:
                job.close()
            except Exception:
                pass

    def __del__(self) -> None:
        self.close()

    async def _drain_stderr(self) -> None:
        """Concurrently drain stderr in chunks to prevent pipe buffer deadlocks."""
        if self._proc.stderr is None:
            return
        try:
            while True:
                chunk = await self._proc.stderr.read(4096)
                if not chunk:
                    break
                self._stderr_chunks.append(chunk.decode("utf-8", errors="replace"))
        except Exception:
            pass

    async def stdout_lines(self) -> AsyncIterator[str]:
        """Asynchronously iterate over stripped stdout lines."""
        if self._proc.stdout is None:
            return
        buf = bytearray()
        while True:
            chunk = await self._proc.stdout.read(65536)
            if not chunk:
                break
            buf.extend(chunk)
            while b"\n" in buf:
                idx = buf.index(b"\n")
                line_bytes = bytes(buf[:idx])
                del buf[:idx + 1]
                yield line_bytes.decode("utf-8", errors="replace").rstrip("\r")
        if buf:
            yield bytes(buf).decode("utf-8", errors="replace").rstrip("\r\n")

    def __aiter__(self) -> AsyncIterator[str]:
        """Asynchronously iterate over stripped stdout lines."""
        return self.stdout_lines()

    async def wait(self) -> int:
        """Wait for process completion, ensure stderr is drained, and return exit code."""
        try:
            code = await self._proc.wait()
            if self._stderr_drain_task is not None:
                await self._stderr_drain_task
            return code
        finally:
            self.close()

    async def terminate(self) -> None:
        """Terminate process (descendant tree on Windows, SIGTERM on POSIX) within a bounded wait."""
        if self._proc.returncode is not None:
            self.close()
            return

        pid = self._proc.pid
        if sys.platform == "win32":
            job_terminated = False
            if self._job is not None:
                try:
                    job = self._job
                    self._job = None
                    job.terminate(exit_code=1)
                    job_terminated = True
                except Exception:
                    pass

            if not job_terminated:
                # Descendant cleanup: kill entire process tree using taskkill as secondary fallback
                if isinstance(pid, int) and pid > 0:
                    try:
                        kill_proc = await asyncio.create_subprocess_exec(
                            "taskkill",
                            "/PID",
                            str(pid),
                            "/T",
                            "/F",
                            stdin=asyncio.subprocess.DEVNULL,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                        )
                        await asyncio.wait_for(kill_proc.wait(), timeout=3.0)
                    except Exception:
                        # Fallback to direct process termination
                        try:
                            self._proc.terminate()
                        except ProcessLookupError:
                            pass
        else:
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass

        # Bounded wait for process to finish
        try:
            await asyncio.wait_for(self.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass


class SubprocessRunner:
    """Concrete CommandRunner adapter wrapping asyncio subprocess operations."""

    def _prepare_command(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[str, list[str], str | None, dict[str, str] | None]:
        """Validate arguments and resolve executable path and environment."""
        if isinstance(cmd, str):
            raise TypeError("Command must be a list of strings, not a string")
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
        return executable, list(cmd[1:]), cwd_str, proc_env

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
            TypeError: If cmd is a string instead of a list.
            ValueError: If cmd is empty.
            CommandNotFoundError: If the binary cannot be resolved or executed.
        """
        executable, args, cwd_str, proc_env = self._prepare_command(cmd, cwd, env)
        raw_cmd = cmd[0]

        try:
            proc = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=DEFAULT_STREAM_LIMIT,
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

    async def spawn(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessHandle:
        """Spawn an external command asynchronously for streaming execution.

        Args:
            cmd: Command tokens list, starting with the binary or command name.
            cwd: Optional working directory path.
            env: Optional dictionary of environment variables to set/override.

        Returns:
            ProcessHandle wrapping the running process with streaming stdout and concurrent stderr draining.

        Raises:
            TypeError: If cmd is a string instead of a list of tokens.
            ValueError: If cmd is empty.
            CommandNotFoundError: If the binary cannot be resolved or executed.
        """
        executable, args, cwd_str, proc_env = self._prepare_command(cmd, cwd, env)
        raw_cmd = cmd[0]

        job: WindowsJobObject | None = None
        if sys.platform == "win32":
            job = WindowsJobObject.create()

        try:
            proc = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=DEFAULT_STREAM_LIMIT,
                cwd=cwd_str,
                env=proc_env,
            )
            if job is not None and proc.pid:
                job.assign_process(proc.pid)
        except Exception as exc:
            if job is not None:
                job.close()
            if isinstance(exc, FileNotFoundError):
                raise CommandNotFoundError(raw_cmd, str(exc)) from exc
            raise

        return SubprocessProcessHandle(proc, job=job)
