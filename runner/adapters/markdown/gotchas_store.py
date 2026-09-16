"""Gotchas aggregation store and markdown normalizer."""

from __future__ import annotations

from collections.abc import Sequence
import os
from pathlib import Path
import re

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.domain.exceptions import TicketFormatError

DEFAULT_GOTCHAS_PATH = Path("docs/tickets/gotchas.md")

DEFAULT_SKELETON = (
    "# Global Gotchas & Lessons Learned\n\n"
    "A chronological record of runtime quirks, platform pitfalls, and architectural "
    "lessons discovered during ticket implementations. Subsequent ticket sessions "
    "ingest these lessons to prevent recurring mistakes.\n\n"
    "---\n"
)


def derive_title(text: str) -> str:
    """Derive a concise, deterministic section title from freeform text or problem description.

    Args:
        text: Freeform gotcha text or problem clause.

    Returns:
        A concise title string suitable for a '### <Title>' header.
    """
    clean = text.strip()
    clean = re.sub(r"[`*]", "", clean)
    # Split on sentence end (dot followed by space), semicolon, newline, or em-dash
    parts = re.split(r"\.\s+|;\s*|\n|(?:\s+[—–]\s+)", clean)
    first_clause = parts[0].strip() if parts else clean
    words = first_clause.split()
    if len(words) > 8:
        title = " ".join(words[:8])
    else:
        title = first_clause
    title = title.strip(" -—–.:")
    if not title:
        return "General Gotcha"
    return title[:1].upper() + title[1:]


def normalize_entry(entry: str) -> str:
    """Normalize a raw gotchas string into the standard markdown section format.

    Preserves pre-existing markdown formatting and headings without corruption.
    Converts unstructured or partially formatted free text into:
        ### <Title>
        - **Problem**: <problem text>
        - **Solution**: <solution text>

    Args:
        entry: Raw gotcha string from a completion signal or caller.

    Returns:
        Normalized markdown section text, or empty string if entry was blank.
    """
    trimmed = entry.strip()
    if not trimmed:
        return ""

    # 1. Heading check: if already starts with markdown heading
    heading_match = re.match(r"^(#{1,6})\s+(.+?)(?:\r?\n|$)(.*)", trimmed, re.DOTALL)
    if heading_match:
        title = heading_match.group(2).strip()
        body = heading_match.group(3).strip()

        # If body already contains - **Problem**: and - **Solution**:
        if re.search(r"^\s*-\s+\*\*Problem\*\*:", body, re.MULTILINE) and re.search(
            r"^\s*-\s+\*\*Solution\*\*:", body, re.MULTILINE
        ):
            return f"### {title}\n{body}"

        # If body contains Problem: and Solution: without bold markers
        prob_match = re.search(
            r"(?:^|\n)\s*(?:-\s+)?(?:\*\*)?Problem(?:\*\*)?:\s*(.*?)(?=\n\s*(?:-\s+)?(?:\*\*)?Solution(?:\*\*)?:|$)",
            body,
            re.DOTALL | re.IGNORECASE,
        )
        sol_match = re.search(
            r"(?:^|\n)\s*(?:-\s+)?(?:\*\*)?Solution(?:\*\*)?:\s*(.*)$",
            body,
            re.DOTALL | re.IGNORECASE,
        )
        if prob_match and sol_match:
            p_text = prob_match.group(1).strip()
            s_text = sol_match.group(1).strip()
            return f"### {title}\n- **Problem**: {p_text}\n- **Solution**: {s_text}"

        # Otherwise preserve custom markdown formatting under the ### heading
        return f"### {title}\n{body}"

    # 2. Check for title on first line followed by Problem/Solution lines
    lines = [line.strip() for line in trimmed.splitlines() if line.strip()]
    explicit_title: str | None = None
    body_text = trimmed

    if len(lines) > 1 and not re.match(
        r"^(?:-\s+)?(?:\*\*)?(?:Problem|Solution|Issue|Fix)(?:\*\*)?:",
        lines[0],
        re.IGNORECASE,
    ):
        if any(
            re.match(
                r"^(?:-\s+)?(?:\*\*)?(?:Problem|Solution|Issue|Fix)(?:\*\*)?:",
                line,
                re.IGNORECASE,
            )
            for line in lines[1:]
        ):
            explicit_title = lines[0].strip(" -—–.:")
            body_text = "\n".join(lines[1:])

    # 3. Check for Problem: and Solution: markers
    prob_match = re.search(
        r"(?:^|\n|\s+)(?:-\s+)?(?:\*\*)?Problem(?:\*\*)?:\s*(.*?)(?=(?:\n|\s+)(?:-\s+)?(?:\*\*)?Solution(?:\*\*)?:|$)",
        body_text,
        re.DOTALL | re.IGNORECASE,
    )
    sol_match = re.search(
        r"(?:^|\n|\s+)(?:-\s+)?(?:\*\*)?Solution(?:\*\*)?:\s*(.*)$",
        body_text,
        re.DOTALL | re.IGNORECASE,
    )

    if prob_match and sol_match:
        before_prob = body_text[: prob_match.start()].strip()
        if not explicit_title and before_prob:
            explicit_title = before_prob.strip(" -—–.:")
        p_text = prob_match.group(1).strip()
        s_text = sol_match.group(1).strip()
        title = explicit_title or derive_title(p_text)
        return f"### {title}\n- **Problem**: {p_text}\n- **Solution**: {s_text}"

    # Check if lines already have - **Problem**: but missing title
    if re.search(r"^\s*-\s+\*\*Problem\*\*:", body_text, re.MULTILINE):
        title = derive_title(body_text)
        return f"### {title}\n{body_text}"

    # 4. Check for 'Title: Text' prefix
    colon_match = re.match(r"^([^:\n]+):\s+(.+)$", trimmed, re.DOTALL)
    if colon_match and not re.match(
        r"^(?:Problem|Solution|Issue|Fix)$", colon_match.group(1).strip(), re.IGNORECASE
    ):
        explicit_title = colon_match.group(1).strip()
        text_rest = colon_match.group(2).strip()
    else:
        text_rest = trimmed

    # 5. Check for semicolon or em-dash separating problem and solution
    separator_match = re.search(r"^(.*?)\s*(?:;\s+|(?:\s+[—–]\s+))\s*(.*)$", text_rest, re.DOTALL)
    if separator_match:
        p_text = separator_match.group(1).strip()
        s_text = separator_match.group(2).strip()
        if not p_text.endswith("."):
            p_text += "."
        if not s_text.endswith("."):
            s_text += "."
        s_text = s_text[:1].upper() + s_text[1:]
        title = explicit_title or derive_title(p_text)
        return f"### {title}\n- **Problem**: {p_text}\n- **Solution**: {s_text}"

    # 6. Single clause / freeform text without solution
    title = explicit_title or derive_title(text_rest)
    return f"### {title}\n- **Problem**: {text_rest}\n- **Solution**: Not specified."


class GotchasStore:
    """Manages reading and atomic appending of global Gotchas in markdown format."""

    def __init__(self, path: Path | str = DEFAULT_GOTCHAS_PATH) -> None:
        """Initialize GotchasStore.

        Args:
            path: Path to the gotchas markdown file (defaults to docs/tickets/gotchas.md).
        """
        self._path = Path(path)

    @property
    def path(self) -> Path:
        """Path to the gotchas markdown file."""
        return self._path

    def load(self) -> str:
        """Load and return the raw text of the gotchas markdown file.

        Returns:
            The content of the file, or an empty string if the file does not exist.
        """
        if not self._path.is_file():
            return ""
        with self._path.open("r", encoding="utf-8", newline="") as handle:
            return handle.read()

    def load_sections(self) -> list[str]:
        """Parse and return all '### <Title>' sections from the current file.

        Returns:
            List of section strings starting with '### '.
        """
        text = self.load()
        if not text:
            return []
        sections = [
            s.strip()
            for s in re.split(r"(?m)(?=^###\s+)", text)
            if s.strip().startswith("### ")
        ]
        return sections

    def append(self, new_gotchas: Sequence[str]) -> list[str]:
        """Append newly discovered gotchas atomically, skipping duplicates.

        Preserves all existing content, headers, and section structure unchanged.
        Creates missing gotchas.md with the standard skeleton before the first entry.

        Args:
            new_gotchas: Sequence of raw or formatted gotcha entry strings.

        Returns:
            List of newly appended normalized entry strings.

        Raises:
            TicketFormatError: If atomic file write fails.
        """
        # Scoped read: load fresh content right at append time
        existing_text = self.load()
        file_existed = self._path.is_file()

        existing_sections = self.load_sections()
        existing_normalized = {self._clean_key(s) for s in existing_sections}
        existing_titles = {
            self._extract_title(s).lower()
            for s in existing_sections
            if self._extract_title(s)
        }

        to_append: list[str] = []
        seen_batch_keys: set[str] = set()
        seen_batch_titles: set[str] = set()

        for raw_entry in new_gotchas:
            normalized = normalize_entry(raw_entry)
            if not normalized:
                continue

            clean_key = self._clean_key(normalized)
            title = self._extract_title(normalized)
            title_lower = title.lower() if title else None

            # Skip exact duplicates against existing content or within this batch
            if clean_key in existing_normalized or clean_key in seen_batch_keys:
                continue
            if title_lower and (
                title_lower in existing_titles or title_lower in seen_batch_titles
            ):
                continue

            to_append.append(normalized)
            seen_batch_keys.add(clean_key)
            if title_lower:
                seen_batch_titles.add(title_lower)

        if not to_append:
            return []

        # Determine line ending style
        newline = "\r\n" if "\r\n" in existing_text else "\n"

        if file_existed:
            base_content = existing_text
            # Determine separator spacing after pre-existing content
            if base_content.endswith(newline * 2):
                separator = ""
            elif base_content.endswith(newline):
                separator = newline
            else:
                separator = newline * 2

            joined_entries = (newline * 2).join(
                self._reline(entry, newline) for entry in to_append
            )
            final_content = f"{base_content}{separator}{joined_entries}{newline}"
        else:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            skeleton = self._reline(DEFAULT_SKELETON, newline)
            joined_entries = (newline * 2).join(
                self._reline(entry, newline) for entry in to_append
            )
            final_content = f"{skeleton}{newline}{joined_entries}{newline}"

        try:
            atomic_write_text(self._path, final_content)
        except OSError as exc:
            raise TicketFormatError(
                f"Failed to update gotchas file '{self._path}' atomically: {exc}. "
                "Ensure no other process has the file open."
            ) from exc

        return to_append

    @staticmethod
    def _extract_title(section: str) -> str | None:
        lines = section.strip().splitlines()
        if not lines:
            return None
        match = re.match(r"^###\s+(.+)$", lines[0])
        return match.group(1).strip() if match else None

    @staticmethod
    def _clean_key(text: str) -> str:
        # Whitespace-collapsed key for exact duplicate matching
        return " ".join(text.strip().split()).lower()

    @staticmethod
    def _reline(text: str, newline: str) -> str:
        lines = text.splitlines()
        return newline.join(lines)
