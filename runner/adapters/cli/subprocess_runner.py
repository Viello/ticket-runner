"""SubprocessRunner adapter executing CLI commands via asyncio."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
from pathlib import Path
import re
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
            self.close()
            if self._stderr_drain_task is not None:
                try:
                    await asyncio.wait_for(self._stderr_drain_task, timeout=2.0)
                except Exception:
                    pass
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
                        except (ProcessLookupError, OSError):
                            pass
        else:
            try:
                self._proc.terminate()
            except (ProcessLookupError, OSError):
                pass

        # Bounded wait for process to finish
        try:
            await asyncio.wait_for(self.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            try:
                self._proc.kill()
            except (ProcessLookupError, OSError):
                pass
            try:
                await asyncio.wait_for(self.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass


def unwrap_batch_file(executable: str) -> tuple[str, list[str]] | None:
    """If executable is a Windows .cmd or .bat wrapper, resolve the underlying PE binary or script target.

    On Windows, invoking .cmd or .bat files through CreateProcess routes execution
    through cmd.exe /c, which fundamentally cannot handle multiline arguments (truncating
    them at the first newline character). This helper inspects batch scripts (such as
    those generated by npm for global CLIs like opencode) and extracts the target binary
    or interpreter to execute directly as a PE image.
    """
    path = Path(executable)
    if path.suffix.lower() not in (".cmd", ".bat") or not path.is_file():
        return None

    sibling_exe = path.parent / f"{path.stem}.exe"
    if sibling_exe.is_file():
        return str(sibling_exe.resolve()), []

    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    dp0 = path.parent

    # 1. Match "%dp0%\<rel_path>.exe" %* (npm binary wrapper, e.g. opencode.cmd)
    m_direct = re.search(r'"%dp0%\\([^"]+\.exe)"', content, re.IGNORECASE)
    if m_direct:
        target = (dp0 / m_direct.group(1)).resolve()
        if target.is_file():
            return str(target), []

    # 2. Match "%_prog%" "%dp0%\<script>" or node "%dp0%\<script>"
    m_node = re.search(r'(?:"%_prog%"|node)\s+"%dp0%\\([^"]+)"', content, re.IGNORECASE)
    if m_node:
        node_exe = shutil.which("node")
        target_script = (dp0 / m_node.group(1)).resolve()
        if node_exe and target_script.is_file():
            return node_exe, [str(target_script)]

    # 3. Match generic python/binary wrapper: "<exe_path>" "<script_path>" %*
    m_generic = re.search(r'"([^"]+\.exe)"\s+"([^"]+)"', content, re.IGNORECASE)
    if m_generic:
        exe_part = Path(m_generic.group(1))
        script_part = Path(m_generic.group(2))
        if exe_part.is_file() and script_part.is_file():
            return str(exe_part.resolve()), [str(script_part.resolve())]

    # 4. Match generic "%dp0%\node_modules\<package>\bin\<name>.exe"
    m_node_bin = re.search(r'"%dp0%\\(node_modules\\[^"]+\.exe)"', content, re.IGNORECASE)
    if m_node_bin:
        target = (dp0 / m_node_bin.group(1)).resolve()
        if target.is_file():
            return str(target), []

    return None


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

        args = list(cmd[1:])
        if sys.platform == "win32":
            unwrapped = unwrap_batch_file(executable)
            if unwrapped is not None:
                executable, extra_args = unwrapped
                args = extra_args + args

        # Merge environment variables if overrides provided
        proc_env: dict[str, str] | None = None
        if env is not None:
            proc_env = os.environ.copy()
            proc_env.update(env)

        cwd_str = str(cwd) if cwd is not None else None
        return executable, args, cwd_str, proc_env

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
