"""Worker supervisor orchestrating OpenCode session runs, live decoding, and telemetry."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import io
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, TextIO

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.opencode.opencode_worker import (
    OpenCodeEvent,
    build_opencode_run_command,
    decode_event,
    extract_resource_access,
)
from runner.domain.config import TokenBudgetConfig
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.telemetry import BudgetAction, BudgetMonitor
from runner.domain.ticket import Ticket
from runner.ports.command_runner import CommandRunner, ProcessHandle
from runner.ports.signal_repository import SignalRepository


logger = logging.getLogger(__name__)

STALL_SILENCE_SECONDS: float = 900.0
BOUNDED_RUN_TIMEOUT_SECONDS: float = 300.0
SIGNAL_GRACE_SECONDS: float = 10.0


class _AwaitableNone:
    """Lightweight awaitable returning None, supporting both sync and async call styles."""

    def __await__(self) -> Any:
        if False:
            yield
        return None


class RunTerminationReason(str, Enum):
    """Reason for session run termination."""

    EXITED = "EXITED"
    KILLED_HANDOFF = "KILLED_HANDOFF"
    KILLED_CEILING = "KILLED_CEILING"
    STALLED = "STALLED"
    DROPPED = "DROPPED"
    KILLED_SIGNAL = "KILLED_SIGNAL"
    KILLED_INTERRUPT = "KILLED_INTERRUPT"


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
    has_error_event: bool = False
    resources_accessed: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if isinstance(self.reason, str) and not isinstance(
            self.reason, RunTerminationReason
        ):
            try:
                object.__setattr__(self, "reason", RunTerminationReason(self.reason))
            except ValueError:
                pass
        if not isinstance(self.resources_accessed, frozenset):
            object.__setattr__(
                self, "resources_accessed", frozenset(self.resources_accessed)
            )

    @property
    def latest_occupancy(self) -> int:
        """Alias to occupancy for caller convenience."""
        return self.occupancy

    @property
    def log_path(self) -> Path | None:
        """Alias to jsonl_path for caller convenience."""
        return self.jsonl_path

    @property
    def skills_accessed(self) -> frozenset[str]:
        """Alias to resources_accessed for caller convenience."""
        return self.resources_accessed

    @property
    def log_paths(self) -> tuple[Path, ...]:
        """Tuple of existing log paths (jsonl, stderr) created for this run."""
        return tuple(p for p in (self.jsonl_path, self.stderr_path) if p is not None)

    @property
    def is_crash(self) -> bool:
        """Whether this session run suffered a crash (non-zero exit or stream error event)."""
        if self.reason in (RunTerminationReason.KILLED_SIGNAL, RunTerminationReason.KILLED_INTERRUPT):
            return False
        return self.exit_code != 0 or self.has_error_event


def _default_notify(notice: str) -> None:
    """Default notification sink writing plain lines to stderr."""
    sys.stderr.write(f"{notice}\n")
    sys.stderr.flush()


class WorkerSupervisor:
    """Supervises OpenCode Worker subprocess session runs with telemetry, watchdog, and termination ladder."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        runtime_paths: RuntimePaths | None = None,
        budget_monitor: BudgetMonitor | None = None,
        budget_config: TokenBudgetConfig | None = None,
        notify: Callable[[str], None] | None = None,
        cwd: Path | None = None,
        stall_timeout: float = STALL_SILENCE_SECONDS,
        bounded_timeout: float = BOUNDED_RUN_TIMEOUT_SECONDS,
        process_wait_timeout: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        on_event: Callable[[OpenCodeEvent], None] | None = None,
        on_budget_action: Callable[[BudgetAction, int], None] | None = None,
        signal_grace_timeout: float = SIGNAL_GRACE_SECONDS,
        signal_repository: SignalRepository | None = None,
        default_reasoning: str = "",
    ) -> None:
        self._cwd = cwd
        self._command_runner = command_runner or SubprocessRunner()
        self._runtime_paths = runtime_paths or (
            RuntimePaths(root_dir=cwd / ".agent") if cwd else RuntimePaths()
        )
        self._budget_monitor = budget_monitor or BudgetMonitor(config=budget_config)
        self._notify = notify or _default_notify
        self._stall_timeout = float(stall_timeout)
        self._bounded_timeout = float(bounded_timeout)
        self._process_wait_timeout = float(process_wait_timeout)
        self._clock = clock
        self._on_event = on_event
        self._on_budget_action = on_budget_action
        self._signal_grace_timeout = float(signal_grace_timeout)
        self._signal_repository = signal_repository
        self._default_reasoning = default_reasoning.strip() if default_reasoning else ""

        self._current_handle: ProcessHandle | None = None
        self._kill_reason: RunTerminationReason | None = None
        self._kill_event: asyncio.Event | None = None
        self._signal_first_seen_at: float | None = None

    @property
    def default_reasoning(self) -> str:
        """Configured default reasoning variant."""
        return self._default_reasoning

    @property
    def signal_grace_timeout(self) -> float:
        """Configured grace period in seconds before terminating a lingering Worker after Signal emission."""
        return self._signal_grace_timeout

    @property
    def signal_repository(self) -> SignalRepository | None:
        """Configured or injected SignalRepository port."""
        return self._signal_repository

    @property
    def signal_first_seen_at(self) -> float | None:
        """Timestamp when the active Ticket's Signal was first detected during this run."""
        return self._signal_first_seen_at

    @property
    def runtime_paths(self) -> RuntimePaths:
        """Runtime paths value object used by this supervisor."""
        return self._runtime_paths

    @property
    def command_runner(self) -> CommandRunner:
        """Command runner port used by this supervisor."""
        return self._command_runner

    @property
    def cwd(self) -> Path | None:
        """Configured working directory."""
        return self._cwd

    @property
    def on_budget_action(self) -> Callable[[BudgetAction, int], None] | None:
        """Callback invoked when BudgetMonitor observes a budget threshold action."""
        return self._on_budget_action

    @on_budget_action.setter
    def on_budget_action(
        self, callback: Callable[[BudgetAction, int], None] | None
    ) -> None:
        self._on_budget_action = callback

    def reset_budget_monitor(self) -> None:
        """Reset the budget monitor for a fresh worker session."""
        self._budget_monitor = BudgetMonitor(
            config=self._budget_monitor.config,
            model_limit=getattr(self._budget_monitor, "_model_limit", None),
        )

    def request_kill(self, reason: RunTerminationReason | str) -> _AwaitableNone:
        """External interrupt API to stop stream reading and run the termination ladder."""
        if isinstance(reason, str) and not isinstance(reason, RunTerminationReason):
            reason = RunTerminationReason(reason)
        self._kill_reason = reason
        if self._kill_event is not None and not self._kill_event.is_set():
            self._kill_event.set()
        return _AwaitableNone()

    async def _terminate_ladder(self, handle: ProcessHandle) -> None:
        """Execute termination ladder: graceful terminate -> tree-kill -> bounded wait."""
        try:
            await handle.terminate()
        except BaseException:
            pass

        if handle.pid > 0:
            try:
                await self._command_runner.run(
                    ["taskkill", "/PID", str(handle.pid), "/T", "/F"]
                )
            except BaseException:
                pass

        try:
            await asyncio.wait_for(handle.wait(), timeout=self._process_wait_timeout)
        except BaseException:
            pass

    def _is_signal_present(self, ticket_id: str) -> bool:
        """Check whether either the ready Signal or a pending/new question Signal exists."""
        if self._runtime_paths.ready_signal_path(ticket_id).is_file():
            return True
        if self._signal_repository is not None:
            try:
                if self._signal_repository.read_ready(ticket_id) is not None:
                    return True
            except Exception:
                return True
            try:
                if self._signal_repository.read_pending_question(ticket_id) is not None:
                    return True
            except Exception:
                if self._runtime_paths.question_path(ticket_id).is_file():
                    return True
        qpath = self._runtime_paths.question_path(ticket_id)
        if qpath.is_file():
            try:
                data = json.loads(qpath.read_text(encoding="utf-8"))
                if isinstance(data, dict) and data.get("status") == "answered":
                    return False
            except Exception:
                pass
            return True
        return False

    async def run(
        self,
        ticket: Ticket | str,
        prompt: str,
        session_id: str | None = None,
        bounded: bool = False,
    ) -> SessionRunResult:
        """Execute a single supervised OpenCode session run.

        Args:
            ticket: Ticket entity or ticket ID string.
            prompt: Prompt instruction or continuation message.
            session_id: Optional session identifier when resuming an existing session.
            bounded: Whether to enforce the wall-clock timeout cap (BOUNDED_RUN_TIMEOUT_SECONDS).

        Returns:
            SessionRunResult with termination reason, session ID, telemetry, and log paths.
        """
        ticket_id = ticket.id if isinstance(ticket, Ticket) else str(ticket)
        variant = (
            (ticket.reasoning.strip() if ticket.reasoning else "")
            if isinstance(ticket, Ticket)
            else ""
        ) or self._default_reasoning
        cmd = build_opencode_run_command(
            prompt=prompt, session_id=session_id, variant=variant
        )

        handle = await self._command_runner.spawn(cmd, cwd=self._cwd)
        self._current_handle = handle
        self._kill_reason = None
        self._kill_event = asyncio.Event()
        self._signal_first_seen_at = None

        active_session_id: str | None = session_id
        diagnostics: list[str] = []
        log_file: TextIO | None = None
        log_skipped: bool = False
        line_buffer: list[str] = []
        jsonl_target_path: Path | None = None
        stderr_target_path: Path | None = None
        termination_reason: RunTerminationReason | None = None
        has_error_event: bool = False
        resources_accessed: set[str] = set()

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

        start_time = self._clock()
        last_line_time = start_time

        try:
            iterator = handle.stdout_lines().__aiter__()
            while True:
                if self._kill_reason is not None:
                    termination_reason = self._kill_reason
                    break

                now = self._clock()
                elapsed_stall = now - last_line_time
                if elapsed_stall >= self._stall_timeout:
                    termination_reason = RunTerminationReason.STALLED
                    break

                if bounded:
                    elapsed_bounded = now - start_time
                    if elapsed_bounded >= self._bounded_timeout:
                        termination_reason = RunTerminationReason.STALLED
                        break

                if self._signal_first_seen_at is None:
                    if self._is_signal_present(ticket_id):
                        self._signal_first_seen_at = now

                if self._signal_first_seen_at is not None:
                    elapsed_signal = now - self._signal_first_seen_at
                    if elapsed_signal >= self._signal_grace_timeout:
                        termination_reason = RunTerminationReason.KILLED_SIGNAL
                        break

                remaining_stall = max(0.0, self._stall_timeout - elapsed_stall)
                if bounded:
                    remaining_bounded = max(0.0, self._bounded_timeout - (now - start_time))
                    step_timeout = min(remaining_stall, remaining_bounded)
                else:
                    step_timeout = remaining_stall

                if self._signal_first_seen_at is not None:
                    remaining_signal = max(0.0, self._signal_grace_timeout - (now - self._signal_first_seen_at))
                    step_timeout = min(step_timeout, remaining_signal)

                if step_timeout <= 0:
                    if (
                        self._signal_first_seen_at is not None
                        and (now - self._signal_first_seen_at) >= self._signal_grace_timeout
                    ):
                        termination_reason = RunTerminationReason.KILLED_SIGNAL
                    else:
                        termination_reason = RunTerminationReason.STALLED
                    break

                next_line_task = asyncio.ensure_future(iterator.__anext__())
                kill_task = asyncio.ensure_future(self._kill_event.wait())

                done, pending = await asyncio.wait(
                    [next_line_task, kill_task],
                    timeout=step_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

                if self._kill_reason is not None:
                    termination_reason = self._kill_reason
                    if next_line_task in done and not next_line_task.cancelled():
                        try:
                            line = next_line_task.result()
                            if log_file is not None:
                                log_file.write(line + "\n")
                                log_file.flush()
                            elif not log_skipped:
                                line_buffer.append(line)
                        except (StopAsyncIteration, Exception):
                            pass
                    break

                if not done:
                    now_timeout = self._clock()
                    if (
                        self._signal_first_seen_at is not None
                        and (now_timeout - self._signal_first_seen_at) >= self._signal_grace_timeout
                    ):
                        termination_reason = RunTerminationReason.KILLED_SIGNAL
                    elif bounded and (now_timeout - start_time) >= self._bounded_timeout:
                        termination_reason = RunTerminationReason.STALLED
                    elif (now_timeout - last_line_time) >= self._stall_timeout:
                        termination_reason = RunTerminationReason.STALLED
                    else:
                        termination_reason = RunTerminationReason.STALLED
                    break

                if kill_task in done:
                    termination_reason = self._kill_reason or RunTerminationReason.STALLED
                    break

                try:
                    line = next_line_task.result()
                except StopAsyncIteration:
                    break

                if log_file is not None:
                    log_file.write(line + "\n")
                    log_file.flush()
                elif not log_skipped:
                    line_buffer.append(line)

                arrival_time = self._clock()
                if arrival_time - last_line_time >= self._stall_timeout:
                    termination_reason = RunTerminationReason.STALLED
                    break

                if bounded and (arrival_time - start_time) >= self._bounded_timeout:
                    termination_reason = RunTerminationReason.STALLED
                    break

                if self._signal_first_seen_at is None:
                    if self._is_signal_present(ticket_id):
                        self._signal_first_seen_at = arrival_time

                if self._signal_first_seen_at is not None:
                    if (arrival_time - self._signal_first_seen_at) >= self._signal_grace_timeout:
                        termination_reason = RunTerminationReason.KILLED_SIGNAL
                        break

                last_line_time = arrival_time

                event = decode_event(line)

                try:
                    detected = extract_resource_access(event, raw_line=line)
                    for resource_name in sorted(detected):
                        logger.info(
                            f"[{ticket_id}] Worker accessed resource: {resource_name}"
                        )
                        resources_accessed.add(resource_name)
                except Exception as exc:
                    logger.warning(
                        f"[{ticket_id}] Failed to extract resource access: {exc}"
                    )

                if event is None:
                    diagnostics.append(
                        f"[{ticket_id}] Unparseable JSON stdout line skipped: {line[:100]}"
                    )
                    continue

                if self._on_event is not None:
                    self._on_event(event)

                if active_session_id is None and event.session_id:
                    active_session_id = event.session_id
                    _init_logging(active_session_id)

                if not event.is_known:
                    diagnostics.append(
                        f"[{ticket_id}] Unknown event type skipped: {event.type}"
                    )
                    continue

                if event.type == "error":
                    has_error_event = True

                if event.type == "step_finish" and event.token_usage is not None:
                    action = self._budget_monitor.observe(event.token_usage)
                    if self._on_budget_action is not None:
                        self._on_budget_action(action, self._budget_monitor.latest_occupancy)

                    if action == BudgetAction.WARN:
                        notice = (
                            f"[{ticket_id}] Token budget warning: occupancy reached "
                            f"{self._budget_monitor.latest_occupancy} tokens "
                            f"(warn threshold: {self._budget_monitor.warn_threshold})"
                        )
                        self._notify(notice)

                if self._kill_reason is not None:
                    termination_reason = self._kill_reason
                    break

            if termination_reason is not None:
                await self._terminate_ladder(handle)
                exit_code = await handle.wait()
            else:
                exit_code = await handle.wait()

            if termination_reason == RunTerminationReason.KILLED_INTERRUPT:
                raise KeyboardInterrupt("Worker interrupted by operator.")

        except asyncio.CancelledError:
            try:
                task = asyncio.create_task(self._terminate_ladder(handle))
                while not task.done():
                    try:
                        await asyncio.shield(task)
                    except asyncio.CancelledError:
                        await asyncio.sleep(0)
                    except BaseException:
                        break
            except BaseException:
                pass
            raise
        except Exception:
            await self._terminate_ladder(handle)
            raise
        finally:
            if hasattr(handle, "close"):
                try:
                    handle.close()
                except Exception:
                    pass
            self._current_handle = None
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass

        # Stderr sidecar logging
        if (
            active_session_id is not None
            and not log_skipped
            and stderr_target_path is not None
        ):
            self._runtime_paths.ensure_logs_dir()
            with stderr_target_path.open("a", encoding="utf-8") as sf:
                sf.write(handle.stderr)

        ready_signal_present = (
            self._runtime_paths.ready_signal_path(ticket_id).is_file()
            or (
                self._signal_repository is not None
                and self._signal_repository.read_ready(ticket_id) is not None
            )
        )

        raw_stderr = handle.stderr.strip()
        if raw_stderr:
            stderr_lines = raw_stderr.splitlines()
            stderr_tail = "\n".join(stderr_lines[-50:])
            if len(stderr_tail) > 4096:
                stderr_tail = stderr_tail[-4096:].strip()
        else:
            stderr_tail = ""

        if termination_reason is not None:
            reason = termination_reason
        elif active_session_id is None or log_skipped:
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
            has_error_event=has_error_event,
            resources_accessed=frozenset(resources_accessed),
        )

    run_session = run
