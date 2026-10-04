"""Evidence triage extractor application interactor (Spec 13).

Parses harness and test logs, extracts first failing test details, bounds failure excerpts
to <= 30 lines / 1,000 characters, and writes summary.json atomically to the evidence directory.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.domain.failure_analyser import extract_test_identifiers, strip_ansi
from runner.domain.runtime_paths import RuntimePaths, TICKET_ID_PATTERN

MAX_EXCERPT_LINES: int = 30
MAX_EXCERPT_CHARS: int = 1000

_TEST_HEADER_RE = re.compile(r"^_{3,}\s*(.+?)\s*_{3,}$")
_SUMMARY_HEADER_RE = re.compile(r"^={3,}\s*short test summary info")
_FAILURES_HEADER_RE = re.compile(r"^={3,}\s*FAILURES")

_ERROR_LINE_PATTERNS = (
    re.compile(r"^E\s+(.+)$"),
    re.compile(r"(AssertionError.*?)$"),
    re.compile(r"([A-Za-z0-9_]+(?:Error|Exception|Fault):.*?)$"),
    re.compile(r"(FAILED\s+.*)$"),
    re.compile(r"(FAIL:?\s+.*)$"),
)

_FAILURE_MARKERS = ("FAILED", "AssertionError", "ERROR ", "FAIL ", "--- FAIL")


@dataclass(frozen=True)
class TriageResult:
    """Bounded, token-preserving triage result from inspecting verification logs."""

    failure_excerpt: str
    exit_code: int = 0
    duration: float = 0.0
    first_failing_test: str | None = None
    error_message: str | None = None
    artifacts: tuple[str, ...] = ()
    summary_path: Path | None = None

    def __post_init__(self) -> None:
        clean = strip_ansi(self.failure_excerpt)
        lines = clean.splitlines()
        if len(lines) > MAX_EXCERPT_LINES:
            clean = "\n".join(lines[:MAX_EXCERPT_LINES])
        if len(clean) > MAX_EXCERPT_CHARS:
            clean = clean[: MAX_EXCERPT_CHARS - 3] + "..." if len(clean) > MAX_EXCERPT_CHARS else clean
            clean = clean[:MAX_EXCERPT_CHARS]
            lines = clean.splitlines()
            if len(lines) > MAX_EXCERPT_LINES:
                clean = "\n".join(lines[:MAX_EXCERPT_LINES])
        object.__setattr__(self, "failure_excerpt", clean)

    def __str__(self) -> str:
        return self.failure_excerpt

    def __len__(self) -> int:
        return len(self.failure_excerpt)

    def __bool__(self) -> bool:
        return bool(self.failure_excerpt)

    def splitlines(self, keepends: bool = False) -> list[str]:
        return self.failure_excerpt.splitlines(keepends)

    def __contains__(self, item: str) -> bool:
        return item in self.failure_excerpt


class EvidenceTriage:
    """Application interactor extracting bounded diagnostic excerpts from test/harness logs."""

    def __init__(
        self,
        ticket_id: str | None = None,
        runtime_paths: RuntimePaths | None = None,
    ) -> None:
        self.ticket_id = ticket_id
        self.runtime_paths = runtime_paths or RuntimePaths()

    @classmethod
    def extract(
        cls_or_self,
        log_path: Path | str,
        exit_code: int = 0,
        duration: float = 0.0,
        ticket_id: str | None = None,
        runtime_paths: RuntimePaths | None = None,
        artifacts: list[str] | tuple[str, ...] | None = None,
    ) -> TriageResult:
        """Parse log, extract bounded failure excerpt, and write summary.json atomically."""
        if isinstance(cls_or_self, EvidenceTriage):
            effective_ticket_id = ticket_id or cls_or_self.ticket_id
            effective_paths = runtime_paths or cls_or_self.runtime_paths
        else:
            effective_ticket_id = ticket_id
            effective_paths = runtime_paths or RuntimePaths()

        path_obj = Path(log_path)
        resolved_ticket_id = cls_or_self._resolve_ticket_id(path_obj, effective_ticket_id)

        lines = cls_or_self._read_lines(path_obj)
        first_failing_test, error_message, excerpt = cls_or_self._extract_failure_info(
            lines, exit_code
        )

        # Collect artifacts
        artifact_set: set[str] = set()
        if artifacts:
            artifact_set.update(artifacts)
        if path_obj.exists():
            artifact_set.add(path_obj.name)

        # Evidence dir resolution
        evidence_dir = effective_paths.ensure_evidence_dir(resolved_ticket_id)
        if evidence_dir.exists():
            for entry in evidence_dir.iterdir():
                if entry.is_file() and entry.name != "summary.json" and not entry.name.endswith(".tmp"):
                    artifact_set.add(entry.name)

        # Also check log_path parent if different from evidence_dir
        if path_obj.parent.exists() and path_obj.parent.resolve() != evidence_dir.resolve():
            for entry in path_obj.parent.iterdir():
                if entry.is_file() and entry.name != "summary.json" and not entry.name.endswith(".tmp"):
                    artifact_set.add(entry.name)

        artifact_list = sorted(artifact_set)

        # Construct payload and write summary.json atomically
        summary_payload = {
            "exit_code": int(exit_code),
            "duration": float(duration),
            "failure_excerpt": excerpt,
            "first_failing_test": first_failing_test,
            "error_message": error_message,
            "artifacts": artifact_list,
            "artifact_files": artifact_list,
        }
        summary_content = json.dumps(summary_payload, indent=2)

        summary_file = evidence_dir / "summary.json"
        atomic_write_text(summary_file, summary_content)

        # If log_path was in a separate directory (e.g. temporary test directory), also write there
        if path_obj.parent.exists() and path_obj.parent.resolve() != evidence_dir.resolve():
            local_summary = path_obj.parent / "summary.json"
            atomic_write_text(local_summary, summary_content)

        return TriageResult(
            failure_excerpt=excerpt,
            exit_code=int(exit_code),
            duration=float(duration),
            first_failing_test=first_failing_test,
            error_message=error_message,
            artifacts=tuple(artifact_list),
            summary_path=summary_file,
        )

    @classmethod
    def _resolve_ticket_id(cls, log_path: Path, explicit_ticket_id: str | None) -> str:
        if explicit_ticket_id and TICKET_ID_PATTERN.match(explicit_ticket_id):
            return explicit_ticket_id
        # Infer from log_path parts
        for part in reversed(log_path.parts):
            if TICKET_ID_PATTERN.match(part):
                return part
        return "T000"

    @classmethod
    def _read_lines(cls, log_path: Path) -> list[str]:
        if not log_path.exists() or log_path.stat().st_size == 0:
            return []
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                return f.readlines()
        except Exception:
            with open(log_path, "rb") as f:
                raw = f.read()
            return raw.decode("utf-8", errors="replace").splitlines(keepends=True)

    @classmethod
    def _extract_failure_info(
        cls, lines: list[str], exit_code: int
    ) -> tuple[str | None, str | None, str]:
        if not lines:
            if exit_code == 0:
                return None, None, ""
            excerpt = f"Process failed with exit code {exit_code} (empty log output)"
            return None, f"Process failed with exit code {exit_code}", excerpt

        # Clean check
        has_failure_marker = any(
            any(marker in strip_ansi(line) for marker in _FAILURE_MARKERS) for line in lines
        )
        if exit_code == 0 and not has_failure_marker:
            return None, None, ""

        # Find first failing test
        test_ids = extract_test_identifiers(lines)
        first_failing_test = test_ids[0] if test_ids else None

        # Find error message
        error_message: str | None = None
        for raw_line in lines:
            line = strip_ansi(raw_line).strip()
            for pattern in _ERROR_LINE_PATTERNS:
                m = pattern.search(line)
                if m:
                    error_message = m.group(1).strip()
                    break
            if error_message:
                break

        # Extract failure block (focusing on the first failing test)
        excerpt_lines: list[str] = []

        # 1. Try finding pytest section: ____ test_name ____
        start_idx: int | None = None
        for i, raw_line in enumerate(lines):
            line = strip_ansi(raw_line)
            if _TEST_HEADER_RE.match(line):
                start_idx = i
                break

        if start_idx is not None:
            # Collect from start_idx until next test header or summary header
            for raw_line in lines[start_idx:]:
                line = strip_ansi(raw_line)
                # If we encounter a second test header, stop
                if len(excerpt_lines) > 0 and _TEST_HEADER_RE.match(line):
                    break
                if len(excerpt_lines) > 0 and _SUMMARY_HEADER_RE.match(line):
                    break
                excerpt_lines.append(raw_line)
                if len(excerpt_lines) >= MAX_EXCERPT_LINES:
                    break
        else:
            # 2. Look for first line containing a failure marker
            first_marker_idx: int | None = None
            for i, raw_line in enumerate(lines):
                line = strip_ansi(raw_line)
                if any(marker in line for marker in _FAILURE_MARKERS):
                    first_marker_idx = i
                    break

            if first_marker_idx is not None:
                start = max(0, first_marker_idx - 2)
                for raw_line in lines[start:]:
                    line = strip_ansi(raw_line)
                    # If we encounter a summary header or subsequent failure header, stop if we already have lines
                    if len(excerpt_lines) > 0 and _SUMMARY_HEADER_RE.match(line):
                        break
                    excerpt_lines.append(raw_line)
                    if len(excerpt_lines) >= MAX_EXCERPT_LINES:
                        break
            else:
                # 3. Fallback: tail of log
                tail = lines[-MAX_EXCERPT_LINES:]
                excerpt_lines = [f"Process failed with exit code {exit_code}:\n"] + tail

        # Sanitize and bound
        raw_text = "".join(excerpt_lines)
        clean = strip_ansi(raw_text).strip()
        bounded_lines = clean.splitlines()[:MAX_EXCERPT_LINES]
        clean_bounded = "\n".join(bounded_lines)
        if len(clean_bounded) > MAX_EXCERPT_CHARS:
            clean_bounded = clean_bounded[: MAX_EXCERPT_CHARS - 3] + "..."
            clean_bounded = clean_bounded[:MAX_EXCERPT_CHARS]
            clean_bounded = "\n".join(clean_bounded.splitlines()[:MAX_EXCERPT_LINES])

        return first_failing_test, error_message, clean_bounded
