"""Unit tests for SubprocessRunner and FakeCommandRunner."""

import asyncio
import os
from pathlib import Path
import sys
import pytest

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.domain.exceptions import CommandNotFoundError, DoctorError, GitError, ConfigError, TicketRunnerError
from runner.ports.command_runner import CommandResult, CommandRunner
from tests.fakes.fake_command_runner import FakeCommandRunner


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
