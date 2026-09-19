"""Unit tests for SubprocessRunner and FakeCommandRunner."""

import asyncio
import os
from pathlib import Path
import sys
import pytest

from runner.adapters.cli.subprocess_runner import SubprocessRunner, unwrap_batch_file
from runner.adapters.cli.windows_job import WindowsJobObject
from runner.domain.exceptions import CommandNotFoundError, DoctorError, GitError, ConfigError, TicketRunnerError
from runner.ports.command_runner import CommandResult, CommandRunner, ProcessHandle
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle


# --- Exception Hierarchy Tests ---

def test_exception_hierarchy() -> None:
    """Verify that domain exceptions properly inherit from TicketRunnerError."""
    assert issubclass(DoctorError, TicketRunnerError)
    assert issubclass(GitError, TicketRunnerError)
    assert issubclass(ConfigError, TicketRunnerError)
    assert issubclass(CommandNotFoundError, TicketRunnerError)

    err = CommandNotFoundError("missing_cmd")
    assert err.command == "missing_cmd"
    assert "missing_cmd" in str(err)


# --- SubprocessRunner Tests ---

def test_subprocess_runner_satisfies_protocol() -> None:
    """Verify that SubprocessRunner satisfies the CommandRunner Protocol."""
    runner = SubprocessRunner()
    assert isinstance(runner, CommandRunner)


def test_subprocess_runner_executes_and_captures_stdout() -> None:
    """Verify SubprocessRunner executes Python command and captures stdout."""
    runner = SubprocessRunner()
    result = asyncio.run(runner.run([sys.executable, "-c", "print('hello from subprocess')"]))

    assert isinstance(result, CommandResult)
    assert result.exit_code == 0
    assert result.success is True
    assert result.stdout.strip() == "hello from subprocess"
    assert result.stderr == ""


def test_subprocess_runner_captures_stderr_and_exit_code() -> None:
    """Verify SubprocessRunner captures stderr and non-zero returncode."""
    runner = SubprocessRunner()
    code = (
        "import sys; "
        "sys.stdout.write('some out\\n'); "
        "sys.stderr.write('some err\\n'); "
        "sys.exit(42)"
    )
    result = asyncio.run(runner.run([sys.executable, "-c", code]))

    assert result.exit_code == 42
    assert result.success is False
    assert result.stdout.strip() == "some out"
    assert result.stderr.strip() == "some err"


def test_subprocess_runner_respects_cwd(tmp_path: Path) -> None:
    """Verify SubprocessRunner runs command in specified cwd."""
    runner = SubprocessRunner()
    code = "import os; print(os.getcwd())"
    result = asyncio.run(runner.run([sys.executable, "-c", code], cwd=tmp_path))

    assert result.exit_code == 0
    # Normalize paths for Windows case/slash comparison
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve()


def test_subprocess_runner_respects_env() -> None:
    """Verify SubprocessRunner passes environment variables to subprocess."""
    runner = SubprocessRunner()
    code = "import os; print(os.environ.get('TEST_VAR_KEY', 'NOT_SET'))"
    result = asyncio.run(
        runner.run([sys.executable, "-c", code], env={"TEST_VAR_KEY": "EXPECTED_VALUE"})
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "EXPECTED_VALUE"


def test_subprocess_runner_raises_on_unresolved_command() -> None:
    """Verify SubprocessRunner raises CommandNotFoundError when binary does not exist."""
    runner = SubprocessRunner()
    with pytest.raises(CommandNotFoundError) as exc_info:
        asyncio.run(runner.run(["nonexistent_binary_xyz_12345"]))

    assert exc_info.value.command == "nonexistent_binary_xyz_12345"


def test_subprocess_runner_raises_on_empty_cmd() -> None:
    """Verify SubprocessRunner raises ValueError if cmd list is empty."""
    runner = SubprocessRunner()
    with pytest.raises(ValueError, match="Command list cannot be empty"):
        asyncio.run(runner.run([]))


# --- FakeCommandRunner Tests ---

def test_fake_command_runner_satisfies_protocol() -> None:
    """Verify that FakeCommandRunner satisfies the CommandRunner Protocol."""
    fake = FakeCommandRunner()
    assert isinstance(fake, CommandRunner)


def test_fake_command_runner_default_result() -> None:
    """Verify FakeCommandRunner returns default result when unscripted."""
    fake = FakeCommandRunner()
    result = asyncio.run(fake.run(["git", "status"]))

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert len(fake.invocations) == 1
    assert fake.invocations[0].cmd == ["git", "status"]
    assert fake.commands == [["git", "status"]]


def test_fake_command_runner_registered_exact_command() -> None:
    """Verify FakeCommandRunner returns registered result for matching command."""
    fake = FakeCommandRunner()
    fake.register(["git", "status", "--porcelain"], exit_code=0, stdout=" M file.txt\n")

    result = asyncio.run(fake.run(["git", "status", "--porcelain"]))
    assert result.exit_code == 0
    assert result.stdout == " M file.txt\n"
    assert result.stderr == ""


def test_fake_command_runner_registered_string_command() -> None:
    """Verify FakeCommandRunner can register via string command."""
    fake = FakeCommandRunner()
    fake.register("git rev-parse HEAD", exit_code=0, stdout="abc1234\n")

    result = asyncio.run(fake.run(["git", "rev-parse", "HEAD"]))
    assert result.exit_code == 0
    assert result.stdout == "abc1234\n"


def test_fake_command_runner_records_cwd_and_env(tmp_path: Path) -> None:
    """Verify FakeCommandRunner records cwd and env for assertions."""
    fake = FakeCommandRunner()
    env = {"MY_VAR": "VAL"}
    asyncio.run(fake.run(["opencode", "--version"], cwd=tmp_path, env=env))

    assert len(fake.invocations) == 1
    inv = fake.invocations[0]
    assert inv.cmd == ["opencode", "--version"]
    assert inv.cwd == tmp_path
    assert inv.env == env


# --- ProcessHandle Protocol Conformance Tests ---

def test_handles_satisfy_process_handle_protocol() -> None:
    """Verify that both real SubprocessProcessHandle and FakeProcessHandle satisfy ProcessHandle."""
    fake_handle = FakeProcessHandle()
    assert isinstance(fake_handle, ProcessHandle)

    runner = SubprocessRunner()
    async def _check_real() -> None:
        handle = await runner.spawn([sys.executable, "-c", "pass"])
        assert isinstance(handle, ProcessHandle)
        await handle.wait()

    asyncio.run(_check_real())


# --- SubprocessRunner Streaming Spawn Tests ---

def test_subprocess_runner_spawn_streams_stdout_in_order() -> None:
    """Verify SubprocessRunner.spawn yields stdout lines in order and propagates exit code."""
    runner = SubprocessRunner()
    code = "import sys; print('line 1'); print('line 2'); print('line 3')"

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        lines = []
        async for line in handle.stdout_lines():
            lines.append(line)
        exit_code = await handle.wait()

        assert lines == ["line 1", "line 2", "line 3"]
        assert exit_code == 0
        assert handle.pid > 0

    asyncio.run(_run())


def test_subprocess_runner_spawn_strips_crlf_and_lf() -> None:
    """Verify SubprocessRunner.spawn strips both Windows CRLF and POSIX LF line endings."""
    runner = SubprocessRunner()
    code = (
        "import sys; "
        "sys.stdout.buffer.write(b'crlf_line\\r\\nlf_line\\nlast_line\\r\\n'); "
        "sys.stdout.buffer.flush()"
    )

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        lines = [line async for line in handle]
        exit_code = await handle.wait()

        assert lines == ["crlf_line", "lf_line", "last_line"]
        assert exit_code == 0

    asyncio.run(_run())


def test_subprocess_runner_spawn_handles_long_stdout_lines() -> None:
    """Verify SubprocessRunner.spawn handles stdout lines exceeding asyncio's default 64KB buffer limit."""
    runner = SubprocessRunner()
    # 10 MB line followed by another line, far exceeding asyncio's default 64KB (65536 bytes) limit
    code = (
        "import sys; "
        "sys.stdout.write('A' * (10 * 1024 * 1024) + '\\n'); "
        "sys.stdout.write('second line\\r\\n'); "
        "sys.stdout.flush()"
    )

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        lines = [line async for line in handle.stdout_lines()]
        exit_code = await handle.wait()

        assert len(lines) == 2
        assert len(lines[0]) == 10 * 1024 * 1024
        assert lines[1] == "second line"
        assert exit_code == 0

    asyncio.run(_run())


def test_subprocess_runner_spawn_respects_cwd_and_env(tmp_path: Path) -> None:
    """Verify SubprocessRunner.spawn executes in designated cwd and inherits passed env."""
    runner = SubprocessRunner()
    code = (
        "import os; "
        "print(os.getcwd()); "
        "print(os.environ.get('SPAWN_TEST_KEY', 'NOT_SET'))"
    )

    async def _run() -> None:
        handle = await runner.spawn(
            [sys.executable, "-c", code],
            cwd=tmp_path,
            env={"SPAWN_TEST_KEY": "SPAWN_VALUE_123"},
        )
        lines = [line async for line in handle]
        exit_code = await handle.wait()

        assert exit_code == 0
        assert len(lines) == 2
        assert Path(lines[0]).resolve() == tmp_path.resolve()
        assert lines[1] == "SPAWN_VALUE_123"

    asyncio.run(_run())


def test_subprocess_runner_spawn_stdin_is_devnull() -> None:
    """Verify spawned process receives DEVNULL stdin so processes cannot block on read."""
    runner = SubprocessRunner()
    code = (
        "import sys; "
        "data = sys.stdin.read(); "
        "print(f'stdin_len:{len(data)}')"
    )

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        lines = [line async for line in handle]
        exit_code = await handle.wait()

        assert exit_code == 0
        assert lines == ["stdin_len:0"]

    asyncio.run(_run())


def test_subprocess_runner_spawn_concurrent_stderr_drain_no_deadlock() -> None:
    """Verify concurrent stderr draining prevents deadlock when child process floods stderr."""
    runner = SubprocessRunner()
    # Child writes 100KB to stderr while writing a few stdout lines
    code = (
        "import sys, time\n"
        "for i in range(5):\n"
        "    sys.stderr.write('E' * 20000)\n"
        "    sys.stderr.flush()\n"
        "    sys.stdout.write(f'out_{i}\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(0.01)\n"
    )

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        lines = []
        async for line in handle.stdout_lines():
            lines.append(line)
            # Artificial slow consumer delay
            await asyncio.sleep(0.02)

        exit_code = await handle.wait()

        assert lines == ["out_0", "out_1", "out_2", "out_3", "out_4"]
        assert exit_code == 0
        # 5 * 20000 = 100000 bytes
        assert len(handle.stderr) == 100000
        assert handle.stderr == "E" * 100000

    asyncio.run(_run())


def test_subprocess_runner_spawn_terminate_bounded_wait() -> None:
    """Verify terminate() kills the process tree within a bounded wait."""
    runner = SubprocessRunner()
    code = "import time; time.sleep(60)"

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        assert handle.pid > 0

        # Terminate should complete promptly without waiting for the 60s sleep
        start_time = asyncio.get_event_loop().time()
        await handle.terminate()
        duration = asyncio.get_event_loop().time() - start_time

        assert duration < 5.0
        exit_code = await handle.wait()
        # Non-zero exit code indicating termination
        assert exit_code != 0

    asyncio.run(_run())


def test_subprocess_runner_spawn_validations() -> None:
    """Verify SubprocessRunner.spawn rejects invalid arguments and missing binaries."""
    runner = SubprocessRunner()

    with pytest.raises(TypeError, match="Command must be a list of strings"):
        asyncio.run(runner.spawn("echo hi"))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Command list cannot be empty"):
        asyncio.run(runner.spawn([]))

    with pytest.raises(CommandNotFoundError):
        asyncio.run(runner.spawn(["nonexistent_binary_xyz_99999"]))


# --- FakeCommandRunner Streaming Spawn Tests ---

def test_fake_command_runner_spawn_default_handle() -> None:
    """Verify FakeCommandRunner.spawn returns default handle and records invocation."""
    fake = FakeCommandRunner()

    async def _run() -> None:
        handle = await fake.spawn(["opencode", "run", "do something"])
        assert isinstance(handle, ProcessHandle)
        lines = [line async for line in handle]
        assert lines == []
        assert await handle.wait() == 0
        assert handle.stderr == ""
        assert handle.pid == 12345

        assert len(fake.spawn_invocations) == 1
        assert fake.spawn_invocations[0].cmd == ["opencode", "run", "do something"]
        assert fake.spawns == [["opencode", "run", "do something"]]

    asyncio.run(_run())


def test_fake_command_runner_spawn_scripted_lines_and_stderr() -> None:
    """Verify FakeCommandRunner.spawn serves registered stdout lines, stderr, and exit code."""
    fake = FakeCommandRunner()
    fake.register_spawn(
        ["opencode", "run", "--format", "json"],
        stdout_lines=['{"type":"step_start"}\r\n', '{"type":"step_finish"}\n'],
        stderr="warning from stderr\n",
        exit_code=42,
        pid=9999,
    )

    async def _run() -> None:
        handle = await fake.spawn(["opencode", "run", "--format", "json"])
        lines = [line async for line in handle.stdout_lines()]
        exit_code = await handle.wait()

        assert lines == ['{"type":"step_start"}', '{"type":"step_finish"}']
        assert exit_code == 42
        assert handle.stderr == "warning from stderr\n"
        assert handle.pid == 9999

    asyncio.run(_run())


def test_fake_command_runner_spawn_terminate() -> None:
    """Verify FakeProcessHandle marks terminated and stops iteration."""
    fake = FakeCommandRunner()
    handle = fake.register_spawn(
        "long-running-cmd",
        stdout_lines=["line 1", "line 2", "line 3"],
    )

    async def _run() -> None:
        spawned_handle = await fake.spawn(["long-running-cmd"])
        assert spawned_handle is handle
        assert not handle.terminated

        await spawned_handle.terminate()
        assert handle.terminated

        # After termination, iteration halts
        lines = [line async for line in spawned_handle]
        assert lines == []

    asyncio.run(_run())


def test_fake_command_runner_spawn_records_argv_list(tmp_path: Path) -> None:
    """Verify FakeCommandRunner preserves argv as a list and records cwd/env."""
    fake = FakeCommandRunner()
    cmd = ["opencode", "run", "--format", "json", "implement ticket"]
    env = {"TOKEN_VAR": "SECRET"}

    async def _run() -> None:
        await fake.spawn(cmd, cwd=tmp_path, env=env)
        assert len(fake.spawn_invocations) == 1
        inv = fake.spawn_invocations[0]
        assert isinstance(inv.cmd, list)
        assert inv.cmd == cmd
        assert inv.cwd == tmp_path
        assert inv.env == env

    asyncio.run(_run())


def test_fake_command_runner_spawn_validations() -> None:
    """Verify FakeCommandRunner.spawn validates input types."""
    fake = FakeCommandRunner()

    with pytest.raises(TypeError, match="Command must be a list of strings"):
        asyncio.run(fake.spawn("echo hi"))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="Command list cannot be empty"):
        asyncio.run(fake.spawn([]))


# --- Windows Job Object and SubprocessProcessHandle Tests ---

def test_windows_job_object_create_and_lifecycle() -> None:
    """Verify WindowsJobObject creates, assigns, and idempotently closes on Windows."""
    if sys.platform != "win32":
        pytest.skip("Windows-only test")

    job = WindowsJobObject.create()
    assert job is not None
    assert job.is_open is True
    assert job.handle is not None

    # Self-assignment of the current Python test process PID
    assigned = job.assign_process(os.getpid())
    assert isinstance(assigned, bool)

    job.close()
    assert job.is_open is False
    assert job.handle is None
    # Idempotent close
    job.close()
    assert job.is_open is False


def test_windows_job_object_non_windows_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify WindowsJobObject.create returns None on non-Windows platforms."""
    monkeypatch.setattr(sys, "platform", "linux")
    job = WindowsJobObject.create()
    assert job is None


def _is_pid_running_win32(pid: int) -> bool:
    """Helper to check if a process is still active on Windows."""
    if sys.platform != "win32":
        return False
    import ctypes
    import ctypes.wintypes
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return False
    exit_code = ctypes.wintypes.DWORD()
    kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
    kernel32.CloseHandle(h)
    return exit_code.value == 259  # STILL_ACTIVE


def test_subprocess_handle_reaps_detached_grandchild_on_terminate() -> None:
    """A spawned process that detaches a grandchild is reaped when terminate() is called."""
    if sys.platform != "win32":
        pytest.skip("Windows-only test")

    runner = SubprocessRunner()
    # Child script spawns a detached grandchild process, prints its PID, and sleeps
    child_code = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(100)'], "
        "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
        "print(p.pid, flush=True)\n"
        "time.sleep(100)\n"
    )

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", child_code])
        assert handle.job is not None
        assert handle.job.is_open is True

        grandchild_pid = None
        async for line in handle.stdout_lines():
            line_str = line.strip()
            if line_str.isdigit():
                grandchild_pid = int(line_str)
                break

        assert grandchild_pid is not None
        assert _is_pid_running_win32(grandchild_pid) is True

        await handle.terminate()
        exit_code = await handle.wait()
        assert exit_code != 0
        assert handle.job is None

        # Allow OS kernel moment to finish process cleanup
        await asyncio.sleep(0.5)
        assert _is_pid_running_win32(grandchild_pid) is False

    asyncio.run(_run())


def test_subprocess_handle_reaps_detached_grandchild_on_normal_exit() -> None:
    """A spawned process whose child detaches is reaped when the process exits normally and job closes."""
    if sys.platform != "win32":
        pytest.skip("Windows-only test")

    runner = SubprocessRunner()
    # Child script spawns a detached grandchild and exits cleanly with 0
    child_code = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(100)'], "
        "creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n"
        "print(p.pid, flush=True)\n"
        "sys.exit(0)\n"
    )

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", child_code])

        grandchild_pid = None
        async for line in handle.stdout_lines():
            line_str = line.strip()
            if line_str.isdigit():
                grandchild_pid = int(line_str)
                break

        assert grandchild_pid is not None
        # Wait for normal child exit (should close the Job Object)
        exit_code = await handle.wait()
        assert exit_code == 0
        assert handle.job is None

        # Grandchild should be reaped because Job Object was closed
        await asyncio.sleep(0.5)
        assert _is_pid_running_win32(grandchild_pid) is False

    asyncio.run(_run())


def test_subprocess_handle_taskkill_fallback_when_job_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the Job Object is unavailable (job=None), terminate() falls back to taskkill /T /F."""
    if sys.platform != "win32":
        pytest.skip("Windows-only test")

    runner = SubprocessRunner()
    # Force job=None on Windows
    monkeypatch.setattr(WindowsJobObject, "create", classmethod(lambda cls: None))

    taskkill_commands: list[list[str]] = []
    original_exec = asyncio.create_subprocess_exec

    async def _spy_exec(*args, **kwargs):
        if args and args[0] == "taskkill":
            taskkill_commands.append(list(args))
        return await original_exec(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _spy_exec)

    code = "import time; time.sleep(60)"

    async def _run() -> None:
        handle = await runner.spawn([sys.executable, "-c", code])
        assert handle.job is None

        await handle.terminate()
        await handle.wait()

        assert any(
            cmd[:2] == ["taskkill", "/PID"] and "/T" in cmd and "/F" in cmd
            for cmd in taskkill_commands
        )

    asyncio.run(_run())


# --- Batch File Wrapper Unwrapping and Multiline Argument Tests ---

def test_unwrap_batch_file_returns_none_for_non_batch_or_missing(tmp_path: Path) -> None:
    """Non-.cmd/.bat files or missing files return None."""
    non_batch = tmp_path / "app.exe"
    non_batch.touch()
    assert unwrap_batch_file(str(non_batch)) is None
    assert unwrap_batch_file(str(tmp_path / "missing.cmd")) is None


def test_unwrap_batch_file_npm_binary_pattern(tmp_path: Path) -> None:
    """Resolves npm-style binary wrapper '%dp0%\\node_modules\\...\\name.exe' to real PE binary."""
    bin_dir = tmp_path / "node_modules" / "opencode-ai" / "bin"
    bin_dir.mkdir(parents=True)
    real_exe = bin_dir / "opencode.exe"
    real_exe.touch()

    cmd_file = tmp_path / "opencode.cmd"
    cmd_file.write_text(
        '@ECHO off\n"%dp0%\\node_modules\\opencode-ai\\bin\\opencode.exe" %*\n',
        encoding="utf-8",
    )

    result = unwrap_batch_file(str(cmd_file))
    assert result is not None
    target_exe, extra_args = result
    assert Path(target_exe).resolve() == real_exe.resolve()
    assert extra_args == []


def test_unwrap_batch_file_node_script_pattern(tmp_path: Path) -> None:
    """Resolves npm-style node script wrapper '%_prog%' '%dp0%\\dist\\cli.js'."""
    script_dir = tmp_path / "dist"
    script_dir.mkdir(parents=True)
    script_file = script_dir / "cli.js"
    script_file.touch()

    cmd_file = tmp_path / "tool.cmd"
    cmd_file.write_text(
        '@ECHO off\n"%_prog%" "%dp0%\\dist\\cli.js" %*\n',
        encoding="utf-8",
    )

    result = unwrap_batch_file(str(cmd_file))
    assert result is not None
    target_exe, extra_args = result
    assert "node" in Path(target_exe).stem.lower()
    assert len(extra_args) == 1
    assert Path(extra_args[0]).resolve() == script_file.resolve()


def test_subprocess_runner_preserves_multiline_arg_via_batch_wrapper(tmp_path: Path) -> None:
    """Verify that SubprocessRunner unwraps Windows batch scripts so multiline prompt arguments are not truncated."""
    if sys.platform != "win32":
        pytest.skip("Windows batch wrapper unwrap test")

    runner = SubprocessRunner()

    record_py = tmp_path / "record_argv.py"
    received_json = tmp_path / "received.json"
    record_py.write_text(
        "import sys, json\n"
        f"with open(r'{received_json}', 'w', encoding='utf-8') as f:\n"
        "    json.dump(sys.argv[1:], f)\n",
        encoding="utf-8",
    )

    fake_cmd = tmp_path / "fake_tool.cmd"
    fake_cmd.write_text(
        f'@ECHO off\n"{sys.executable}" "{record_py}" %*\n',
        encoding="utf-8",
    )

    multiline_prompt = (
        "# Ticket Task: T001 — Smoke test\n\n"
        "## Execution Skill & Discipline\n"
        "Before writing or modifying any code, read AGENTS.md.\n\n"
        "## Active Ticket Details\n"
        "Requirements here."
    )

    async def _run() -> None:
        handle = await runner.spawn([str(fake_cmd), "--auto", multiline_prompt])
        exit_code = await handle.wait()
        assert exit_code == 0

        import json
        data = json.loads(received_json.read_text(encoding="utf-8"))
        assert len(data) == 2
        assert data[0] == "--auto"
        assert data[1] == multiline_prompt

    asyncio.run(_run())



