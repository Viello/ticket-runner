"""Unit tests for the SpecMarkdownParser adapter and spec excerpt extraction."""

from pathlib import Path
import pytest

from runner.adapters.markdown.spec_parser import (
    SpecExcerpt,
    SpecMarkdownParser,
    SpecParser,
    extract_spec_excerpt,
)
from runner.domain.exceptions import SpecFormatError, TicketFormatError

SPEC_04_PATH = Path("docs/specs/04-signal-protocol-and-gatekeeper.md")

SAMPLE_SPEC = """# Spec 99: Test Spec

## Problem Statement

This is the problem statement describing the issue.
It has multiple lines.

## Solution

This is the proposed solution.
It also spans multiple lines.

## User Stories

1. As a user, I want X.
"""

SAMPLE_SPEC_CRLF = (
    "# Spec 99: Test Spec\r\n\r\n"
    "## Problem Statement\r\n\r\n"
    "CRLF problem statement.\r\n\r\n"
    "## Solution\r\n\r\n"
    "CRLF solution statement.\r\n\r\n"
    "## User Stories\r\n\r\n"
    "1. CRLF user story.\r\n"
)


def _write_spec(tmp_path: Path, filename: str, content: str) -> Path:
    spec_path = tmp_path / filename
    with spec_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(content)
    return spec_path


def test_extract_excerpt_from_real_spec_04() -> None:
    assert SPEC_04_PATH.is_file(), f"Spec file not found at {SPEC_04_PATH}"
    parser = SpecMarkdownParser()
    excerpt = parser.extract_excerpt(SPEC_04_PATH)

    assert isinstance(excerpt, SpecExcerpt)
    assert excerpt.spec_path == SPEC_04_PATH.as_posix()
    assert "Autonomous agents frequently hallucinate successful completion" in excerpt.problem_statement
    assert "Enforce durable, filesystem-based Signals" in excerpt.solution
    assert "## User Stories" not in excerpt.text
    assert "## Implementation Decisions" not in excerpt.text

    # Verify sections appear in the exact required order
    prob_idx = excerpt.text.index("## Problem Statement")
    sol_idx = excerpt.text.index("## Solution")
    assert prob_idx < sol_idx
    assert str(excerpt) == excerpt.text


def test_extract_excerpt_convenience_function_and_alias(tmp_path: Path) -> None:
    path = _write_spec(tmp_path, "sample.md", SAMPLE_SPEC)

    excerpt1 = extract_spec_excerpt(path)
    excerpt2 = SpecParser().extract_excerpt(path)

    assert excerpt1.problem_statement == "This is the problem statement describing the issue.\nIt has multiple lines."
    assert excerpt1.solution == "This is the proposed solution.\nIt also spans multiple lines."
    assert excerpt1.spec_path == path.as_posix()
    assert excerpt1.text == excerpt2.text


def test_extract_excerpt_crlf_tolerance(tmp_path: Path) -> None:
    path = _write_spec(tmp_path, "crlf.md", SAMPLE_SPEC_CRLF)

    excerpt = SpecMarkdownParser().extract_excerpt(path)

    assert "\r" not in excerpt.text
    assert excerpt.problem_statement == "CRLF problem statement."
    assert excerpt.solution == "CRLF solution statement."
    assert "## Problem Statement\n\nCRLF problem statement.\n\n## Solution\n\nCRLF solution statement." in excerpt.text


def test_extract_excerpt_section_order_invariance(tmp_path: Path) -> None:
    inverted = """# Inverted Spec

## Solution

Solution comes first in file.

## Problem Statement

Problem comes second in file.
"""
    path = _write_spec(tmp_path, "inverted.md", inverted)
    excerpt = SpecMarkdownParser().extract_excerpt(path)

    assert excerpt.problem_statement == "Problem comes second in file."
    assert excerpt.solution == "Solution comes first in file."
    # Output must always have Problem Statement before Solution
    assert excerpt.text.startswith("## Problem Statement\n\nProblem comes second in file.\n\n## Solution\n\nSolution comes first in file.")


def test_missing_problem_statement_raises_spec_format_error(tmp_path: Path) -> None:
    bad_spec = """# Spec

## Solution

Only solution exists.
"""
    path = _write_spec(tmp_path, "no_problem.md", bad_spec)

    with pytest.raises(SpecFormatError) as exc_info:
        SpecMarkdownParser().extract_excerpt(path)

    assert issubclass(SpecFormatError, TicketFormatError)
    assert "## Problem Statement" in str(exc_info.value)
    assert str(path.as_posix()) in str(exc_info.value)


def test_missing_solution_raises_spec_format_error(tmp_path: Path) -> None:
    bad_spec = """# Spec

## Problem Statement

Only problem exists.
"""
    path = _write_spec(tmp_path, "no_solution.md", bad_spec)

    with pytest.raises(SpecFormatError) as exc_info:
        SpecMarkdownParser().extract_excerpt(path)

    assert "## Solution" in str(exc_info.value)
    assert str(path.as_posix()) in str(exc_info.value)


def test_empty_problem_statement_raises_spec_format_error(tmp_path: Path) -> None:
    empty_prob = """# Spec

## Problem Statement

## Solution

Solution here.
"""
    path = _write_spec(tmp_path, "empty_prob.md", empty_prob)

    with pytest.raises(SpecFormatError) as exc_info:
        SpecMarkdownParser().extract_excerpt(path)

    assert "empty" in str(exc_info.value).lower()
    assert "## Problem Statement" in str(exc_info.value)


def test_empty_solution_raises_spec_format_error(tmp_path: Path) -> None:
    empty_sol = """# Spec

## Problem Statement

Problem statement here.

## Solution

"""
    path = _write_spec(tmp_path, "empty_sol.md", empty_sol)

    with pytest.raises(SpecFormatError) as exc_info:
        SpecMarkdownParser().extract_excerpt(path)

    assert "empty" in str(exc_info.value).lower()
    assert "## Solution" in str(exc_info.value)


def test_unreadable_file_raises_spec_format_error(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.md"

    with pytest.raises(SpecFormatError) as exc_info:
        SpecMarkdownParser().extract_excerpt(non_existent)

    assert "does_not_exist.md" in str(exc_info.value)
