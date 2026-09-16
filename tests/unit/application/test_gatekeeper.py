"""Unit tests for Gatekeeper command execution and diagnostics capture (T028)."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

import pytest

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationReport,
    resolve_shell,
)
from runner.domain.config import VerificationConfig
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle


BUILD_CMD = "npm run build"
TEST_CMD = "pytest -q"


class _LingeringWaitHandle(FakeProcessHandle):
    """Fake handle whose stdout closes immediately but whose process wait lingers."""

    def __init__(self, wait_delay: float) -> None:
        super().__init__(stdout_lines=[], stderr="no output", exit_code=0)
        self._wait_delay = wait_delay
        self.wait_cancelled = False

    async def wait(self) -> int:
        try:
            await asyncio.sleep(self._wait_delay)
        except asyncio.CancelledError:
            self.wait_cancelled = True
            raise
        return 0


def _windows_argv(command: str) -> list[str]:
    """Mirror of the executor's Windows spawn key, used only to register fake handles."""
    return [resolve_shell("win32"), "/d", "/s", "/c", command]


def _assert_windows_shell_call(argv: list[str], command: str) -> None:
    """Assert an argv independently of host resolution: cmd.exe with /d /s /c and the command last."""
    assert argv[0].lower().endswith("cmd.exe")
    assert argv[1:] == ["/d", "/s", "/c", command]


def _verify(
    executor: GatekeeperCommandExecutor, config: VerificationConfig
) -> VerificationReport:
    async def _run() -> VerificationReport:
        return await executor.verify(config)

    return asyncio.run(_run())


# --- AC 1: build-then-test order, per-command timeout, shell argv, passed semantics ---


def test_build_runs_before_test_through_windows_shell(tmp_path: Path) -> None:
    """Build spawns before test, both through cmd.exe, and a clean run yields empty diagnostics."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(_windows_argv(BUILD_CMD), stdout_lines=["building package"])
    fake_runner.register_spawn(_windows_argv(TEST_CMD), stdout_lines=["42 tests passed"])

    executor = GatekeeperCommandExecutor(
        command_runner=fake_runner, cwd=tmp_path, platform="win32"
    )
    report = _verify(
        executor, VerificationConfig(build_cmd=BUILD_CMD, test_cmd=TEST_CMD)
    )

    assert len(fake_runner.spawns) == 2
    _assert_windows_shell_call(fake_runner.spawns[0], BUILD_CMD)
    _assert_windows_shell_call(fake_runner.spawns[1], TEST_CMD)
    assert [inv.cwd for inv in fake_runner.spawn_invocations] == [tmp_path, tmp_path]
    assert report.passed is True
    assert report.diagnostics == ()
    assert report.skipped_commands == ()
    assert [outcome.label for outcome in report.results] == ["build", "test"]
    assert [outcome.exit_code for outcome in report.results] == [0, 0]
    assert all(outcome.timed_out is False for outcome in report.results)
    assert all(outcome.passed is True for outcome in report.results)
    assert "building package" in report.results[0].tail
    assert "42 tests passed" in report.results[1].tail


def test_posix_platform_wraps_commands_in_bin_sh() -> None:
    """Non-Windows platforms dispatch through /bin/sh -c."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(["/bin/sh", "-c", TEST_CMD])

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="linux")
    report = _verify(executor, VerificationConfig(test_cmd=TEST_CMD))

    assert fake_runner.spawns == [["/bin/sh", "-c", TEST_CMD]]
    assert report.passed is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shell resolution test")
def test_windows_shell_resolves_to_absolute_trusted_path() -> None:
    """The default Windows shell is an absolute path, never a cwd-relative bare name."""
    shell = resolve_shell("win32")

    assert Path(shell).is_absolute()
    assert Path(shell).name.lower() == "cmd.exe"


def test_empty_build_command_is_skipped_silently() -> None:
    """An empty (or whitespace-only) build_cmd never spawns and never fails."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(_windows_argv(TEST_CMD))

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    report = _verify(executor, VerificationConfig(build_cmd="", test_cmd=TEST_CMD))

    assert len(fake_runner.spawns) == 1
    _assert_windows_shell_call(fake_runner.spawns[0], TEST_CMD)
    assert report.passed is True
    assert report.skipped_commands == ()
    assert [outcome.label for outcome in report.results] == ["test"]

    blank_runner = FakeCommandRunner()
    blank_runner.register_spawn(_windows_argv(TEST_CMD))
    blank_executor = GatekeeperCommandExecutor(
        command_runner=blank_runner, platform="win32"
    )
    blank_report = _verify(
        blank_executor, VerificationConfig(build_cmd="   ", test_cmd=TEST_CMD)
    )

    assert len(blank_runner.spawns) == 1
    assert blank_report.passed is True
    assert blank_report.skipped_commands == ()


# --- AC 2/3: failure, skip, timeout, and diagnostics shape ---


def test_build_failure_skips_test_and_reports_diagnostics() -> None:
    """A failing non-empty build_cmd skips test_cmd, populates skipped_commands, and reports a block."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(
        _windows_argv(BUILD_CMD),
        stdout_lines=["compile error in module.ts"],
        stderr="link error: missing symbol",
        exit_code=1,
    )

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    report = _verify(
        executor, VerificationConfig(build_cmd=BUILD_CMD, test_cmd=TEST_CMD)
    )

    assert len(fake_runner.spawns) == 1
    _assert_windows_shell_call(fake_runner.spawns[0], BUILD_CMD)
    assert report.passed is False
    assert report.skipped_commands == (TEST_CMD,)
    assert [outcome.label for outcome in report.results] == ["build"]
    outcome = report.results[0]
    assert outcome.exit_code == 1
    assert outcome.timed_out is False
    assert outcome.passed is False
    assert "compile error in module.ts" in outcome.tail
    assert "link error: missing symbol" in outcome.tail

    assert len(report.diagnostics) == 1
    diagnostic = report.diagnostics[0]
    assert diagnostic.startswith(f"$ {BUILD_CMD}")
    assert "exit code 1" in diagnostic
    assert "compile error in module.ts" in diagnostic
    assert "link error: missing symbol" in diagnostic
    assert TEST_CMD not in diagnostic


def test_test_failure_reports_both_command_tails() -> None:
    """A passing build and failing test both keep their tails; diagnostics carry only the failure."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(_windows_argv(BUILD_CMD), stdout_lines=["build ok"])
    fake_runner.register_spawn(
        _windows_argv(TEST_CMD),
        stdout_lines=["FAILED tests/test_foo.py::test_bar"],
        stderr="AssertionError: expected 1 got 2",
        exit_code=2,
    )

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    report = _verify(
        executor, VerificationConfig(build_cmd=BUILD_CMD, test_cmd=TEST_CMD)
    )

    assert len(fake_runner.spawns) == 2
    assert report.passed is False
    assert report.skipped_commands == ()
    assert [outcome.label for outcome in report.results] == ["build", "test"]
    assert "build ok" in report.results[0].tail
    assert "FAILED tests/test_foo.py::test_bar" in report.results[1].tail
    assert "AssertionError: expected 1 got 2" in report.results[1].tail
    assert report.results[1].exit_code == 2

    assert len(report.diagnostics) == 1
    diagnostic = report.diagnostics[0]
    assert diagnostic.startswith(f"$ {TEST_CMD}")
    assert "exit code 2" in diagnostic
    assert "FAILED tests/test_foo.py::test_bar" in diagnostic
    assert "AssertionError: expected 1 got 2" in diagnostic
    assert BUILD_CMD not in diagnostic


def test_build_timeout_terminates_handle_and_skips_test() -> None:
    """A build exceeding timeout_seconds is terminated through its handle and reported timed out."""
    fake_runner = FakeCommandRunner()
    handle = fake_runner.register_spawn(
        _windows_argv(BUILD_CMD),
        stdout_lines=["starting slow build"],
        stderr="held pipe",
        delay=5.0,
    )

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    config = VerificationConfig(
        build_cmd=BUILD_CMD, test_cmd=TEST_CMD, timeout_seconds=1
    )
    report = _verify(executor, config)

    assert handle.terminated is True
    assert len(fake_runner.spawns) == 1
    assert report.passed is False
    assert report.skipped_commands == (TEST_CMD,)
    outcome = report.results[0]
    assert outcome.timed_out is True
    assert outcome.exit_code is None
    assert outcome.passed is False
    assert "held pipe" in outcome.tail
    assert len(report.diagnostics) == 1
    assert report.diagnostics[0].startswith(f"$ {BUILD_CMD}")
    assert "timed out after 1s" in report.diagnostics[0]


def test_timeout_applies_per_command_after_build_passes() -> None:
    """Each command receives its own timeout bound; a hanging test times out after a fast build."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(_windows_argv(BUILD_CMD), stdout_lines=["build ok"])
    test_handle = fake_runner.register_spawn(
        _windows_argv(TEST_CMD),
        stdout_lines=["collecting tests"],
        stderr="test hung",
        delay=5.0,
    )

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    config = VerificationConfig(
        build_cmd=BUILD_CMD, test_cmd=TEST_CMD, timeout_seconds=1
    )
    report = _verify(executor, config)

    assert test_handle.terminated is True
    assert len(fake_runner.spawns) == 2
    assert report.passed is False
    assert report.skipped_commands == ()
    assert [outcome.label for outcome in report.results] == ["build", "test"]
    assert report.results[0].passed is True
    assert report.results[1].timed_out is True
    assert report.results[1].exit_code is None
    assert "test hung" in report.results[1].tail
    assert len(report.diagnostics) == 1
    assert report.diagnostics[0].startswith(f"$ {TEST_CMD}")
    assert "timed out after 1s" in report.diagnostics[0]


def test_process_wait_is_bounded_even_when_stdout_closes() -> None:
    """A command whose stdout closes but whose process lingers still times out and is terminated."""
    fake_runner = FakeCommandRunner()
    handle = _LingeringWaitHandle(wait_delay=5.0)
    fake_runner.register_spawn_handle(_windows_argv(BUILD_CMD), handle)

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    config = VerificationConfig(
        build_cmd=BUILD_CMD, test_cmd=TEST_CMD, timeout_seconds=1
    )
    report = _verify(executor, config)

    assert handle.terminated is True
    assert handle.wait_cancelled is True
    assert report.passed is False
    assert report.skipped_commands == (TEST_CMD,)
    assert report.results[0].timed_out is True
    assert report.results[0].exit_code is None
    assert "no output" in report.results[0].tail
    assert "timed out after 1s" in report.diagnostics[0]


# --- AC 4: trailing-100-line diagnostics window ---


def test_tail_keeps_last_hundred_lines_across_stdout_then_stderr() -> None:
    """Output beyond 100 lines is truncated to the trailing window, stdout before stderr."""
    fake_runner = FakeCommandRunner()
    stdout_lines = [f"stdout-{index}" for index in range(1, 151)]
    stderr = "\n".join(f"stderr-{index}" for index in range(1, 6))
    fake_runner.register_spawn(
        _windows_argv(TEST_CMD), stdout_lines=stdout_lines, stderr=stderr, exit_code=1
    )

    executor = GatekeeperCommandExecutor(command_runner=fake_runner, platform="win32")
    report = _verify(executor, VerificationConfig(test_cmd=TEST_CMD))

    tail_lines = report.results[0].tail.splitlines()
    assert len(tail_lines) == 100
    assert tail_lines[0] == "stdout-56"
    assert tail_lines[-5:] == ["stderr-1", "stderr-2", "stderr-3", "stderr-4", "stderr-5"]
    assert "stdout-55" not in tail_lines

    diagnostic_lines = report.diagnostics[0].splitlines()
    assert diagnostic_lines[0] == f"$ {TEST_CMD}"
    assert diagnostic_lines[1] == "exit code 1"
    assert diagnostic_lines[2:] == tail_lines


# --- AC 5: real SubprocessRunner dispatch on the host platform ---


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shell wrapper integration test")
def test_real_subprocess_runner_executes_commands_through_cmd(tmp_path: Path) -> None:
    """The real adapter proves cmd.exe /d /s /c executes trivial exit-code commands."""
    executor = GatekeeperCommandExecutor(
        command_runner=SubprocessRunner(), cwd=tmp_path, platform="win32"
    )

    passing = _verify(executor, VerificationConfig(test_cmd="exit 0"))
    assert passing.passed is True
    assert passing.diagnostics == ()
    assert passing.results[0].exit_code == 0

    failing = _verify(executor, VerificationConfig(test_cmd="echo boom && exit 3"))
    assert failing.passed is False
    assert failing.results[0].exit_code == 3
    assert "exit code 3" in failing.diagnostics[0]
    assert "boom" in failing.diagnostics[0]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell wrapper integration test")
def test_real_subprocess_runner_executes_commands_through_bin_sh(tmp_path: Path) -> None:
    """The real adapter proves /bin/sh -c executes trivial exit-code commands."""
    executor = GatekeeperCommandExecutor(
        command_runner=SubprocessRunner(), cwd=tmp_path, platform="posix"
    )

    passing = _verify(executor, VerificationConfig(test_cmd="exit 0"))
    assert passing.passed is True
    assert passing.diagnostics == ()
    assert passing.results[0].exit_code == 0

    failing = _verify(executor, VerificationConfig(test_cmd="echo boom && exit 3"))
    assert failing.passed is False
    assert failing.results[0].exit_code == 3
    assert "exit code 3" in failing.diagnostics[0]
    assert "boom" in failing.diagnostics[0]


# --- Public result shape pinned for T031 ---


def test_public_result_shapes_are_constructible() -> None:
    """VerificationReport and CommandOutcome expose the pinned public fields."""
    outcome = CommandOutcome(
        label="test",
        command=TEST_CMD,
        exit_code=None,
        timed_out=True,
        tail="boom",
    )
    report = VerificationReport(
        passed=False,
        results=(outcome,),
        diagnostics=("$ pytest -q\ntimed out after 300s\nboom",),
        skipped_commands=(),
    )

    assert report.passed is False
    assert report.results[0].timed_out is True
    assert report.results[0].exit_code is None
    assert report.diagnostics[0].splitlines()[1] == "timed out after 300s"
    assert report.skipped_commands == ()
