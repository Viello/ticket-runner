"""Crash recovery orchestrator restoring in-flight ticket execution across crashes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

from runner.application.git_operations import GitOperations
from runner.application.state_coordinator import StateCoordinator
from runner.application.worker_supervisor import (
    RunTerminationReason,
    SessionRunResult,
    WorkerSupervisor,
)
from runner.domain.exceptions import StateFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.state import RunnerState, StateStatus
from runner.domain.ticket import Ticket
from runner.ports.state_store import StateStore
from runner.ports.ticket_repository import TicketRepository

logger = logging.getLogger(__name__)

ACTIVE_WORK_STATUSES = (
    StateStatus.WORKING,
    StateStatus.GATEKEEPER,
    StateStatus.WAITING_FOR_USER,
    StateStatus.PAUSE_REQUESTED,
)

IGNORED_DIR_NAMES = frozenset({
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".coverage",
    "htmlcov",
    ".venv",
    "venv",
    "env",
    "build",
    "dist",
    ".git",
})

IGNORED_FILE_EXTENSIONS = (".pyc", ".pyo", ".pyd")


@dataclass(frozen=True)
class RecoveryResult:
    """Outcome of the startup crash recovery inspection."""

    action: str
    recovered: bool
    ticket_id: str | None = None
    session_id: str | None = None
    uncommitted_files: tuple[str, ...] = ()
    quarantine_path: Path | None = None
    warning_logged: bool = False
    session_run_result: SessionRunResult | None = None


class CrashRecoveryCoordinator:
    """Coordinates startup state inspection, working tree verification, and session resumption."""

    def __init__(
        self,
        state_store: StateStore,
        git_operations: GitOperations,
        worker_supervisor: WorkerSupervisor,
        state_coordinator: StateCoordinator | None = None,
        runtime_paths: RuntimePaths | None = None,
        ticket_store: TicketRepository | None = None,
        printer: Callable[[str], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._state_store = state_store
        self._git_operations = git_operations
        self._worker_supervisor = worker_supervisor
        self._state_coordinator = state_coordinator
        self._runtime_paths = runtime_paths or RuntimePaths()
        self._ticket_store = ticket_store
        self._printer = printer
        self._clock = clock

    @property
    def state_store(self) -> StateStore:
        """Underlying state store port."""
        return self._state_store

    @property
    def git_operations(self) -> GitOperations:
        """Underlying git operations interactor."""
        return self._git_operations

    @property
    def worker_supervisor(self) -> WorkerSupervisor:
        """Underlying worker supervisor."""
        return self._worker_supervisor

    @property
    def state_coordinator(self) -> StateCoordinator | None:
        """Coordinating service for runner state persistence."""
        return self._state_coordinator

    @property
    def runtime_paths(self) -> RuntimePaths:
        """Runtime paths value object."""
        return self._runtime_paths

    @property
    def ticket_store(self) -> TicketRepository | None:
        """Backing ticket repository if available."""
        return self._ticket_store

    def _log_or_print(self, msg: str) -> None:
        """Emit log message to printer if configured."""
        if self._printer is not None:
            try:
                self._printer(msg)
            except Exception:
                pass

    def _now_timestamp(self) -> str:
        """Return formatted UTC timestamp for quarantine filename without invalid characters."""
        if self._clock is not None:
            try:
                dt = datetime.fromtimestamp(self._clock(), tz=timezone.utc)
                return dt.strftime("%Y%m%dT%H%M%SZ")
            except Exception:
                pass
        return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def _resolve_state_path(self) -> Path:
        """Locate the state file path on disk."""
        if hasattr(self._state_store, "path"):
            return Path(getattr(self._state_store, "path"))
        return self._runtime_paths.state_path

    def quarantine_corrupt_state(self, exc: Exception | str) -> Path | None:
        """Quarantine corrupted state.json by renaming, logging diagnostic, and writing clean idle state."""
        state_path = self._resolve_state_path()
        corrupt_path: Path | None = None
        ts = self._now_timestamp()

        if state_path.is_file():
            corrupt_path = state_path.with_name(f"{state_path.name}.corrupt.{ts}")
            counter = 1
            while corrupt_path.exists():
                corrupt_path = state_path.with_name(f"{state_path.name}.corrupt.{ts}_{counter}")
                counter += 1
            try:
                state_path.rename(corrupt_path)
            except Exception as ren_err:
                logger.error(f"Failed to rename corrupted state file '{state_path}': {ren_err}")

        err_msg = (
            f"[Runner] Error: Corrupted state file '{state_path.name}' quarantined to "
            f"'{corrupt_path.name if corrupt_path else 'unknown'}': {exc}"
        )
        logger.error(err_msg)
        self._log_or_print(err_msg)

        # Initialize clean state document
        clean_state = RunnerState.idle(branch="agent/ticket-runner")
        try:
            self._state_store.write(clean_state.to_dict())
            if self._state_coordinator is not None:
                self._state_coordinator.save_state(clean_state)
        except Exception as wr_err:
            logger.error(f"Failed to initialize clean state document: {wr_err}")

        return corrupt_path

    def _is_ignored_path(self, path: str) -> bool:
        """Determine whether a path is runtime state (.agent/) or a build artifact."""
        norm = path.replace("\\", "/").strip("/")
        parts = norm.split("/")
        if not parts or parts[0] == ".agent":
            return True
        if any(p in IGNORED_DIR_NAMES or p.endswith(".egg-info") for p in parts):
            return True
        if any(norm.endswith(ext) for ext in IGNORED_FILE_EXTENSIONS):
            return True
        return False

    def _parse_uncommitted_files(self, porcelain_output: str) -> list[str]:
        """Parse git status --porcelain output and return uncommitted files ignoring .agent/ and build artifacts."""
        files: list[str] = []
        for line in porcelain_output.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) < 2:
                continue
            raw_path = parts[1].strip()
            if " -> " in raw_path:
                raw_path = raw_path.split(" -> ", 1)[1].strip()
            raw_path = raw_path.strip('"').strip("'")
            if self._is_ignored_path(raw_path):
                continue
            files.append(raw_path)
        return files

    def _find_latest_checkpoint(self, ticket_id: str) -> Path | None:
        """Find the latest handoff checkpoint file for the ticket."""
        checkpoint_dir = self._runtime_paths.checkpoint_dir(ticket_id)
        handoff_file = checkpoint_dir / "handoff.md"
        if handoff_file.is_file():
            return handoff_file
        if checkpoint_dir.is_dir():
            md_files = list(checkpoint_dir.glob("*.md"))
            if md_files:
                md_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                return md_files[0]
        return None

    def _resolve_ticket(self, ticket_id: str) -> Ticket | str:
        """Lookup Ticket object from ticket repository if available, or fall back to ticket ID string."""
        if self._ticket_store is not None:
            try:
                for t in self._ticket_store.list_all_pending():
                    if t.id == ticket_id:
                        return t
            except Exception:
                pass
        return ticket_id

    def construct_reconnect_prompt(self, ticket_id: str, uncommitted_files: Sequence[str]) -> str:
        """Construct reconnection prompt embedding detected uncommitted files or clean tree notice."""
        if uncommitted_files:
            files_str = ", ".join(uncommitted_files)
            return (
                f"Resuming session after restart. Uncommitted edits detected in: {files_str}. "
                f"Continue implementation for ticket {ticket_id}."
            )
        return f"Resuming session after restart. Continue implementation for ticket {ticket_id}."

    def construct_session_b_prompt(
        self,
        ticket_id: str,
        checkpoint_path: Path | str | None,
        uncommitted_files: Sequence[str] = (),
    ) -> str:
        """Construct Session B prompt with checkpoint reference or fallback."""
        if checkpoint_path is not None:
            posix_path = Path(checkpoint_path).as_posix()
            return (
                f"Read the context handoff document at `{posix_path}`, "
                f"inspect `git status`, then continue working on ticket {ticket_id}."
            )
        return self.construct_reconnect_prompt(ticket_id, uncommitted_files)

    async def recover(self) -> RecoveryResult:
        """Inspect on-disk state and recover in-flight ticket execution across crashes."""
        # 1. Inspect state.json
        state_doc: dict[str, Any] | None
        try:
            state_doc = self._state_store.read()
        except StateFormatError as exc:
            corrupt_path = self.quarantine_corrupt_state(exc)
            return RecoveryResult(action="quarantined", recovered=False, quarantine_path=corrupt_path)
        except Exception as exc:
            logger.warning(f"Unexpected error reading state file: {exc}")
            return RecoveryResult(action="none", recovered=False)

        if state_doc is None:
            return RecoveryResult(action="none", recovered=False)

        try:
            runner_state = RunnerState.from_dict(state_doc)
        except StateFormatError as exc:
            corrupt_path = self.quarantine_corrupt_state(exc)
            return RecoveryResult(action="quarantined", recovered=False, quarantine_path=corrupt_path)

        # 2. Check for active work
        if (
            runner_state.status == StateStatus.IDLE
            or runner_state.active_ticket_id is None
            or runner_state.status not in ACTIVE_WORK_STATUSES
        ):
            return RecoveryResult(action="none", recovered=False)

        ticket_id = runner_state.active_ticket_id

        # 3. Inspect working tree status
        try:
            status_output = await self._git_operations.status_porcelain()
        except Exception as exc:
            logger.warning(f"Failed to inspect working tree status: {exc}")
            status_output = ""

        uncommitted_files = self._parse_uncommitted_files(status_output)

        # 4. Inspect tui_open
        warning_logged = False
        if runner_state.tui_open:
            warning_logged = True
            warn_msg = (
                f"Runner exited while TUI session was open (session: {runner_state.tui_session_id}). "
                f"TUI may still be running. Resuming managed execution."
            )
            logger.warning(warn_msg)
            self._log_or_print(warn_msg)

            runner_state = runner_state.clear_tui()
            if self._state_coordinator is not None:
                self._state_coordinator.save_state(runner_state)
            else:
                self._state_store.write(runner_state.to_dict())

        # 5. Build reconnection prompt
        reconnect_prompt = self.construct_reconnect_prompt(ticket_id, uncommitted_files)

        # 6. Attempt session resumption if opencode_session_id is recorded
        resumption_failed = False
        resumed_run: SessionRunResult | None = None

        if runner_state.opencode_session_id is not None:
            try:
                resumed_run = await self._worker_supervisor.run(
                    ticket=self._resolve_ticket(ticket_id),
                    prompt=reconnect_prompt,
                    session_id=runner_state.opencode_session_id,
                )
                if (
                    resumed_run.is_crash
                    or resumed_run.exit_code != 0
                    or resumed_run.reason in (RunTerminationReason.DROPPED, RunTerminationReason.STALLED)
                ):
                    resumption_failed = True
            except Exception as exc:
                logger.warning(f"Session resumption failed with exception: {exc}")
                resumption_failed = True
        else:
            resumption_failed = True

        if not resumption_failed and resumed_run is not None:
            return RecoveryResult(
                action="resumed_session",
                recovered=True,
                ticket_id=ticket_id,
                session_id=runner_state.opencode_session_id,
                uncommitted_files=tuple(uncommitted_files),
                warning_logged=warning_logged,
                session_run_result=resumed_run,
            )

        # 7. Checkpoint fallback: discover latest handoff.md and initiate Session B
        latest_checkpoint = self._find_latest_checkpoint(ticket_id)
        session_b_prompt = self.construct_session_b_prompt(
            ticket_id, latest_checkpoint, uncommitted_files
        )

        if hasattr(self._worker_supervisor, "reset_budget_monitor"):
            self._worker_supervisor.reset_budget_monitor()

        session_b_run = await self._worker_supervisor.run(
            ticket=self._resolve_ticket(ticket_id),
            prompt=session_b_prompt,
            session_id=None,
        )

        # Persist new session ID if one was established
        new_session_id = session_b_run.session_id
        if new_session_id:
            runner_state = replace(runner_state, opencode_session_id=new_session_id)
            if self._state_coordinator is not None:
                self._state_coordinator.save_state(runner_state)
            else:
                self._state_store.write(runner_state.to_dict())

        return RecoveryResult(
            action="resumed_checkpoint",
            recovered=True,
            ticket_id=ticket_id,
            session_id=new_session_id,
            uncommitted_files=tuple(uncommitted_files),
            warning_logged=warning_logged,
            session_run_result=session_b_run,
        )
