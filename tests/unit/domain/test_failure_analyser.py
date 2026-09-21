"""Unit tests for failure analyser and isolation probe (T065)."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from runner.domain.config import VerificationConfig
from runner.domain.failure_analyser import (
    FailureDiagnostic,
    analyse,
    build_isolation_command,
    extract_error_fingerprints,
    extract_test_identifiers,
    interpolate_isolation_command,
)


def _make_config(
    test_cmd: str = "pytest",
    isolation_cmd: str = "",
    timeout_seconds: int = 30,
) -> VerificationConfig:
    return VerificationConfig(
        test_cmd=test_cmd,
        isolation_cmd=isolation_cmd,
        timeout_seconds=timeout_seconds,
    )


class TestFailureClassification:
    """Acceptance criteria and classification priority tests."""

    def test_hang_classification_regardless_of_output(self) -> None:
        """analyse() given a HANG termination reason returns label == 'HANG' regardless of output content."""
        output = [
            "ModuleNotFoundError: No module named 'foo'",
            "FAILED tests/test_a.py::test_1 - AssertionError",
            "FAILED tests/test_b.py::test_2 - AssertionError",
            "FAILED tests/test_c.py::test_3 - AssertionError",
            "FAILED tests/test_d.py::test_4 - AssertionError",
            "FAILED tests/test_e.py::test_5 - AssertionError",
        ]
        config = _make_config(test_cmd="pytest")
        diag = analyse(output, exit_code=None, termination_reason="HANG", config=config)
        assert diag.label == "HANG"
        assert "Stuck-Test-Suite Runbook" in diag.suggested_action

    def test_stalled_termination_reason_treated_as_hang(self) -> None:
        """STALLED is treated as HANG classification."""
        config = _make_config()
        diag = analyse(["some output"], exit_code=1, termination_reason="STALLED", config=config)
        assert diag.label == "HANG"

    def test_env_classification_on_first_line(self) -> None:
        """analyse() given pytest output with ModuleNotFoundError on the first line returns label == 'ENV'."""
        output = [
            "ModuleNotFoundError: No module named 'missing_package'",
            "Traceback (most recent call last):",
            "  File 'run.py', line 1",
        ]
        config = _make_config(test_cmd="pytest")
        diag = analyse(output, exit_code=1, termination_reason=None, config=config)
        assert diag.label == "ENV"
        assert "ModuleNotFoundError" in diag.top_errors

    def test_env_priority_over_cascade(self) -> None:
        """An ENV error appearing before test identifier lines classifies as ENV even if there are many FAILED lines."""
        output = [
            "ImportError: cannot import name 'helper' from 'utils'",
            "FAILED tests/test_1.py::test_one - AssertionError",
            "FAILED tests/test_2.py::test_two - AssertionError",
            "FAILED tests/test_3.py::test_three - AssertionError",
            "FAILED tests/test_4.py::test_four - AssertionError",
            "FAILED tests/test_5.py::test_five - AssertionError",
            "FAILED tests/test_6.py::test_six - AssertionError",
        ]
        config = _make_config()
        diag = analyse(output, exit_code=1, termination_reason=None, config=config)
        assert diag.label == "ENV"

    def test_cascade_classification_with_repeating_error(self) -> None:
        """analyse() given pytest output with 10 FAILED entries sharing AssertionError returns label == 'CASCADE' and top_errors[0] == 'AssertionError'."""
        output = [
            f"FAILED tests/test_{i}.py::test_func_{i} - AssertionError: assert False"
            for i in range(10)
        ]
        config = _make_config(test_cmd="pytest")
        # Provide a mock probe_runner so subprocess isn't called for real
        probe_runner = MagicMock(return_value="isolation rerun output")
        diag = analyse(
            output,
            exit_code=1,
            termination_reason=None,
            config=config,
            probe_runner=probe_runner,
        )
        assert diag.label == "CASCADE"
        assert diag.top_errors[0] == "AssertionError"
        assert diag.root_tests == ["tests/test_0.py::test_func_0"]
        assert diag.isolation_output == "isolation rerun output"

    def test_flaky_fallback_classification(self) -> None:
        """analyse() given a non-zero exit with no recognisable pattern returns label == 'FLAKY'."""
        output = [
            "Random error occurred during test execution",
            "Exit signal 1",
        ]
        config = _make_config()
        diag = analyse(output, exit_code=1, termination_reason=None, config=config)
        assert diag.label == "FLAKY"


class TestLogTailAndBounds:
    """Bounded log tail checks."""

    def test_log_tail_bounded_to_100_lines(self) -> None:
        """log_tail contains at most 100 lines."""
        output = [f"line {i}" for i in range(250)]
        config = _make_config()
        diag = analyse(output, exit_code=1, termination_reason=None, config=config)
        assert len(diag.log_tail) == 100
        assert diag.log_tail[0] == "line 150"
        assert diag.log_tail[-1] == "line 249"

    def test_log_tail_preserves_short_output(self) -> None:
        """log_tail preserves all lines when under 100 lines."""
        output = ["line 1", "line 2", "line 3"]
        config = _make_config()
        diag = analyse(output, exit_code=1, termination_reason=None, config=config)
        assert diag.log_tail == ["line 1", "line 2", "line 3"]


class TestTestIdentifierExtraction:
    """Test identifier extraction patterns across test runners."""

    def test_extract_first_pytest_identifier(self) -> None:
        """Extracts first pytest identifier and parses the first occurrence, not the last."""
        output = [
            "collected 3 items",
            "FAILED tests/unit/domain/test_foo.py::test_first - AssertionError",
            "FAILED tests/unit/domain/test_bar.py::test_second - TypeError",
        ]
        test_ids = extract_test_identifiers(output)
        assert len(test_ids) >= 1
        assert test_ids[0] == "tests/unit/domain/test_foo.py::test_first"

    def test_extract_jest_identifier(self) -> None:
        """Extracts jest 'describe > test name' pattern."""
        output = [
            "FAIL src/auth.test.ts",
            "  ● Authentication > Login > should reject invalid password",
            "    expect(received).toBe(expected)",
        ]
        test_ids = extract_test_identifiers(output)
        assert len(test_ids) >= 1
        assert test_ids[0] == "Authentication > Login > should reject invalid password"

    def test_extract_go_test_identifier(self) -> None:
        """Extracts go test '--- FAIL: TestFoo' pattern."""
        output = [
            "=== RUN   TestLogin",
            "--- FAIL: TestLogin (0.02s)",
            "=== RUN   TestLogout",
            "--- FAIL: TestLogout (0.01s)",
        ]
        test_ids = extract_test_identifiers(output)
        assert len(test_ids) >= 1
        assert test_ids[0] == "TestLogin"

    def test_extract_cargo_test_identifier(self) -> None:
        """Extracts cargo test 'test test_fn ... FAILED' pattern."""
        output = [
            "running 2 tests",
            "test tests::test_parse ... FAILED",
            "test tests::test_render ... ok",
        ]
        test_ids = extract_test_identifiers(output)
        assert len(test_ids) >= 1
        assert test_ids[0] == "tests::test_parse"

    def test_empty_when_no_identifier_found(self) -> None:
        """If none is found, root_tests is an empty list — not an error."""
        output = ["Build failed before tests started", "fatal error: compiler crashed"]
        test_ids = extract_test_identifiers(output)
        assert test_ids == []


class TestErrorFingerprints:
    """Extraction of top 3 unique error classes."""

    def test_extract_top_3_unique_fingerprints(self) -> None:
        output = [
            "AssertionError: 1 != 2",
            "AssertionError: 2 != 3",
            "AssertionError: 3 != 4",
            "TypeError: unsupported operand",
            "TypeError: invalid argument",
            "KeyError: 'missing'",
            "ValueError: bad input",
        ]
        errors = extract_error_fingerprints(output)
        assert errors == ["AssertionError", "TypeError", "KeyError"]


class TestIsolationCommandBuilder:
    """Acceptance criteria: isolation command builder returns template string without executing anything."""

    def test_pytest_template(self) -> None:
        assert build_isolation_command("pytest tests/") == "pytest {test_id} -x"

    def test_python_m_pytest_template(self) -> None:
        assert build_isolation_command("python -m pytest tests/ -v") == "pytest {test_id} -x"

    def test_jest_template(self) -> None:
        assert (
            build_isolation_command("npm test -- jest")
            == 'npx jest --testNamePattern "{test_name}"'
        )

    def test_vitest_template(self) -> None:
        assert (
            build_isolation_command("npx vitest run")
            == 'npx vitest --testNamePattern "{test_name}"'
        )

    def test_go_test_template(self) -> None:
        assert (
            build_isolation_command("go test ./...")
            == "go test -run {test_name} ./..."
        )

    def test_cargo_test_template(self) -> None:
        assert (
            build_isolation_command("cargo test --workspace")
            == "cargo test {test_name}"
        )

    def test_unknown_runner_returns_none(self) -> None:
        assert build_isolation_command("make test") is None

    def test_explicit_isolation_cmd_override(self) -> None:
        assert (
            build_isolation_command("pytest", isolation_cmd="custom-runner {test_id} --once")
            == "custom-runner {test_id} --once"
        )


class TestSecurityInterpolationAndSubprocess:
    """Security verification: command interpolation and subprocess invocation without shell=True."""

    def test_safe_interpolation_prevents_command_injection(self) -> None:
        """Metacharacters in test_id do not trigger shell evaluation."""
        template = "pytest {test_id} -x"
        malicious_test_id = "test_foo.py::test_fn; echo pwned"
        argv = interpolate_isolation_command(template, test_id=malicious_test_id)
        # Should be an argument vector where 'test_foo.py::test_fn; echo pwned' or its tokens are not shell-evaluated
        assert isinstance(argv, list)
        assert argv[0] == "pytest"
        # The malicious string is contained as arguments to pytest, not passed to a shell
        assert "-x" in argv

    def test_isolation_probe_never_invokes_shell(self) -> None:
        """Verification that subprocess.run is called with shell=False and respects timeout."""
        output = [
            "FAILED tests/test_foo.py::test_bar - AssertionError: oops",
        ]
        config = _make_config(test_cmd="pytest", timeout_seconds=42)

        with patch("subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.stdout = "single test passed"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            diag = analyse(output, exit_code=1, termination_reason=None, config=config)

            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs.get("shell") is False
            assert kwargs.get("timeout") == 42
            assert diag.isolation_output == "single test passed"

    def test_isolation_skipped_when_no_root_test(self) -> None:
        """When no test identifier is extracted, isolation probe is skipped and isolation_output is None."""
        output = ["Generic failure without test names"]
        config = _make_config(test_cmd="pytest")
        with patch("subprocess.run") as mock_run:
            diag = analyse(output, exit_code=1, termination_reason=None, config=config)
            mock_run.assert_not_called()
            assert diag.root_tests == []
            assert diag.isolation_output is None

    def test_isolation_skipped_when_unknown_runner(self) -> None:
        """When runner heuristic cannot determine template and no override is configured, skip isolation."""
        output = ["FAILED test_foo"]
        config = _make_config(test_cmd="unknown_runner_command")
        with patch("subprocess.run") as mock_run:
            diag = analyse(output, exit_code=1, termination_reason=None, config=config)
            mock_run.assert_not_called()
            assert diag.isolation_output is None

    def test_isolation_probe_timeout_handled_gracefully(self) -> None:
        """Isolation probe handles subprocess.TimeoutExpired gracefully without raising."""
        output = ["FAILED tests/test_slow.py::test_blocked - TimeoutError"]
        config = _make_config(test_cmd="pytest", timeout_seconds=5)
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pytest"], timeout=5, output="partial test out")
            diag = analyse(output, exit_code=1, termination_reason=None, config=config)
            assert diag.isolation_output is not None
            assert "timed out after 5s" in diag.isolation_output
            assert "partial test out" in diag.isolation_output

    def test_isolation_probe_file_not_found_handled_gracefully(self) -> None:
        """Isolation probe handles FileNotFoundError without raising."""
        output = ["FAILED tests/test_a.py::test_missing - Error"]
        config = _make_config(test_cmd="pytest")
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("No such file or directory: 'pytest'")
            diag = analyse(output, exit_code=1, termination_reason=None, config=config)
            assert diag.isolation_output is not None
            assert "failed to execute" in diag.isolation_output

    def test_multiline_string_input_supported(self) -> None:
        """analyse() accepts a single multi-line string in addition to a list of lines."""
        raw_output = "line 1\nline 2\nFAILED tests/test_str.py::test_str_input - AssertionError\n"
        config = _make_config()
        probe_runner = MagicMock(return_value="ran string test")
        diag = analyse(raw_output, exit_code=1, termination_reason=None, config=config, probe_runner=probe_runner)
        assert diag.root_tests == ["tests/test_str.py::test_str_input"]
        assert diag.isolation_output == "ran string test"

    def test_dict_config_supported(self) -> None:
        """analyse() accepts dict-shaped configuration."""
        output = ["FAILED tests/test_dict.py::test_dict - AssertionError"]
        config = {"test_cmd": "pytest", "isolation_cmd": "", "timeout_seconds": 15}
        probe_runner = MagicMock(return_value="probe output")
        diag = analyse(output, exit_code=1, termination_reason=None, config=config, probe_runner=probe_runner)
        assert diag.isolation_output == "probe output"

    def test_parameterized_pytest_id_extraction(self) -> None:
        """Extracts parameterized pytest identifiers including bracketed parameter values."""
        output = [
            "FAILED tests/unit/test_params.py::test_case[param_1-value_2] - AssertionError",
        ]
        test_ids = extract_test_identifiers(output)
        assert test_ids == ["tests/unit/test_params.py::test_case[param_1-value_2]"]

    @pytest.mark.parametrize(
        "malicious_payload",
        [
            "test_foo.py::test_fn; whoami",
            "test_foo.py::test_fn && echo injected",
            "test_foo.py::test_fn | cat /etc/passwd",
            "test_foo.py::test_fn `touch /tmp/pwn`",
            "test_foo.py::test_fn $(touch /tmp/pwn)",
            "test_foo.py::test_fn > /tmp/overwrite",
        ],
    )
    def test_shell_metacharacters_do_not_inject_commands(self, malicious_payload: str) -> None:
        """Various shell metacharacters in test identifiers never trigger shell command injection."""
        template = "pytest {test_id} -x"
        argv = interpolate_isolation_command(template, test_id=malicious_payload)
        assert argv[0] == "pytest"
        assert "-x" in argv
        # The entire malicious payload stays tokenized as arguments without shell interpretation
        # We ensure subprocess.run is executed with shell=False
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ok", stderr="")
            config = _make_config(test_cmd="pytest")
            analyse([f"FAILED {malicious_payload} - Error"], exit_code=1, termination_reason=None, config=config)
            mock_run.assert_called_once()
            _, kwargs = mock_run.call_args
            assert kwargs.get("shell") is False

    def test_analyse_classifies_worker_stall_on_no_signal_after_nudge(self) -> None:
        """NO_SIGNAL_AFTER_NUDGE is classified as WORKER_STALL with actionable guidance."""
        config = _make_config(test_cmd="pytest")
        diag = analyse(
            output_lines=["NO_SIGNAL_AFTER_NUDGE", "Token budget: 75,837 / 150,000"],
            exit_code=1,
            termination_reason="NO_SIGNAL_AFTER_NUDGE",
            config=config,
        )
        assert diag.label == "WORKER_STALL"
        assert "Worker session stalled" in diag.suggested_action
        assert diag.isolation_output is None


