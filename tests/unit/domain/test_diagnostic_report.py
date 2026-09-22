"""Unit tests for structured diagnostic report rendering (T066)."""

from __future__ import annotations

import pytest

from runner.domain.failure_analyser import (
    FailureDiagnostic,
    LABEL_CASCADE,
    LABEL_ENV,
    LABEL_FLAKY,
    LABEL_HANG,
    render_diagnostic_report,
)


def test_render_diagnostic_report_hang() -> None:
    diag = FailureDiagnostic(
        label=LABEL_HANG,
        root_tests=["test_suite.py::test_tui_render"],
        top_errors=["TimeoutError", "AssertionError"],
        log_tail=["line 1", "line 2", "line 3"],
        isolation_output=None,
        suggested_action="Run /diagnosing-bugs (§ Stuck-Test-Suite Runbook) to triage hanging test or infinite loop.",
    )
    report = render_diagnostic_report(diag, token_count=42150, token_budget=150000)

    expected_lines = [
        "⚠ HANG detected — test_suite.py::test_tui_render",
        "Top errors: TimeoutError, AssertionError",
        "--- last 100 lines ---",
        "line 1",
        "line 2",
        "line 3",
        "Token budget: 42,150 / 150,000",
        "Suggested: Run /diagnosing-bugs (§ Stuck-Test-Suite Runbook) to triage hanging test or infinite loop.",
        "Run /diagnosing-bugs? [Y/n]",
    ]
    assert report == "\n".join(expected_lines)


def test_render_diagnostic_report_with_isolation_output() -> None:
    diag = FailureDiagnostic(
        label=LABEL_CASCADE,
        root_tests=["tests/test_foo.py::test_bar"],
        top_errors=["ImportError"],
        log_tail=["line A", "line B"],
        isolation_output="pytest tests/test_foo.py::test_bar -x\nFAILED: No module named 'foo'",
        suggested_action="Investigate root failing test in isolation to fix common failure class.",
    )
    report = render_diagnostic_report(diag, token_count=1000, token_budget=150000)

    assert "⚠ CASCADE detected — tests/test_foo.py::test_bar" in report
    assert "Top errors: ImportError" in report
    assert "pytest tests/test_foo.py::test_bar -x\nFAILED: No module named 'foo'" in report
    assert "--- last 100 lines ---" in report
    assert "line A\nline B" in report
    assert "Token budget: 1,000 / 150,000" in report
    assert "Run /diagnosing-bugs? [Y/n]" in report


def test_render_diagnostic_report_unknown_root_and_no_errors() -> None:
    diag = FailureDiagnostic(
        label=LABEL_FLAKY,
        root_tests=[],
        top_errors=[],
        log_tail=[],
        isolation_output=None,
        suggested_action="Inspect test failure trace or re-run test suite.",
    )
    report = render_diagnostic_report(diag, token_count=0, token_budget=150000)

    assert report.startswith("⚠ FLAKY detected — unknown")
    assert "Top errors: none" in report
    assert "--- last 100 lines ---" in report
    assert "Token budget: 0 / 150,000" in report
    assert "Run /diagnosing-bugs? [Y/n]" in report


def test_render_diagnostic_report_bounds_log_tail_to_100_lines() -> None:
    lines = [f"log line {i}" for i in range(150)]
    diag = FailureDiagnostic(
        label=LABEL_ENV,
        root_tests=["test_env.py"],
        top_errors=["ModuleNotFoundError"],
        log_tail=lines,
        isolation_output=None,
        suggested_action="Check environment, dependencies, and imports before retrying.",
    )
    report = render_diagnostic_report(diag)
    # The tail inside report must only contain the last 100 lines (log line 50 to 149)
    assert "log line 49" not in report
    assert "log line 50" in report
    assert "log line 149" in report
