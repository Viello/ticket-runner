"""Worker supervisor orchestrating OpenCode session runs, live decoding, and telemetry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import io
from pathlib import Path
import sys
from typing import Any, TextIO

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.opencode.opencode_worker import (
    build_opencode_run_command,
    decode_event,
)
from runner.domain.config import TokenBudgetConfig
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.telemetry import BudgetAction, BudgetMonitor
from runner.domain.ticket import Ticket
from runner.ports.command_runner import CommandRunner


class RunTerminationReason(str, Enum):
    """Reason for session run termination."""

    EXITED = "EXITED"
    KILLED_HANDOFF = "KILLED_HANDOFF"
    KILLED_CEILING = "KILLED_CEILING"
    STALLED = "STALLED"
    DROPPED = "DROPPED"


@dataclass(frozen=True)
class SessionRunResult:
    """Outcome of a single supervised OpenCode Worker session run."""

    reason: RunTerminationReason = RunTerminationReason.EXITED
    session_id: str | None = None
    exit_code: int = 0
    occupancy: int = 0
    ready_signal_present: bool = False
    stderr_tail: str = ""
    jsonl_path: Path | None = None
    stderr_path: Path | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.reason, str) and not isinstance(
            self.reason, RunTerminationReason
        ):
            try:
                object.__setattr__(self, "reason", RunTerminationReason(self.reason))
            except ValueError:
                pass

    @property
    def latest_occupancy(self) -> int:
        """Alias to occupancy for caller convenience."""
        return self.occupancy

    @property
    def log_path(self) -> Path | None:
        """Alias to jsonl_path for caller convenience."""
        return self.jsonl_path

    @property
    def log_paths(self) -> tuple[Path, ...]:
        """Tuple of existing log paths (jsonl, stderr) created for this run."""
        return tuple(p for p in (self.jsonl_path, self.stderr_path) if p is not None)


def _default_notify(notice: str) -> None:
    """Default notification sink writing plain lines to stderr."""
    sys.stderr.write(f"{notice}\n")
    sys.stderr.flush()


class WorkerSupervisor:
    """Supervises OpenCode Worker subprocess session runs with telemetry and logging."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        runtime_paths: RuntimePaths | None = None,
        budget_monitor: BudgetMonitor | None = None,
        budget_config: TokenBudgetConfig | None = None,
        notify: Callable[[str], None] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self._cwd = cwd
        self._command_runner = command_runner or SubprocessRunner()
        self._runtime_paths = runtime_paths or (
            RuntimePaths(root_dir=cwd / ".agent") if cwd else RuntimePaths()
        )
        self._budget_monitor = budget_monitor or BudgetMonitor(config=budget_config)
        self._notify = notify or _default_notify

    async def run(
        self,
        ticket: Ticket | str,
        prompt: str,
        session_id: str | None = None,
    ) -> SessionRunResult:
        """Execute a single supervised OpenCode session run.

        Args:
            ticket: Ticket entity or ticket ID string.
            prompt: Prompt instruction or continuation message.
            session_id: Optional session identifier when resuming an existing session.

        Returns:
            SessionRunResult with termination reason, session ID, telemetry, and log paths.
        """
        ticket_id = ticket.id if isinstance(ticket, Ticket) else str(ticket)
        cmd = build_opencode_run_command(prompt=prompt, session_id=session_id)

        handle = await self._command_runner.spawn(cmd, cwd=self._cwd)

        active_session_id: str | None = session_id
        diagnostics: list[str] = []
        log_file: TextIO | None = None
        log_skipped: bool = False
        line_buffer: list[str] = []
        jsonl_target_path: Path | None = None
        stderr_target_path: Path | None = None

        def _init_logging(sid: str) -> None:
            nonlocal log_file, log_skipped, jsonl_target_path, stderr_target_path
            safe_paths = self._runtime_paths.safe_session_paths(ticket_id, sid)
            if safe_paths is None:
                log_skipped = True
                diag = (
                    f"[{ticket_id}] Diagnostic: Session ID '{sid}' rejected by allowlist "
                    f"or path containment; skipping log file creation."
                )
                diagnostics.append(diag)
                self._notify(diag)
                return

            jsonl_target_path, stderr_target_path = safe_paths
            self._runtime_paths.ensure_logs_dir()
            log_file = jsonl_target_path.open("a", encoding="utf-8", newline="")
            for buffered_line in line_buffer:
                log_file.write(buffered_line + "\n")
                log_file.flush()
            line_buffer.clear()

        # If resuming an existing session with an ID already provided, initialize logging
        if active_session_id is not None:
            _init_logging(active_session_id)

        try:
            async for line in handle.stdout_lines():
                if log_file is not None:
                    log_file.write(line + "\n")
                    log_file.flush()
                elif not log_skipped:
                    line_buffer.append(line)

                event = decode_event(line)
                if event is None:
                    diagnostics.append(
                        f"[{ticket_id}] Unparseable JSON stdout line skipped: {line[:100]}"
                    )
                    continue

                if active_session_id is None and event.session_id:
                    active_session_id = event.session_id
                    _init_logging(active_session_id)

                if not event.is_known:
                    diagnostics.append(
                        f"[{ticket_id}] Unknown event type skipped: {event.type}"
                    )
                    continue

                if event.type == "step_finish" and event.token_usage is not None:
                    action = self._budget_monitor.observe(event.token_usage)
                    if action == BudgetAction.WARN:
                        notice = (
                            f"[{ticket_id}] Token budget warning: occupancy reached "
                            f"{self._budget_monitor.latest_occupancy} tokens "
                            f"(warn threshold: {self._budget_monitor.warn_threshold})"
                        )
                        self._notify(notice)
        finally:
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass

        exit_code = await handle.wait()

        # Stderr sidecar logging
        if (
            active_session_id is not None
            and not log_skipped
            and stderr_target_path is not None
        ):
            self._runtime_paths.ensure_logs_dir()
            with stderr_target_path.open("a", encoding="utf-8") as sf:
                sf.write(handle.stderr)

        ready_signal_present = self._runtime_paths.ready_signal_path(ticket_id).is_file()

        raw_stderr = handle.stderr.strip()
        if raw_stderr:
            stderr_lines = raw_stderr.splitlines()
            stderr_tail = "\n".join(stderr_lines[-50:])
            if len(stderr_tail) > 4096:
                stderr_tail = stderr_tail[-4096:].strip()
        else:
            stderr_tail = ""

        if active_session_id is None or log_skipped:
            reason = RunTerminationReason.DROPPED
        else:
            reason = RunTerminationReason.EXITED

        return SessionRunResult(
            reason=reason,
            session_id=active_session_id,
            exit_code=exit_code,
            occupancy=self._budget_monitor.latest_occupancy,
            ready_signal_present=ready_signal_present,
            stderr_tail=stderr_tail,
            jsonl_path=jsonl_target_path if not log_skipped else None,
            stderr_path=stderr_target_path if not log_skipped else None,
            diagnostics=tuple(diagnostics),
        )

    run_session = run
