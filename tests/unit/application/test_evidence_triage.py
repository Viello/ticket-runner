"""Unit tests for EvidenceTriage application interactor (Spec 13)."""

import json
from pathlib import Path
import pytest

from runner.application.evidence_triage import EvidenceTriage, TriageResult
from runner.domain.runtime_paths import RuntimePaths


def test_clean_pass_produces_empty_excerpt(tmp_path: Path) -> None:
    """Smoke Scenario: Clean pass produces empty excerpt."""
    log_path = tmp_path / "clean_pass.log"
    log_content = "\n".join(f"test_item_{i} passed" for i in range(100))
    log_path.write_text(log_content, encoding="utf-8")

    result = EvidenceTriage.extract(log_path, exit_code=0, duration=5.0, ticket_id="T107")

    assert isinstance(result, TriageResult)
    assert result.failure_excerpt == ""
    assert result.exit_code == 0
    assert result.duration == 5.0
    assert result.first_failing_test is None
    assert result.error_message is None

    # Inspect written summary.json
    summary_path = tmp_path / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["exit_code"] == 0
    assert summary["duration"] == 5.0
    assert summary["failure_excerpt"] == ""
    assert "clean_pass.log" in summary["artifacts"]


def test_large_log_triage_stays_bounded(tmp_path: Path) -> None:
    """Smoke Scenario: Large log triage stays bounded (50k lines, failure at line 40k)."""
    log_path = tmp_path / "large_run.log"
    lines: list[str] = [f"line {i}: passing test execution step" for i in range(50000)]

    # Inject failure at line 40,000
    failure_block = [
        "=================================== FAILURES ===================================",
        "______________________________ test_heavy_computation __________________________",
        "    def test_heavy_computation():",
        "        data = compute_massive_dataset()",
        ">       assert len(data) == 1000",
        "E       AssertionError: assert 500 == 1000",
        "tests/test_compute.py:42: AssertionError",
        "=========================== short test summary info ===========================",
        "FAILED tests/test_compute.py::test_heavy_computation - AssertionError: assert 500 == 1000",
    ]
    lines[40000 : 40000 + len(failure_block)] = failure_block

    log_path.write_text("\n".join(lines), encoding="utf-8")

    result = EvidenceTriage.extract(log_path, exit_code=1, duration=42.0, ticket_id="T107")

    assert isinstance(result, TriageResult)
    assert len(result.failure_excerpt.splitlines()) <= 30
    assert len(result.failure_excerpt) <= 1000
    assert len(result) <= 1000
    assert "AssertionError" in result.failure_excerpt
    assert "test_heavy_computation" in result.failure_excerpt

    # Inspect written summary.json
    summary_path = tmp_path / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["exit_code"] == 1
    assert summary["duration"] == 42.0
    assert summary["failure_excerpt"] != ""
    assert len(summary["failure_excerpt"]) <= 1000
    assert len(summary["failure_excerpt"].splitlines()) <= 30
    assert "large_run.log" in summary["artifacts"]


def test_multiple_failures_extracts_only_first(tmp_path: Path) -> None:
    """Only the first failing test and error message are extracted to preserve context."""
    log_path = tmp_path / "multi_failure.log"
    log_content = """
=================================== FAILURES ===================================
__________________________________ test_first __________________________________
    def test_first():
>       assert 1 == 2
E       AssertionError: assert 1 == 2
tests/test_first.py:10: AssertionError
_________________________________ test_second __________________________________
    def test_second():
>       assert "foo" == "bar"
E       AssertionError: assert 'foo' == 'bar'
tests/test_second.py:20: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_first.py::test_first - AssertionError: assert 1 == 2
FAILED tests/test_second.py::test_second - AssertionError: assert 'foo' == 'bar'
"""
    log_path.write_text(log_content.strip(), encoding="utf-8")

    result = EvidenceTriage.extract(log_path, exit_code=1, duration=1.5, ticket_id="T107")

    assert "test_first" in result.failure_excerpt
    assert "test_second" not in result.failure_excerpt
    assert result.first_failing_test == "tests/test_first.py::test_first"
    assert "assert 1 == 2" in (result.error_message or "")
    assert len(result.failure_excerpt.splitlines()) <= 30
    assert len(result.failure_excerpt) <= 1000


def test_edge_case_empty_log(tmp_path: Path) -> None:
    """Empty log file handling with non-zero exit code."""
    empty_log = tmp_path / "empty.log"
    empty_log.write_text("", encoding="utf-8")

    result = EvidenceTriage.extract(empty_log, exit_code=127, duration=0.1, ticket_id="T107")

    assert result.exit_code == 127
    assert "127" in result.failure_excerpt
    assert len(result.failure_excerpt.splitlines()) <= 30
    assert len(result.failure_excerpt) <= 1000

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["exit_code"] == 127
    assert "127" in summary["failure_excerpt"]


def test_edge_case_binary_content(tmp_path: Path) -> None:
    """Binary garbage in log does not crash extractor and produces bounded excerpt."""
    binary_log = tmp_path / "binary.log"
    # Write arbitrary bytes containing null bytes, invalid UTF-8 sequences, and a failure marker
    raw_data = b"\x00\xff\xfe\x80\x81Binary garbage\nFAILED test_binary::test_corrupt\nE   AssertionError: corrupt bytes\n\x00\x01\x02"
    binary_log.write_bytes(raw_data)

    result = EvidenceTriage.extract(binary_log, exit_code=1, duration=2.0, ticket_id="T107")

    assert result.exit_code == 1
    assert len(result.failure_excerpt.splitlines()) <= 30
    assert len(result.failure_excerpt) <= 1000
    assert "AssertionError" in result.failure_excerpt


def test_ansi_escape_code_stripping_and_character_limit(tmp_path: Path) -> None:
    """ANSI color codes are stripped before calculating the 1,000-character ceiling."""
    log_path = tmp_path / "ansi.log"
    # 2,000 characters of colored text with failure markers
    colored_line = "\x1b[31mE       AssertionError: red failure text with lots of padding " + ("x" * 1500) + "\x1b[0m\n"
    log_path.write_text(f"FAILED tests/test_color.py::test_color\n{colored_line}", encoding="utf-8")

    result = EvidenceTriage.extract(log_path, exit_code=1, duration=3.0, ticket_id="T107")

    assert "\x1b[" not in result.failure_excerpt
    assert len(result.failure_excerpt) <= 1000
    assert len(result.failure_excerpt.splitlines()) <= 30


def test_instance_usage_with_custom_runtime_paths(tmp_path: Path) -> None:
    """EvidenceTriage can be used as an instance with injected RuntimePaths."""
    agent_dir = tmp_path / "custom_agent"
    paths = RuntimePaths(root_dir=agent_dir)
    evidence_dir = paths.ensure_evidence_dir("T107")

    log_path = evidence_dir / "harness.log"
    log_path.write_text("FAILED test_harness::test_cli\nE   RuntimeError: Boom", encoding="utf-8")
    (evidence_dir / "trace.json").write_text("{}", encoding="utf-8")

    triage = EvidenceTriage(ticket_id="T107", runtime_paths=paths)
    result = triage.extract(log_path, exit_code=1, duration=10.0)

    assert result.exit_code == 1
    assert "RuntimeError: Boom" in result.failure_excerpt

    # Written to custom evidence dir
    summary_path = evidence_dir / "summary.json"
    assert summary_path.exists()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["exit_code"] == 1
    assert "harness.log" in summary["artifacts"]
    assert "trace.json" in summary["artifacts"]
    assert "summary.json" not in summary["artifacts"]
