"""Runtime paths value object resolving .agent/ artifact and directory paths."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_AGENT_DIR = Path(".agent")
SESSION_ID_PATTERN = re.compile(r"^ses_[A-Za-z0-9]+$")
TICKET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def is_valid_session_id(session_id: object) -> bool:
    """Return True if session_id matches the OpenCode session allowlist (^ses_[A-Za-z0-9]+$)."""
    if not isinstance(session_id, str):
        return False
    return bool(SESSION_ID_PATTERN.match(session_id))


@dataclass(frozen=True)
class RuntimePaths:
    """Frozen value object computing .agent/ runtime artifact paths.

    Pure path computation with on-demand directory creation helpers.
    Performs no process or network I/O, and does not write to disk at import or instantiation.
    """

    root_dir: Path = DEFAULT_AGENT_DIR

    def __post_init__(self) -> None:
        if isinstance(self.root_dir, str):
            object.__setattr__(self, "root_dir", Path(self.root_dir))

    @property
    def signals_dir(self) -> Path:
        """Directory for worker signals (.agent/signals)."""
        return self.root_dir / "signals"

    @property
    def questions_dir(self) -> Path:
        """Directory for worker clarification questions (.agent/questions)."""
        return self.root_dir / "questions"

    @property
    def checkpoints_dir(self) -> Path:
        """Base directory for context handoff checkpoints (.agent/checkpoints)."""
        return self.root_dir / "checkpoints"

    @property
    def logs_dir(self) -> Path:
        """Directory for worker session logs (.agent/logs)."""
        return self.root_dir / "logs"

    @property
    def state_path(self) -> Path:
        """Path to the runner state file (.agent/state.json)."""
        return self.root_dir / "state.json"

    @property
    def status_file(self) -> Path:
        """Path to the runner status file (.agent/status.json)."""
        return self.root_dir / "status.json"

    def _validate_ticket_id(self, ticket_id: str) -> str:
        """Validate ticket_id against allowlist to prevent directory traversal."""
        if not isinstance(ticket_id, str) or not TICKET_ID_PATTERN.match(ticket_id):
            raise ValueError(f"Invalid ticket identifier or path traversal detected: {ticket_id!r}")
        return ticket_id

    def _check_containment(self, target: Path, base: Path) -> Path:
        """Ensure resolved target path is strictly contained within base directory."""
        try:
            base_resolved = base.resolve()
            target_resolved = target.resolve()
            if not target_resolved.is_relative_to(base_resolved):
                raise ValueError(f"Path traversal detected escaping {base}: {target}")
        except (ValueError, RuntimeError) as exc:
            raise ValueError(f"Path traversal detected escaping {base}: {target}") from exc
        return target

    def ready_signal_path(self, ticket_id: str) -> Path:
        """Path to a ticket's ready signal file (.agent/signals/{ticket_id}_ready.json)."""
        self._validate_ticket_id(ticket_id)
        target = self.signals_dir / f"{ticket_id}_ready.json"
        return self._check_containment(target, self.signals_dir)

    def question_path(self, ticket_id: str) -> Path:
        """Path to a ticket's question file (.agent/questions/{ticket_id}.json)."""
        self._validate_ticket_id(ticket_id)
        target = self.questions_dir / f"{ticket_id}.json"
        return self._check_containment(target, self.questions_dir)

    def question_file_path(self, ticket_id: str) -> Path:
        """Alias to question_path for caller convenience."""
        return self.question_path(ticket_id)

    def checkpoint_dir(self, ticket_id: str) -> Path:
        """Directory for a ticket's handoff checkpoints (.agent/checkpoints/{ticket_id})."""
        self._validate_ticket_id(ticket_id)
        target = self.checkpoints_dir / ticket_id
        return self._check_containment(target, self.checkpoints_dir)

    def checkpoint_path(self, ticket_id: str) -> Path:
        """Path to a ticket's handoff checkpoint (.agent/checkpoints/{ticket_id}/handoff.md)."""
        return self.checkpoint_dir(ticket_id) / "handoff.md"

    def session_log_path(self, ticket_id: str, session_id: str) -> Path:
        """Path to a worker session's JSONL telemetry log (.agent/logs/{ticket_id}_session_{session_id}.jsonl)."""
        self._validate_ticket_id(ticket_id)
        if not is_valid_session_id(session_id):
            raise ValueError(f"Invalid session identifier or path traversal detected: {session_id!r}")
        target = self.logs_dir / f"{ticket_id}_session_{session_id}.jsonl"
        return self._check_containment(target, self.logs_dir)

    def session_jsonl_path(self, ticket_id: str, session_id: str) -> Path:
        """Alias to session_log_path for caller convenience."""
        return self.session_log_path(ticket_id, session_id)

    def session_stderr_path(self, ticket_id: str, session_id: str) -> Path:
        """Path to a worker session's stderr sidecar log (.agent/logs/{ticket_id}_session_{session_id}.stderr.log)."""
        self._validate_ticket_id(ticket_id)
        if not is_valid_session_id(session_id):
            raise ValueError(f"Invalid session identifier or path traversal detected: {session_id!r}")
        target = self.logs_dir / f"{ticket_id}_session_{session_id}.stderr.log"
        return self._check_containment(target, self.logs_dir)

    def session_stderr_log_path(self, ticket_id: str, session_id: str) -> Path:
        """Alias to session_stderr_path for caller convenience."""
        return self.session_stderr_path(ticket_id, session_id)

    def diagnostic_log_path(self, ticket_id: str) -> Path:
        """Path to a ticket's diagnostic report log (.agent/logs/{ticket_id}_diagnostic.md)."""
        self._validate_ticket_id(ticket_id)
        target = self.logs_dir / f"{ticket_id}_diagnostic.md"
        return self._check_containment(target, self.logs_dir)

    def smoke_log_path(self, spec_slug: str) -> Path:
        """Path to a spec's smoke log (.agent/smoke_log_{safe_slug}.md).

        Sanitizes spec_slug against directory traversal by replacing non-alphanumeric,
        non-hyphen characters with underscores and ensuring containment within root_dir.
        """
        safe_slug = re.sub(r"[^\w\-]", "_", spec_slug)
        target = self.root_dir / f"smoke_log_{safe_slug}.md"
        try:
            root_resolved = self.root_dir.resolve()
            if not target.resolve().is_relative_to(root_resolved):
                raise ValueError(f"Path traversal detected escaping root_dir: {spec_slug!r}")
        except (ValueError, RuntimeError) as exc:
            raise ValueError(f"Path traversal detected escaping root_dir: {spec_slug!r}") from exc
        return target


    def safe_session_paths(
        self, ticket_id: str, session_id: str
    ) -> tuple[Path, Path] | None:
        """Return safe (jsonl_path, stderr_path) if both ticket_id and session_id pass allowlists and containment.

        Returns None if ticket_id or session_id is invalid or if the resulting paths escape logs_dir.
        """
        if not isinstance(ticket_id, str) or not TICKET_ID_PATTERN.match(ticket_id):
            return None
        if not is_valid_session_id(session_id):
            return None

        jsonl = self.session_log_path(ticket_id, session_id)
        stderr = self.session_stderr_path(ticket_id, session_id)

        try:
            logs_resolved = self.logs_dir.resolve()
            if not jsonl.resolve().is_relative_to(logs_resolved):
                return None
            if not stderr.resolve().is_relative_to(logs_resolved):
                return None
        except (ValueError, RuntimeError):
            return None

        return jsonl, stderr

    def ensure_signals_dir(self) -> Path:
        """Create and return the signals directory."""
        self.signals_dir.mkdir(parents=True, exist_ok=True)
        return self.signals_dir

    def ensure_questions_dir(self) -> Path:
        """Create and return the questions directory."""
        self.questions_dir.mkdir(parents=True, exist_ok=True)
        return self.questions_dir

    def ensure_checkpoints_dir(self) -> Path:
        """Create and return the base checkpoints directory."""
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        return self.checkpoints_dir

    def ensure_checkpoint_dir(self, ticket_id: str) -> Path:
        """Create and return the ticket-specific checkpoint directory."""
        d = self.checkpoint_dir(ticket_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def ensure_logs_dir(self) -> Path:
        """Create and return the logs directory."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        return self.logs_dir

    def ensure_parent_dir(self, path: Path | str) -> Path:
        """Ensure the parent directory of a path exists on demand.

        Handles empty parent edge cases safely without attempting to create an empty path.
        """
        parent = Path(path).parent
        if str(parent) not in ("", "."):
            parent.mkdir(parents=True, exist_ok=True)
        return parent

    def ensure_all_dirs(self, ticket_id: str | None = None) -> None:
        """Create all standard runtime directories on demand, optionally including a ticket checkpoint dir."""
        self.ensure_signals_dir()
        self.ensure_questions_dir()
        self.ensure_checkpoints_dir()
        if ticket_id is not None:
            self.ensure_checkpoint_dir(ticket_id)
        self.ensure_logs_dir()
