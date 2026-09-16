"""Spec markdown parser and lightweight excerpt extractor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from runner.domain.exceptions import SpecFormatError

HEADING_PATTERN = re.compile(r"^##\s+(?P<title>.+?)\s*$")


@dataclass(frozen=True)
class SpecExcerpt:
    """Lightweight architectural excerpt extracted from a spec file."""

    text: str
    spec_path: str
    problem_statement: str = ""
    solution: str = ""

    def __str__(self) -> str:
        return self.text


class SpecMarkdownParser:
    """Extracts lightweight spec excerpts from spec markdown documents."""

    def extract_excerpt(self, path: Path | str) -> SpecExcerpt:
        """Extract '## Problem Statement' and '## Solution' from a spec markdown file.

        Args:
            path: Path to the spec markdown file.

        Returns:
            SpecExcerpt containing the formatted excerpt and the spec path.

        Raises:
            SpecFormatError: If the file is unreadable or either required section is missing/empty.
        """
        spec_path = Path(path)
        try:
            with spec_path.open("r", encoding="utf-8", newline="") as handle:
                content = handle.read()
        except OSError as exc:
            raise SpecFormatError(
                f"Cannot read spec file '{spec_path.as_posix()}': {exc}. "
                f"Ensure the spec file exists and is accessible."
            ) from exc

        return self.parse_excerpt(content, spec_path)

    def parse_excerpt(self, text: str, spec_path: Path | str = "") -> SpecExcerpt:
        """Parse raw spec markdown text to extract Problem Statement and Solution.

        Args:
            text: Raw markdown text of the specification.
            spec_path: Optional path reference to include in the excerpt.

        Returns:
            SpecExcerpt with extracted sections.

        Raises:
            SpecFormatError: If either required section is missing or empty.
        """
        lines = text.splitlines()
        normalized_path = Path(spec_path).as_posix() if spec_path else ""

        sections: dict[str, list[str]] = {}
        current_section: str | None = None

        for line in lines:
            match = HEADING_PATTERN.match(line)
            if match:
                title = match.group("title").strip().lower()
                if title == "problem statement":
                    current_section = "problem_statement"
                    sections.setdefault(current_section, [])
                elif title == "solution":
                    current_section = "solution"
                    sections.setdefault(current_section, [])
                else:
                    current_section = None
                continue

            if current_section is not None:
                sections[current_section].append(line)

        if "problem_statement" not in sections:
            raise SpecFormatError(
                f"Spec file '{normalized_path}' is missing required '## Problem Statement' section. "
                f"Please add '## Problem Statement' describing architectural motivation."
            )

        problem_statement = "\n".join(sections["problem_statement"]).strip()
        if not problem_statement:
            raise SpecFormatError(
                f"Spec file '{normalized_path}' has an empty '## Problem Statement' section. "
                f"Please provide descriptive content under '## Problem Statement'."
            )

        if "solution" not in sections:
            raise SpecFormatError(
                f"Spec file '{normalized_path}' is missing required '## Solution' section. "
                f"Please add '## Solution' outlining the architectural design."
            )

        solution = "\n".join(sections["solution"]).strip()
        if not solution:
            raise SpecFormatError(
                f"Spec file '{normalized_path}' has an empty '## Solution' section. "
                f"Please provide descriptive content under '## Solution'."
            )

        excerpt_text = (
            f"## Problem Statement\n\n"
            f"{problem_statement}\n\n"
            f"## Solution\n\n"
            f"{solution}"
        )

        return SpecExcerpt(
            text=excerpt_text,
            spec_path=normalized_path,
            problem_statement=problem_statement,
            solution=solution,
        )


SpecParser = SpecMarkdownParser


def extract_spec_excerpt(path: Path | str) -> SpecExcerpt:
    """Convenience function to extract a SpecExcerpt from a file path."""
    return SpecMarkdownParser().extract_excerpt(path)
