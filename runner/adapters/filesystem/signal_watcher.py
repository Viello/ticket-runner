"""Filesystem-backed SignalRepository reading and writing .agent/ Signal JSON files."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import json
from pathlib import Path
from typing import Any, Mapping, TypeVar

from runner.adapters.markdown.atomic_write import TEMP_SUFFIX, atomic_write_text
from runner.domain.exceptions import SignalFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import QuestionSignal, ReadySignal, SignalStatus
from runner.ports.signal_repository import SignalRepository

_T = TypeVar("_T")


def _serialize(payload: Mapping[str, Any]) -> str:
    """Render a Signal payload as stable UTF-8 JSON with a trailing newline."""
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


class FilesystemSignalRepository(SignalRepository):
    """Binds the SignalRepository port to RuntimePaths using atomic file writes."""

    def __init__(self, runtime_paths: RuntimePaths) -> None:
        self._runtime_paths = runtime_paths

    def read_ready(self, ticket_id: str) -> ReadySignal | None:
        """Read the Ticket's ready Signal without consuming it."""
        path = self._runtime_paths.ready_signal_path(ticket_id)
        text = self._read_text_if_present(path)
        if text is None:
            return None
        return self._parse_strictly(
            text, path, "ready Signal", lambda raw: ReadySignal.parse(raw, ticket_id)
        )

    def read_pending_question(self, ticket_id: str) -> QuestionSignal | None:
        """Read the Ticket's question Signal unless it is absent or already answered."""
        path = self._runtime_paths.question_path(ticket_id)
        text = self._read_text_if_present(path)
        if text is None:
            return None
        question = self._parse_strictly(
            text, path, "question Signal", lambda raw: QuestionSignal.parse(raw, ticket_id)
        )
        if question.status is SignalStatus.ANSWERED:
            return None
        return question

    def consume_ready(self, ticket_id: str) -> None:
        """Delete the Ticket's ready Signal; a missing file is a no-op."""
        self._remove_if_present(self._runtime_paths.ready_signal_path(ticket_id))

    def write_answer(self, ticket_id: str, answer: str) -> QuestionSignal:
        """Atomically rewrite the pending question as answered, preserving every other field."""
        path = self._runtime_paths.question_path(ticket_id)
        text = self._read_text_if_present(path)
        if text is None:
            raise SignalFormatError(f"Question signal file not found: '{path}'")
        question = self._parse_strictly(
            text, path, "question Signal", lambda raw: QuestionSignal.parse(raw, ticket_id)
        )
        answered = replace(question, status=SignalStatus.ANSWERED, answer=answer)
        payload: dict[str, Any] = json.loads(text)
        payload["status"] = answered.status.value
        payload["answer"] = answered.answer
        self._runtime_paths.ensure_questions_dir()
        atomic_write_text(path, _serialize(payload))
        return answered

    def clean_question(self, ticket_id: str) -> None:
        """Delete the Ticket's question Signal file if pending or malformed, retaining answered files."""
        path = self._runtime_paths.question_path(ticket_id)
        text = self._read_text_if_present(path)
        if text is None:
            return
        try:
            payload = json.loads(text)
            if isinstance(payload, Mapping) and payload.get("status") == SignalStatus.ANSWERED.value:
                return
        except Exception:
            pass
        self._remove_if_present(path)

    def purge(self, ticket_id: str) -> None:
        """Delete both Signal artifacts for the Ticket, creating directories as needed."""
        self._runtime_paths.ensure_signals_dir()
        self._runtime_paths.ensure_questions_dir()
        self._remove_if_present(self._runtime_paths.ready_signal_path(ticket_id))
        self._remove_if_present(self._runtime_paths.question_path(ticket_id))

    def _read_text_if_present(self, path: Path) -> str | None:
        """Read UTF-8 text, treating a vanished file as absence and bad bytes as malformed."""
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except UnicodeDecodeError as exc:
            raise SignalFormatError(f"Signal file '{path}' is not valid UTF-8: {exc}") from exc

    def _parse_strictly(
        self, text: str, path: Path, label: str, parser: Callable[[str], _T]
    ) -> _T:
        """Parse a Signal payload, naming the offending file in any format error."""
        try:
            return parser(text)
        except SignalFormatError as exc:
            raise SignalFormatError(f"Malformed {label} file '{path}': {exc}") from exc

    def _remove_if_present(self, path: Path) -> None:
        """Best-effort delete of an artifact and its atomic-write temp sibling."""
        for candidate in (path, path.with_name(path.name + TEMP_SUFFIX)):
            try:
                candidate.unlink()
            except FileNotFoundError:
                continue
