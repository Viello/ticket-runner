"""Unit tests for Gatekeeper command execution and diagnostics capture (T028)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
import sys

import pytest

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationReport,
    inject_test_timeout,
    resolve_shell,
)
from runner.domain.config import VerificationConfig
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle


BUILD_CMD = "npm run build"
TEST_CMD = "pytest -q"


def _make_executor(
    runner: FakeCommandRunner,
    *,
    cwd: Path | None = None,
    platform: str = "win32",
    path_resolver: Callable[[str], str | None] | None = None,
) -> GatekeeperCommandExecutor:
    """Build an executor whose PATH resolver is scripted, independent of the host PATH."""
    return GatekeeperCommandExecutor(
        command_runner=runner,
        cwd=cwd,
        platform=platform,
        path_resolver=path_resolver or (lambda token: rf"C:\tools\{token}.exe"),
    )


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

    executor = _make_executor(fake_runner, cwd=tmp_path)
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

    executor = _make_executor(fake_runner, platform="linux")
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

    executor = _make_executor(fake_runner, platform="win32")
    report = _verify(executor, VerificationConfig(build_cmd="", test_cmd=TEST_CMD))

    assert len(fake_runner.spawns) == 1
    _assert_windows_shell_call(fake_runner.spawns[0], TEST_CMD)
    assert report.passed is True
    assert report.skipped_commands == ()
    assert [outcome.label for outcome in report.results] == ["test"]

    blank_runner = FakeCommandRunner()
    blank_runner.register_spawn(_windows_argv(TEST_CMD))
    blank_executor = _make_executor(blank_runner, platform="win32")
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

    executor = _make_executor(fake_runner, platform="win32")
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

    executor = _make_executor(fake_runner, platform="win32")
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

    executor = _make_executor(fake_runner, platform="win32")
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

    executor = _make_executor(fake_runner, platform="win32")
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

    executor = _make_executor(fake_runner, platform="win32")
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

    executor = _make_executor(fake_runner, platform="win32")
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


# --- T037: leading-token PATH resolution defense-in-depth ---


def test_unresolvable_test_command_reports_command_not_found() -> None:
    """An unresolvable leading token is surfaced as command-not-found, never spawned."""
    fake_runner = FakeCommandRunner()
    executor = _make_executor(
        fake_runner,
        platform="win32",
        path_resolver=lambda token: None if token == "pytest" else rf"C:\tools\{token}.exe",
    )
    report = _verify(executor, VerificationConfig(test_cmd=TEST_CMD))

    assert fake_runner.spawns == []
    assert report.passed is False
    assert report.skipped_commands == ()
    assert [outcome.label for outcome in report.results] == ["test"]
    outcome = report.results[0]
    assert outcome.not_found == "pytest"
    assert outcome.exit_code is None
    assert outcome.timed_out is False
    assert outcome.passed is False

    assert len(report.diagnostics) == 1
    diagnostic = report.diagnostics[0]
    assert diagnostic.startswith(f"$ {TEST_CMD}")
    assert "command not found: 'pytest'" in diagnostic
    assert "exit code" not in diagnostic


def test_unresolvable_build_command_skips_test_command() -> None:
    """A command-not-found build_cmd is a failed build, so test_cmd is skipped."""
    fake_runner = FakeCommandRunner()
    executor = _make_executor(
        fake_runner,
        platform="win32",
        path_resolver=lambda token: None if token == "npm" else rf"C:\tools\{token}.exe",
    )
    report = _verify(
        executor, VerificationConfig(build_cmd=BUILD_CMD, test_cmd=TEST_CMD)
    )

    assert fake_runner.spawns == []
    assert report.passed is False
    assert report.skipped_commands == (TEST_CMD,)
    assert [outcome.label for outcome in report.results] == ["build"]
    assert report.results[0].not_found == "npm"
    assert "command not found: 'npm'" in report.diagnostics[0]


def test_cmd_builtin_leading_token_is_not_resolved() -> None:
    """cmd.exe builtins/control words skip PATH resolution so they never false-positive."""
    fake_runner = FakeCommandRunner()

    def resolver(token: str) -> str | None:
        raise AssertionError(f"resolver must not be called for builtin token '{token}'")

    executor = _make_executor(fake_runner, platform="win32", path_resolver=resolver)
    report = _verify(executor, VerificationConfig(test_cmd="exit 0"))

    assert fake_runner.spawns == [_windows_argv("exit 0")]
    assert report.passed is True
    assert report.diagnostics == ()


def test_only_leading_token_is_resolved_never_full_command() -> None:
    """Resolution targets the token before the first space, never the wrapped command string."""
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(
        _windows_argv("python -m pytest -q"), stdout_lines=["1 passed"]
    )

    resolved_tokens: list[str] = []
    executor = _make_executor(
        fake_runner,
        platform="win32",
        path_resolver=lambda token: (
            resolved_tokens.append(token) or rf"C:\tools\{token}.exe"
        ),
    )
    report = _verify(executor, VerificationConfig(test_cmd="python -m pytest -q"))

    assert resolved_tokens == ["python"]
    assert fake_runner.spawns == [_windows_argv("python -m pytest -q")]
    assert report.passed is True


# --- T064: Silence Window, HANG Classification, and Per-Test Timeout Injection ---


def test_silence_window_kills_hanging_process_and_surfaces_hang() -> None:
    """A subprocess that emits one line then goes silent for > silence_window_seconds is killed with HANG reason."""
    fake_runner = FakeCommandRunner()
    handle = fake_runner.register_spawn(
        _windows_argv(TEST_CMD),
        stdout_lines=["line 1", "line 2"],
        line_delays=[0.0, 0.2],
    )

    executor = _make_executor(fake_runner, platform="win32")

    async def _run() -> CommandOutcome:
        return await executor._execute(
            "test", TEST_CMD, timeout_seconds=5, silence_window_seconds=0.05
        )

    outcome = asyncio.run(_run())

    assert handle.terminated is True
    assert outcome.timed_out is True
    assert outcome.termination_reason == "HANG"
    assert outcome.passed is False
    assert "line 1" in outcome.tail
    assert "line 2" not in outcome.tail


def test_silence_window_resets_on_each_received_line() -> None:
    """The silence window timer resets on each received line, not just process start."""
    fake_runner = FakeCommandRunner()
    # 3 lines with 0.03s delay between them.
    # Total duration = 0.09s > silence_window of 0.06s.
    # Because each gap is 0.03s < 0.06s, it must NOT be killed!
    handle = fake_runner.register_spawn(
        _windows_argv(TEST_CMD),
        stdout_lines=["line 1", "line 2", "line 3"],
        line_delays=[0.03, 0.03, 0.03],
    )

    executor = _make_executor(fake_runner, platform="win32")

    async def _run() -> CommandOutcome:
        return await executor._execute(
            "test", TEST_CMD, timeout_seconds=5, silence_window_seconds=0.06
        )

    outcome = asyncio.run(_run())

    assert handle.terminated is False
    assert outcome.timed_out is False
    assert outcome.termination_reason is None
    assert outcome.exit_code == 0
    assert outcome.passed is True
    assert "line 1\nline 2\nline 3" in outcome.tail


def test_normal_completion_before_silence_window_returns_exit_0() -> None:
    """A subprocess that completes normally in < silence_window_seconds returns exit code 0."""
    fake_runner = FakeCommandRunner()
    handle = fake_runner.register_spawn(
        _windows_argv(TEST_CMD),
        stdout_lines=["all good"],
    )

    executor = _make_executor(fake_runner, platform="win32")
    config = VerificationConfig(test_cmd=TEST_CMD, silence_window_seconds=10)
    report = _verify(executor, config)

    assert handle.terminated is False
    assert report.passed is True
    assert report.results[0].exit_code == 0
    assert report.results[0].termination_reason is None


def test_verify_injects_pytest_timeout_flag() -> None:
    """When per_test_timeout_seconds > 0 and test_cmd contains pytest, --timeout=N is injected."""
    fake_runner = FakeCommandRunner()
    expected_cmd = "pytest --timeout=10 -q"
    fake_runner.register_spawn(
        _windows_argv(expected_cmd),
        stdout_lines=["1 passed in 0.5s"],
    )

    executor = _make_executor(fake_runner, platform="win32")
    config = VerificationConfig(
        test_cmd="pytest -q",
        per_test_timeout_seconds=10,
    )
    report = _verify(executor, config)

    assert report.passed is True
    assert len(fake_runner.spawns) == 1
    _assert_windows_shell_call(fake_runner.spawns[0], expected_cmd)


def test_verify_cargo_test_has_no_flag_injected() -> None:
    """When test_cmd contains cargo test, no extra flag is injected regardless of per_test_timeout_seconds."""
    fake_runner = FakeCommandRunner()
    expected_cmd = "cargo test"
    fake_runner.register_spawn(
        _windows_argv(expected_cmd),
        stdout_lines=["test result: ok"],
    )

    executor = _make_executor(fake_runner, platform="win32")
    config = VerificationConfig(
        test_cmd="cargo test",
        per_test_timeout_seconds=15,
    )
    report = _verify(executor, config)

    assert report.passed is True
    assert len(fake_runner.spawns) == 1
    _assert_windows_shell_call(fake_runner.spawns[0], expected_cmd)


def test_inject_test_timeout_frameworks() -> None:
    """Test framework detection and flag injection across all supported and unsupported frameworks."""
    # pytest
    assert inject_test_timeout("pytest", 5) == "pytest --timeout=5"
    assert inject_test_timeout("pytest -v", 5) == "pytest --timeout=5 -v"
    assert inject_test_timeout("python -m pytest tests/", 5) == "python -m pytest --timeout=5 tests/"

    # jest / vitest
    assert inject_test_timeout("jest", 3) == "jest --testTimeout=3000"
    assert inject_test_timeout("npx jest --bail", 3) == "npx jest --testTimeout=3000 --bail"
    assert inject_test_timeout("vitest run", 4) == "vitest --testTimeout=4000 run"

    # go test
    assert inject_test_timeout("go test ./...", 30) == "go test -timeout 30s ./..."

    # unsupported: cargo test, dotnet test, unknown
    assert inject_test_timeout("cargo test", 10) == "cargo test"
    assert inject_test_timeout("dotnet test", 10) == "dotnet test"
    assert inject_test_timeout("make test", 10) == "make test"

    # disabled (<= 0)
    assert inject_test_timeout("pytest -q", 0) == "pytest -q"
    assert inject_test_timeout("pytest -q", -5) == "pytest -q"


def test_inject_test_timeout_security_safeguards() -> None:
    """Verify timeout flag injection safely constructs commands without shell evaluation or argument injection."""
    # Boolean or non-integer per_test_timeout_seconds is ignored
    assert inject_test_timeout("pytest", True) == "pytest"  # type: ignore[arg-type]
    assert inject_test_timeout("pytest", "10; rm -rf /") == "pytest"  # type: ignore[arg-type]

    # Malicious shell characters in test_cmd are not evaluated
    res = inject_test_timeout("pytest `whoami` $(id)", 10)
    assert res == "pytest --timeout=10 `whoami` $(id)"

    # Flag is never placed at index 0 where it would shadow executable
    injected = inject_test_timeout("pytest -q", 10)
    from runner.application.gatekeeper import leading_command_token

    assert leading_command_token(injected) == "pytest"


def test_process_tree_termination_handles_already_exited_process_cleanly() -> None:
    """Process tree termination cleanly handles already-exited processes without unhandled exceptions."""
    fake_runner = FakeCommandRunner()

    class ExitedHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(wait_delay=5.0)

        async def terminate(self) -> None:
            self.terminated = True
            raise ProcessLookupError("process already exited")

    handle = ExitedHandle()
    fake_runner.register_spawn_handle(_windows_argv(TEST_CMD), handle)

    executor = _make_executor(fake_runner, platform="win32")

    async def _run() -> CommandOutcome:
        return await executor._execute(
            "test", TEST_CMD, timeout_seconds=1, silence_window_seconds=0.01
        )

    # Must complete cleanly without raising ProcessLookupError
    outcome = asyncio.run(_run())
    assert outcome.termination_reason == "HANG"
    assert outcome.timed_out is True


def test_format_diagnostic_hang_rendering() -> None:
    """_format_diagnostic renders hung status when termination_reason is HANG."""
    from runner.application.gatekeeper import _format_diagnostic

    outcome = CommandOutcome(
        label="test",
        command="pytest -q",
        exit_code=None,
        timed_out=True,
        tail="some test output",
        termination_reason="HANG",
    )
    diagnostic = _format_diagnostic(outcome, timeout_seconds=300, silence_window_seconds=60)
    assert "$ pytest -q" in diagnostic
    assert "hung (silence window of 60s exceeded)" in diagnostic
    assert "some test output" in diagnostic

