"""Gatekeeper command executor running configured verification commands (T028)."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
import inspect
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Any, Callable, Protocol, runtime_checkable

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.application.handoff_coordinator import SingleCycleStatus, WorkerRunResult
from runner.application.state_coordinator import StateCoordinator
from runner.domain.config import TokenBudgetConfig, VerificationConfig
from runner.domain.exceptions import DiscordGatewayError, NonInteractiveError, SignalFormatError, UserAbortError
from runner.domain.failure_analyser import (
    FailureDiagnostic,
    analyse,
    render_diagnostic_report,
)
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal
from runner.domain.status_event import RunState, StatusEvent
from runner.domain.ticket import Ticket
from runner.ports.command_runner import CommandRunner
from runner.ports.intervention import (
    InterventionAction,
    InterventionDecision,
    InterventionGateway,
)
from runner.ports.signal_repository import SignalRepository
from runner.ports.status_publisher import StatusPublisher
from runner.ports.terminal_display import UiEventSink
from runner.application.git_operations import GitOperations

logger = logging.getLogger(__name__)

TAIL_LINE_LIMIT: int = 100
"""Number of trailing output lines retained per command and injected as diagnostics."""

TERMINATION_GRACE_SECONDS: float = 0.5
"""Bounded grace for stream draining after a timed-out command is terminated."""

BUILD_LABEL: str = "build"
TEST_LABEL: str = "test"

CMD_BUILTINS: frozenset[str] = frozenset({
    "assoc",
    "break",
    "call",
    "cd",
    "chdir",
    "cls",
    "color",
    "copy",
    "date",
    "del",
    "dir",
    "doskey",
    "echo",
    "endlocal",
    "erase",
    "exit",
    "fc",
    "find",
    "findstr",
    "for",
    "format",
    "goto",
    "graftabl",
    "help",
    "if",
    "label",
    "md",
    "mkdir",
    "mklink",
    "more",
    "move",
    "path",
    "pause",
    "popd",
    "print",
    "prompt",
    "pushd",
    "rd",
    "rem",
    "ren",
    "rename",
    "rmdir",
    "set",
    "setlocal",
    "shift",
    "sort",
    "start",
    "subst",
    "time",
    "title",
    "tree",
    "type",
    "ver",
    "verify",
    "vol",
    "where",
    "xcopy",
})
"""Known cmd.exe internal commands and control words that need no PATH resolution."""


def leading_command_token(command: str) -> str | None:
    """Return the leading whitespace-delimited token of a shell command string.

    Only the token before the first space is returned, never the full command
    string that ``build_shell_argv`` later wraps in the platform shell. Returns
    None for empty or whitespace-only commands.
    """
    stripped = command.strip()
    if not stripped:
        return None
    return stripped.split(maxsplit=1)[0]


def resolve_shell(platform: str | None = None) -> str:
    """Resolve the platform shell to a trusted executable path.

    Windows resolution prefers COMSPEC and the System32 directory over PATH
    lookups so a repository-local `cmd.exe` dropped into the supervised working
    tree can never shadow the real shell.
    """
    effective_platform = platform if platform is not None else sys.platform
    if effective_platform != "win32":
        return "/bin/sh"

    comspec = os.environ.get("COMSPEC", "")
    if comspec and Path(comspec).is_absolute() and Path(comspec).is_file():
        return comspec

    system_root = os.environ.get("SystemRoot", "")
    if system_root:
        candidate = Path(system_root) / "System32" / "cmd.exe"
        if candidate.is_file():
            return str(candidate)

    return "cmd.exe"


def build_shell_argv(command: str, platform: str | None = None) -> list[str]:
    """Wrap a shell command string into platform shell argv tokens (ADR 0016).

    Args:
        command: Trusted operator-authored shell command string from config.yaml.
        platform: Platform identifier; defaults to the host platform.

    Returns:
        argv tokens for cmd.exe /d /s /c on Windows, /bin/sh -c elsewhere.
    """
    effective_platform = platform if platform is not None else sys.platform
    shell = resolve_shell(effective_platform)
    if effective_platform == "win32":
        return [shell, "/d", "/s", "/c", command]
    return [shell, "-c", command]


def inject_test_timeout(test_cmd: str, per_test_timeout_seconds: int) -> str:
    """Inject test framework native per-test timeout flag when supported and enabled.

    Args:
        test_cmd: Configured test command string.
        per_test_timeout_seconds: Timeout in seconds per test; 0 disables injection.

    Returns:
        Command string with native timeout flag prepended to framework arguments,
        or unchanged command string if unsupported or disabled.
    """
    if (
        isinstance(per_test_timeout_seconds, bool)
        or not isinstance(per_test_timeout_seconds, int)
        or per_test_timeout_seconds <= 0
    ):
        return test_cmd

    # Cargo test, dotnet test, and unknown test runners are explicitly unflagged
    if re.search(r"\b(cargo\s+test|dotnet\s+test)\b", test_cmd, re.IGNORECASE):
        return test_cmd

    timeout_s = int(per_test_timeout_seconds)

    # 1. go test -> -timeout Ns
    if re.search(r"\bgo\s+test\b", test_cmd):
        return re.sub(
            r"(\bgo\s+test\b)",
            rf"\1 -timeout {timeout_s}s",
            test_cmd,
            count=1,
        )

    # 2. pytest -> --timeout=N
    if re.search(r"\bpytest\b", test_cmd):
        return re.sub(
            r"(\bpytest\b)",
            rf"\1 --timeout={timeout_s}",
            test_cmd,
            count=1,
        )

    # 3. jest / vitest -> --testTimeout=N000 (milliseconds)
    if re.search(r"\b(jest|vitest)\b", test_cmd):
        timeout_ms = timeout_s * 1000
        return re.sub(
            r"(\b(jest|vitest)\b)",
            rf"\1 --testTimeout={timeout_ms}",
            test_cmd,
            count=1,
        )

    return test_cmd


@dataclass(frozen=True)
class CommandOutcome:
    """Outcome of a single Gatekeeper verification command.

    Attributes:
        label: Command role, "build" or "test".
        command: The operator-authored command string that was executed.
        exit_code: Process exit code, or None when the command timed out.
        timed_out: Whether the command exceeded its timeout bound.
        tail: Last TAIL_LINE_LIMIT output lines, stdout lines followed by
            drained stderr lines. Precise stdout/stderr interleaving is not
            available on the command runner port, so ordering is normalized.
        not_found: The leading executable token that could not be resolved on
            PATH, causing the command to be rejected before spawning.
        termination_reason: Specific reason for process termination ("HANG", None).
    """

    label: str
    command: str
    exit_code: int | None
    timed_out: bool
    tail: str
    not_found: str | None = None
    termination_reason: str | None = None

    @property
    def passed(self) -> bool:
        """A command passes only when it exited with code 0 and never timed out."""
        return (
            not self.timed_out
            and self.exit_code == 0
            and self.not_found is None
            and self.termination_reason is None
        )


@dataclass(frozen=True)
class VerificationReport:
    """Consolidated Gatekeeper verification outcome for one verification cycle.

    Attributes:
        passed: True only when every executed command passed.
        results: Per-command outcomes in execution order.
        diagnostics: Injection-shaped blocks for failed and timed-out commands only.
        skipped_commands: Command strings not executed because an earlier command failed.
    """

    passed: bool
    results: tuple[CommandOutcome, ...]
    diagnostics: tuple[str, ...]
    skipped_commands: tuple[str, ...]


def _format_diagnostic(
    outcome: CommandOutcome,
    timeout_seconds: int,
    silence_window_seconds: int | None = None,
) -> str:
    """Render one failed command block: header, status line, then the output tail."""
    if outcome.not_found is not None:
        status = f"command not found: '{outcome.not_found}'"
    elif outcome.termination_reason == "HANG":
        if silence_window_seconds is not None:
            status = f"hung (silence window of {silence_window_seconds}s exceeded)"
        else:
            status = "hung (silence window exceeded)"
    elif outcome.timed_out:
        status = f"timed out after {timeout_seconds}s"
    else:
        status = f"exit code {outcome.exit_code}"
    block = [f"$ {outcome.command}", status]
    if outcome.tail:
        block.append(outcome.tail)
    return "\n".join(block)


class GatekeeperCommandExecutor:
    """Runs build_cmd then test_cmd as bounded shell subprocesses and captures diagnostics."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        cwd: Path | None = None,
        platform: str | None = None,
        path_resolver: Callable[[str], str | None] | None = None,
        ui_event_sink: UiEventSink | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._command_runner = command_runner or SubprocessRunner()
        self._cwd = cwd
        self._platform = platform if platform is not None else sys.platform
        self._path_resolver = path_resolver or shutil.which
        self._ui_event_sink = ui_event_sink
        self._clock = clock or time.monotonic

    @property
    def cwd(self) -> Path | None:
        """Configured working directory for gatekeeper execution."""
        return self._cwd

    @property
    def ui_event_sink(self) -> UiEventSink | None:
        """Configured UiEventSink for verification telemetry."""
        return self._ui_event_sink

    @ui_event_sink.setter
    def ui_event_sink(self, value: UiEventSink | None) -> None:
        self._ui_event_sink = value

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        """Execute the configured verification commands sequentially.

        An empty build_cmd is skipped silently. A failing or timed-out build_cmd
        skips test_cmd. Each command runs under its own timeout_seconds bound.
        """
        results: list[CommandOutcome] = []
        diagnostics: list[str] = []
        skipped: list[str] = []

        if config.build_cmd.strip():
            build_outcome = await self._execute(
                BUILD_LABEL,
                config.build_cmd,
                config.timeout_seconds,
                silence_window_seconds=config.silence_window_seconds,
            )
            results.append(build_outcome)
            if not build_outcome.passed:
                diagnostics.append(
                    _format_diagnostic(
                        build_outcome,
                        config.timeout_seconds,
                        silence_window_seconds=config.silence_window_seconds,
                    )
                )
                skipped.append(config.test_cmd)
                return VerificationReport(
                    passed=False,
                    results=tuple(results),
                    diagnostics=tuple(diagnostics),
                    skipped_commands=tuple(skipped),
                )

        effective_test_cmd = inject_test_timeout(
            config.test_cmd, config.per_test_timeout_seconds
        )
        test_outcome = await self._execute(
            TEST_LABEL,
            effective_test_cmd,
            config.timeout_seconds,
            silence_window_seconds=config.silence_window_seconds,
        )
        results.append(test_outcome)
        if not test_outcome.passed:
            diagnostics.append(
                _format_diagnostic(
                    test_outcome,
                    config.timeout_seconds,
                    silence_window_seconds=config.silence_window_seconds,
                )
            )

        return VerificationReport(
            passed=all(outcome.passed for outcome in results),
            results=tuple(results),
            diagnostics=tuple(diagnostics),
            skipped_commands=tuple(skipped),
        )

    async def _execute(
        self,
        label: str,
        command: str,
        timeout_seconds: int,
        silence_window_seconds: int | float | None = None,
    ) -> CommandOutcome:
        """Spawn one shell command and wait for output and exit under its timeout bound."""
        token = leading_command_token(command)
        if token is not None and token.lower() not in CMD_BUILTINS:
            if self._path_resolver(token) is None:
                return CommandOutcome(
                    label=label,
                    command=command,
                    exit_code=None,
                    timed_out=False,
                    tail="",
                    not_found=token,
                )
        if self._ui_event_sink is not None:
            try:
                self._ui_event_sink.emit("gate", f"Gatekeeper: running {command} ...")
            except Exception:
                pass

        argv = build_shell_argv(command, self._platform)
        handle = await self._command_runner.spawn(argv, cwd=self._cwd)

        stdout_lines: deque[str] = deque(maxlen=TAIL_LINE_LIMIT)
        exit_code: int | None = None
        timed_out = False
        termination_reason: str | None = None

        start_time = self._clock()
        last_activity_time = start_time
        silence_window = (
            float(silence_window_seconds)
            if silence_window_seconds is not None and silence_window_seconds > 0
            else float(timeout_seconds)
        )
        total_timeout = float(timeout_seconds)

        activity_event = asyncio.Event()

        async def _consume_stdout() -> None:
            nonlocal last_activity_time
            async for line in handle.stdout_lines():
                stdout_lines.append(line.rstrip("\r\n"))
                last_activity_time = self._clock()
                activity_event.set()

        stdout_task = asyncio.ensure_future(_consume_stdout())
        wait_task = asyncio.ensure_future(handle.wait())
        last_stderr_len = len(handle.stderr)

        while True:
            if stdout_task.done() and wait_task.done():
                break

            current_stderr_len = len(handle.stderr)
            if current_stderr_len > last_stderr_len:
                last_stderr_len = current_stderr_len
                last_activity_time = self._clock()

            if activity_event.is_set():
                activity_event.clear()
                last_activity_time = self._clock()

            now = self._clock()
            elapsed_total = now - start_time
            if elapsed_total >= total_timeout:
                timed_out = True
                break

            elapsed_silence = now - last_activity_time
            if elapsed_silence >= silence_window:
                timed_out = True
                termination_reason = "HANG"
                break

            remaining_total = max(0.001, total_timeout - elapsed_total)
            remaining_silence = max(0.001, silence_window - elapsed_silence)
            step_timeout = min(remaining_total, remaining_silence)

            event_task = asyncio.ensure_future(activity_event.wait())
            try:
                await asyncio.wait(
                    {stdout_task, wait_task, event_task},
                    timeout=step_timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            finally:
                if not event_task.done():
                    event_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await event_task

        if timed_out:
            with suppress(Exception):
                await handle.terminate()
            _, pending = await asyncio.wait(
                {stdout_task, wait_task},
                timeout=TERMINATION_GRACE_SECONDS,
                return_when=asyncio.ALL_COMPLETED,
            )

        for task in (stdout_task, wait_task):
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

        if not timed_out:
            exit_code = wait_task.result()
            with suppress(Exception):
                stdout_task.result()

        tail_source = list(stdout_lines)
        tail_source.extend(handle.stderr.splitlines()[-TAIL_LINE_LIMIT:])

        outcome = CommandOutcome(
            label=label,
            command=command,
            exit_code=exit_code,
            timed_out=timed_out,
            tail="\n".join(tail_source[-TAIL_LINE_LIMIT:]),
            termination_reason=termination_reason,
        )

        if self._ui_event_sink is not None:
            try:
                status_text = "passed" if outcome.passed else "failed"
                self._ui_event_sink.emit("gate", f"Gatekeeper: {command} {status_text}")
            except Exception:
                pass

        return outcome


MAX_DIAGNOSTIC_LINES: int = 100
"""Maximum number of diagnostic output lines embedded in resume prompts to bound context."""


def build_verification_failure_prompt(
    ticket: Ticket,
    diagnostics: str,
    hint: str | None = None,
    max_lines: int = MAX_DIAGNOSTIC_LINES,
    attempt: int = 1,
) -> str:
    """Format an actionable diagnostic resume prompt with bounded error tail and optional operator hint.

    Args:
        ticket: Active Ticket being verified.
        diagnostics: Captured diagnostic output (failed test tail, signal error, or escalation).
        hint: Optional operator guidance from the intervention menu.
        max_lines: Maximum lines of diagnostics retained (default 100).
        attempt: Verification attempt number (1-based). When >= 2, prepends diagnosing-bugs instruction.

    Returns:
        Rendered resume prompt string.
    """
    raw_lines = diagnostics.strip().splitlines()
    if len(raw_lines) > max_lines:
        bounded = "\n".join(raw_lines[-max_lines:])
    else:
        bounded = "\n".join(raw_lines)

    parts = [
        f"Gatekeeper verification failed for ticket {ticket.id}.",
        "",
        "Diagnostics:",
        "```",
        bounded,
        "```",
    ]
    if hint and hint.strip():
        parts.extend([
            "",
            f"Operator hint: {hint.strip()}",
        ])
    parts.extend([
        "",
        f"Please address the failure, verify your changes locally, and emit `.agent/signals/{ticket.id}_ready.json` when complete.",
    ])
    prompt = "\n".join(parts)

    if attempt >= 2:
        directive = (
            f"Gatekeeper verification failed (attempt {attempt}). "
            "Before making further edits, read and follow '.agents/skills/diagnosing-bugs/SKILL.md' "
            "using your file reading tool to diagnose and isolate the root cause.\n\n"
        )
        return f"{directive}{prompt}"

    return prompt


class VerificationLoopStatus(str, Enum):
    """Outcome status of a verification loop run."""

    PASSED = "passed"
    SKIPPED = "skipped"
    QUESTION_PENDING = "question_pending"
    INTERVENTION_REQUESTED = "intervention_requested"


@dataclass(frozen=True)
class VerificationLoopResult:
    """Outcome of driving Gatekeeper verification across attempt budgets."""

    status: VerificationLoopStatus
    ready_signal: ReadySignal | None = None
    verification_report: VerificationReport | None = None
    diagnostics: str | None = None
    session_id: str | None = None
    attempts: int = 0
    resources_accessed: frozenset[str] = frozenset()
    failure_diagnostic: FailureDiagnostic | None = None

    @property
    def is_passed(self) -> bool:
        """True when all Gatekeeper commands passed for a valid ready Signal."""
        return self.status == VerificationLoopStatus.PASSED

    @property
    def is_skipped(self) -> bool:
        """True when operator selected skip after budget exhaustion."""
        return self.status == VerificationLoopStatus.SKIPPED

    @property
    def is_question_pending(self) -> bool:
        """True when a Worker question interrupted verification."""
        return self.status == VerificationLoopStatus.QUESTION_PENDING

    @property
    def is_intervention_requested(self) -> bool:
        """True when operator requested intervention after failure diagnostic."""
        return self.status == VerificationLoopStatus.INTERVENTION_REQUESTED

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (str, VerificationLoopStatus)):
            val = other.value if isinstance(other, VerificationLoopStatus) else other
            return self.status.value == val
        return super().__eq__(other)

    @classmethod
    def passed(
        cls,
        ready_signal: ReadySignal,
        report: VerificationReport,
        attempts: int,
        session_id: str | None = None,
        resources_accessed: frozenset[str] = frozenset(),
    ) -> VerificationLoopResult:
        return cls(
            status=VerificationLoopStatus.PASSED,
            ready_signal=ready_signal,
            verification_report=report,
            attempts=attempts,
            session_id=session_id,
            resources_accessed=resources_accessed,
        )

    @classmethod
    def skipped(
        cls,
        diagnostics: str,
        attempts: int,
        session_id: str | None = None,
        resources_accessed: frozenset[str] = frozenset(),
    ) -> VerificationLoopResult:
        return cls(
            status=VerificationLoopStatus.SKIPPED,
            diagnostics=diagnostics,
            attempts=attempts,
            session_id=session_id,
            resources_accessed=resources_accessed,
        )

    @classmethod
    def question_pending(
        cls,
        session_id: str | None,
        attempts: int,
    ) -> VerificationLoopResult:
        return cls(
            status=VerificationLoopStatus.QUESTION_PENDING,
            session_id=session_id,
            attempts=attempts,
        )

    @classmethod
    def intervention_requested(
        cls,
        failure_diagnostic: FailureDiagnostic,
        attempts: int,
        session_id: str | None = None,
        diagnostics: str | None = None,
        resources_accessed: frozenset[str] = frozenset(),
    ) -> VerificationLoopResult:
        return cls(
            status=VerificationLoopStatus.INTERVENTION_REQUESTED,
            failure_diagnostic=failure_diagnostic,
            attempts=attempts,
            session_id=session_id,
            diagnostics=diagnostics,
            resources_accessed=resources_accessed,
        )


@runtime_checkable
class WorkerCycleRunner(Protocol):
    """Protocol for driving a single Worker execution cycle."""

    async def __call__(
        self,
        ticket: Ticket,
        *,
        session_id: str | None = None,
        prompt: str | None = None,
    ) -> WorkerRunResult:
        ...


class VerificationLoop:
    """Supervises Worker execution cycles and Gatekeeper verification against an attempt budget (T031)."""

    def __init__(
        self,
        ticket: Ticket,
        cycle_runner: WorkerCycleRunner | Callable[..., Awaitable[WorkerRunResult]],
        signal_repository: SignalRepository,
        executor: GatekeeperCommandExecutor,
        intervention_gateway: InterventionGateway,
        verification_config: VerificationConfig | None = None,
        max_attempts: int | None = None,
        initial_prompt: str | None = None,
        initial_session_id: str | None = None,
        notify: Callable[[str], None] | None = None,
        state_coordinator: StateCoordinator | None = None,
        ui_event_sink: UiEventSink | None = None,
        failure_analyser: Callable[..., FailureDiagnostic] | None = None,
        runtime_paths: RuntimePaths | None = None,
        token_budget: int | TokenBudgetConfig | None = None,
        status_publisher: StatusPublisher | None = None,
        git_operations: GitOperations | None = None,
        phase_callback: Callable[[str], Any | Awaitable[Any]] | None = None,
        event_callback: Callable[[str, str], Any | Awaitable[Any]] | None = None,
        discord_logger: Any | None = None,
        discord_thread_manager: Any | None = None,
        thread_id: str = "",
        status_card_message_id: str = "",
        presence_coordinator: Any | None = None,
    ) -> None:
        self._ticket = ticket
        self._cycle_runner = cycle_runner
        self._signal_repository = signal_repository
        self._executor = executor
        self._intervention_gateway = intervention_gateway
        self._verification_config = verification_config or VerificationConfig(test_cmd="pytest -q")
        if max_attempts is not None:
            self._max_attempts = max_attempts
        else:
            self._max_attempts = self._verification_config.max_attempts
        self._initial_prompt = initial_prompt
        self._active_session_id = initial_session_id
        self._attempts: int = 0
        self._pending_prompt: str | None = initial_prompt
        self._last_diagnostics: str = ""
        self._notify = notify
        self._accumulated_resources: set[str] = set()
        self._state_coordinator = state_coordinator
        self._ui_event_sink = ui_event_sink
        self._failure_analyser = failure_analyser or analyse
        self._runtime_paths = runtime_paths or RuntimePaths()
        self._status_publisher = status_publisher
        self._git_operations = git_operations
        self._phase_callback = phase_callback
        self._event_callback = event_callback
        self._discord_logger = discord_logger
        self._discord_thread_manager = discord_thread_manager
        self._thread_id = thread_id
        self._status_card_message_id = status_card_message_id
        self._presence_coordinator = presence_coordinator
        self._handoff_logged = False
        if isinstance(token_budget, TokenBudgetConfig):
            self._effective_token_budget = token_budget.ceiling
        elif isinstance(token_budget, int) and not isinstance(token_budget, bool):
            self._effective_token_budget = token_budget
        else:
            self._effective_token_budget = 150000
        self._last_token_count: int = 0
        if ui_event_sink is not None and getattr(self._executor, "ui_event_sink", None) is None:
            self._executor.ui_event_sink = ui_event_sink

    async def _trigger_phase(self, phase: str) -> None:
        """Trigger a phase transition notification or callback."""
        if self._phase_callback is not None:
            try:
                res = self._phase_callback(phase)
                if inspect.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.warning("phase_callback failed: %s", exc)

    async def _trigger_event(self, event_type: str, payload: str) -> None:
        """Trigger a structured event to event_callback or directly via discord_logger."""
        if self._event_callback is not None:
            try:
                res = self._event_callback(event_type, payload)
                if inspect.iscoroutine(res):
                    await res
            except Exception as exc:
                logger.warning("event_callback failed: %s", exc)
        elif self._discord_logger is not None and self._thread_id:
            presence_mode = "nearby"
            if self._presence_coordinator is not None and hasattr(self._presence_coordinator, "current_mode"):
                presence_mode = self._presence_coordinator.current_mode
            try:
                from runner.adapters.discord.logger import CRITICAL_EVENT_TYPES
                is_crit = event_type in CRITICAL_EVENT_TYPES
                await self._discord_logger.log(
                    event_type,
                    payload,
                    self._thread_id,
                    presence_mode,
                    severity="critical" if is_crit else None,
                )
            except DiscordGatewayError as exc:
                logger.warning("Failed to emit Discord event %s: %s", event_type, exc)
            except Exception as exc:
                logger.warning("Failed to emit Discord event %s: %s", event_type, exc)

    def _publish_status(
        self,
        event_name: str,
        run_state: RunState,
        attempt: int | None = None,
        last_step_summary: str | None = None,
    ) -> None:
        """Publish a status event if a status publisher is configured."""
        if self._status_publisher is None:
            return
        from datetime import datetime, timezone

        event = StatusEvent(
            ticket_id=self._ticket.id,
            run_state=run_state,
            attempt=attempt if attempt is not None else self._attempts,
            max_attempts=self._max_attempts,
            token_count=self._last_token_count,
            token_budget=self._effective_token_budget,
            last_step_summary=last_step_summary,
            last_step_at=datetime.now(timezone.utc).isoformat(),
            last_event=event_name,
        )
        try:
            self._status_publisher.publish(event)
        except Exception as exc:
            logger.warning("Failed to publish status event %s: %s", event_name, exc)

    @property
    def ui_event_sink(self) -> UiEventSink | None:
        """UiEventSink telemetry sink."""
        return self._ui_event_sink

    @ui_event_sink.setter
    def ui_event_sink(self, value: UiEventSink | None) -> None:
        self._ui_event_sink = value
        if hasattr(self._executor, "ui_event_sink"):
            self._executor.ui_event_sink = value

    @property
    def state_coordinator(self) -> StateCoordinator | None:
        """State coordinator used to persist verification transitions."""
        return self._state_coordinator

    @state_coordinator.setter
    def state_coordinator(self, value: StateCoordinator | None) -> None:
        self._state_coordinator = value

    @property
    def accumulated_resources(self) -> frozenset[str]:
        """Resources accessed across all worker execution cycles."""
        return frozenset(self._accumulated_resources)

    def _check_ready_warnings(self) -> list[str]:
        """Emit soft warnings if required review skills or AGENTS.md were not accessed."""
        warnings: list[str] = []
        if "code-review" not in self._accumulated_resources:
            warnings.append(
                f"[{self._ticket.id}] Warning: Ready signal emitted without reading '.agents/skills/code-review/SKILL.md'. Proceeding to verification."
            )
        if "AGENTS.md" not in self._accumulated_resources:
            warnings.append(
                f"[{self._ticket.id}] Warning: Ready signal emitted without reading 'AGENTS.md'. Proceeding to verification."
            )
        if self._ticket.security_required and "security-review" not in self._accumulated_resources:
            warnings.append(
                f"[{self._ticket.id}] Warning: Ready signal emitted without reading required '.agents/skills/security-review/SKILL.md'. Proceeding to verification."
            )

        for warning in warnings:
            logger.warning(warning)
            if self._notify is not None:
                try:
                    self._notify(warning)
                except Exception:
                    pass

        return warnings

    @property
    def ticket(self) -> Ticket:
        """Active Ticket being verified."""
        return self._ticket

    @property
    def attempts(self) -> int:
        """Current count of consumed verification attempts."""
        return self._attempts

    @property
    def max_attempts(self) -> int:
        """Verification attempts ceiling before tripping the circuit breaker."""
        return self._max_attempts

    @property
    def active_session_id(self) -> str | None:
        """Active Worker session identifier."""
        return self._active_session_id

    @property
    def last_diagnostics(self) -> str:
        """Last captured failure diagnostics."""
        return self._last_diagnostics

    def _clean_question(self, ticket_id: str) -> None:
        """Clean any stale or malformed question signal for the ticket."""
        if hasattr(self._signal_repository, "clean_question"):
            self._signal_repository.clean_question(ticket_id)

    def _append_smoke_log(
        self,
        ready_signal: ReadySignal,
        ticket: Ticket,
        runtime_paths: RuntimePaths | None = None,
    ) -> None:
        """Append smoke scenario entries to the per-spec-slug smoke log file.

        The log lives at ``.agent/smoke_log_{spec_slug}.md`` and is append-only.
        Each passing verification cycle contributes a dated section. The human
        reviews the log after all tickets for a spec are complete.

        Args:
            ready_signal: The passing ready signal carrying manual_verification entries.
            ticket: The active ticket.
            runtime_paths: RuntimePaths instance; defaults to self._runtime_paths.
        """
        from datetime import datetime, timezone

        paths = runtime_paths or self._runtime_paths
        spec_slug = ready_signal.scope if ready_signal.scope else ticket.id
        log_path = paths.smoke_log_path(spec_slug)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        lines: list[str] = []
        lines.append(f"## {ticket.id} — {ticket.title}")
        lines.append(f"_Appended: {timestamp}_")
        lines.append("")

        for scenario in ready_signal.manual_verification:
            name = scenario.get("name", "")
            setup = scenario.get("setup", "")
            steps = scenario.get("steps", "")
            expected = scenario.get("expected", "")
            auto_covered = bool(scenario.get("auto_covered", False))
            update_notes = scenario.get("update_notes", "")

            auto_tag = " [also auto-covered]" if auto_covered else ""
            lines.append(f"### {name}{auto_tag}")
            lines.append("")
            if setup:
                lines.append(f"**Setup**: {setup}")
            if steps:
                lines.append(f"**Steps**: {steps}")
            if expected:
                lines.append(f"**Expected**: {expected}")
            if update_notes:
                lines.append("")
                lines.append(f"> {update_notes}")
            lines.append("")

        lines.append("---")
        lines.append("")

        block = "\n".join(lines)

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            if not log_path.exists():
                header = f"# Smoke Log — {spec_slug}\n\n"
                atomic_write_text(log_path, header + block)
            else:
                existing = log_path.read_text(encoding="utf-8")
                atomic_write_text(log_path, existing + block)
        except Exception as exc:
            logger.warning("Failed to append smoke log %s: %s", log_path, exc)

    async def run(
        self,
        *,
        prompt: str | None = None,
    ) -> VerificationLoopResult:
        """Drive the verification loop until acceptance, skip, or question interruption.

        Args:
            prompt: Optional prompt override (e.g. for question answer resume).

        Returns:
            VerificationLoopResult indicating PASSED, SKIPPED, or QUESTION_PENDING.

        Raises:
            UserAbortError: When the operator selects abort from the intervention menu.
        """
        if prompt is not None:
            self._pending_prompt = prompt

        while True:
            current_prompt = self._pending_prompt
            current_session = self._active_session_id

            await self._trigger_phase("Working")

            # 1. Execute worker cycle run
            kwargs: dict[str, Any] = {}
            try:
                sig = inspect.signature(self._cycle_runner)
                params = sig.parameters
                has_var = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                if "session_id" in params or has_var:
                    kwargs["session_id"] = current_session
                if "prompt" in params or has_var:
                    kwargs["prompt"] = current_prompt
            except (ValueError, TypeError):
                kwargs = {"session_id": current_session, "prompt": current_prompt}

            run_result = await self._cycle_runner(self._ticket, **kwargs)

            if run_result.session_id:
                self._active_session_id = run_result.session_id

            # Accumulate resources accessed during this cycle
            if hasattr(run_result, "resources_accessed") and run_result.resources_accessed:
                self._accumulated_resources.update(run_result.resources_accessed)
            elif hasattr(run_result, "skills_accessed") and run_result.skills_accessed:
                self._accumulated_resources.update(run_result.skills_accessed)
            if hasattr(run_result, "run_results"):
                for sr in getattr(run_result, "run_results", ()):
                    if hasattr(sr, "resources_accessed"):
                        self._accumulated_resources.update(sr.resources_accessed)

            if hasattr(run_result, "occupancy") and run_result.occupancy:
                self._last_token_count = run_result.occupancy

            occupancy = getattr(run_result, "occupancy", 0) or 0
            ceiling = getattr(self._effective_token_budget, "ceiling", self._effective_token_budget)
            handoff_thresh = getattr(self._effective_token_budget, "handoff", 135000)
            if not isinstance(handoff_thresh, int):
                handoff_thresh = 135000
            if not isinstance(ceiling, int):
                ceiling = 150000

            if run_result.status == SingleCycleStatus.CEILING or (occupancy and occupancy >= ceiling):
                await self._trigger_event(
                    "hard_ceiling",
                    f"Hard ceiling reached ({occupancy} tokens >= {ceiling}) for ticket '{self._ticket.id}'.",
                )
            elif (getattr(run_result, "handoffs", 0) > 0) or (occupancy and occupancy >= handoff_thresh):
                if not self._handoff_logged or getattr(run_result, "handoffs", 0) > 0:
                    self._handoff_logged = True
                    await self._trigger_event(
                        "handoff",
                        f"Context handoff triggered ({occupancy} tokens >= {handoff_thresh}) for ticket '{self._ticket.id}'.",
                    )

            # Reset pending prompt since it has been consumed
            self._pending_prompt = None

            # Precedence check: if a valid ready Signal exists, it wins over any stale question
            ready_signal: ReadySignal | None = None
            ready_format_error: SignalFormatError | None = None
            try:
                ready_signal = self._signal_repository.read_ready(self._ticket.id)
            except SignalFormatError as exc:
                ready_format_error = exc

            if ready_signal is not None:
                await self._trigger_phase("Reviewing")
                if self._discord_thread_manager is not None and self._thread_id:
                    try:
                        await self._discord_thread_manager.finish_live_digest(self._thread_id)
                    except Exception as exc:
                        logger.warning("Failed to finish live digest: %s", exc)
                elif self._discord_logger is not None and self._thread_id:
                    try:
                        await self._discord_logger.finish_live_digest(self._thread_id)
                    except Exception as exc:
                        logger.warning("Failed to finish live digest: %s", exc)
                # Valid ready signal wins: clean stale question so it cannot re-trigger
                self._clean_question(self._ticket.id)
                self._signal_repository.consume_ready(self._ticket.id)

                # Check soft warnings before proceeding to verification
                self._check_ready_warnings()

                if self._state_coordinator is not None:
                    self._state_coordinator.transition_to_gatekeeper(
                        verification_attempts=self._attempts
                    )

                # Execute Gatekeeper independent verification commands
                self._publish_status(
                    event_name="ATTEMPT_STARTED",
                    run_state=RunState.VERIFYING,
                    attempt=self._attempts + 1,
                )
                await self._trigger_phase("Verifying")
                report = await self._executor.verify(self._verification_config)
                if report.passed:
                    self._attempts += 1
                    self._publish_status(
                        event_name="ATTEMPT_ENDED",
                        run_state=RunState.DONE,
                        attempt=self._attempts,
                        last_step_summary="Verification passed",
                    )

                    # --- Manual verification handling ---
                    if ready_signal.manual_verification_is_default:
                        # manual_verification was absent from the payload => backward-compatible, do not emit
                        pass
                    elif not ready_signal.manual_verification:
                        # manual_verification present but empty => ticket defined no smoke scenarios
                        logger.warning(
                            "[%s] manual_verification is empty — ticket must define at least one smoke scenario.",
                            self._ticket.id,
                        )
                    else:
                        def _scenario_label(s: dict) -> str:
                            tag = " [also auto-covered]" if s.get("auto_covered") else ""
                            return f"{s.get('name', '')}{tag}"

                        # 1. Commit body injection if GitOperations is available
                        if self._git_operations is not None:
                            changes = [f"Update {p}" for p in ready_signal.modified_files] + [
                                "Manual verification required:",
                                *(f"- {_scenario_label(s)}" for s in ready_signal.manual_verification),
                            ]
                            try:
                                commit_res = self._git_operations.commit_ticket(
                                    scope=ready_signal.scope or "adapters",
                                    title=self._ticket.title,
                                    changes=changes,
                                )
                                if inspect.iscoroutine(commit_res):
                                    await commit_res
                            except Exception as exc:
                                logger.warning("GitOperations commit_ticket failed: %s", exc)
                        else:
                            logger.warning(
                                "GitOperations not provided to VerificationLoop; skipping commit-body injection"
                            )

                        # 2. Emit full human-action checklist to terminal
                        scenario_lines: list[str] = []
                        for scenario in ready_signal.manual_verification:
                            name = scenario.get("name", "")
                            setup = scenario.get("setup", "")
                            steps = scenario.get("steps", "")
                            expected = scenario.get("expected", "")
                            auto_covered = bool(scenario.get("auto_covered", False))
                            auto_tag = " [also auto-covered]" if auto_covered else ""
                            scenario_lines.append(f"Scenario: {name}{auto_tag}")
                            if setup:
                                scenario_lines.append(f"Setup: {setup}")
                            if steps:
                                scenario_lines.append(f"Steps: {steps}")
                            if expected:
                                scenario_lines.append(f"Expected: {expected}")
                        scenario_text = "\n".join(scenario_lines)
                        if self._notify is not None:
                            try:
                                self._notify(scenario_text)
                            except Exception:
                                print(scenario_text)
                        else:
                            print(scenario_text)

                        # 3. Append to per-spec-slug smoke log (durable record)
                        self._append_smoke_log(ready_signal, self._ticket)

                    return VerificationLoopResult.passed(
                        ready_signal=ready_signal,
                        report=report,
                        attempts=self._attempts,
                        session_id=self._active_session_id,
                        resources_accessed=frozenset(self._accumulated_resources),
                    )

                # Verification failed
                self._publish_status(
                    event_name="ATTEMPT_ENDED",
                    run_state=RunState.RUNNING,
                    attempt=self._attempts + 1,
                    last_step_summary="Verification failed",
                )
                diagnostics = "\n\n".join(report.diagnostics)
                await self._trigger_event("verification_failed", diagnostics)
                failed_outcome = next((r for r in report.results if not r.passed), None)
                escalation_result = await self._check_escalation(
                    diagnostics=diagnostics, outcome=failed_outcome
                )
                if escalation_result is not None:
                    return escalation_result

                self._attempts += 1
                self._last_diagnostics = diagnostics
                action = await self._handle_failure(diagnostics)
                if action == InterventionAction.SKIP:
                    return VerificationLoopResult.skipped(
                        diagnostics=self._last_diagnostics,
                        attempts=self._attempts,
                        session_id=self._active_session_id,
                        resources_accessed=frozenset(self._accumulated_resources),
                    )
                continue

            # 2. Check for question interruption or malformed question
            is_question = (
                run_result.status == SingleCycleStatus.QUESTION_PENDING
                or run_result.is_question_pending
            )

            pending_question = None
            try:
                pending_question = self._signal_repository.read_pending_question(self._ticket.id)
            except SignalFormatError as exc:
                # A malformed pending question is a failed Verification Attempt with the parse error as diagnostics
                self._clean_question(self._ticket.id)
                diagnostics = str(exc)
                escalation_result = await self._check_escalation(diagnostics=diagnostics)
                if escalation_result is not None:
                    return escalation_result
                self._attempts += 1
                self._last_diagnostics = diagnostics
                action = await self._handle_failure(diagnostics)
                if action == InterventionAction.SKIP:
                    return VerificationLoopResult.skipped(
                        diagnostics=self._last_diagnostics,
                        attempts=self._attempts,
                        session_id=self._active_session_id,
                    )
                continue

            if pending_question is not None or is_question:
                # Valid pending question interrupts verification: 0 budget consumed
                return VerificationLoopResult.question_pending(
                    session_id=self._active_session_id,
                    attempts=self._attempts,
                )

            # 3. Check for worker-phase non-READY failure
            if run_result.status != SingleCycleStatus.READY:
                diagnostics = (
                    run_result.escalation_details
                    or (run_result.escalation.reason if run_result.escalation else run_result.status.value)
                )
                self._signal_repository.consume_ready(self._ticket.id)
                escalation_result = await self._check_escalation(diagnostics=diagnostics)
                if escalation_result is not None:
                    return escalation_result
                self._attempts += 1
                self._last_diagnostics = diagnostics
                action = await self._handle_failure(diagnostics)
                if action == InterventionAction.SKIP:
                    return VerificationLoopResult.skipped(
                        diagnostics=self._last_diagnostics,
                        attempts=self._attempts,
                        session_id=self._active_session_id,
                    )
                continue

            # 4. Ready signal validation
            if ready_format_error is not None:
                self._signal_repository.consume_ready(self._ticket.id)
                diagnostics = str(ready_format_error)
                escalation_result = await self._check_escalation(diagnostics=diagnostics)
                if escalation_result is not None:
                    return escalation_result
                self._attempts += 1
                self._last_diagnostics = diagnostics
                action = await self._handle_failure(diagnostics)
                if action == InterventionAction.SKIP:
                    return VerificationLoopResult.skipped(
                        diagnostics=self._last_diagnostics,
                        attempts=self._attempts,
                        session_id=self._active_session_id,
                    )
                continue

            diagnostics = (
                f"Ready signal file for ticket '{self._ticket.id}' was missing on disk."
            )
            escalation_result = await self._check_escalation(diagnostics=diagnostics)
            if escalation_result is not None:
                return escalation_result
            self._attempts += 1
            self._last_diagnostics = diagnostics
            action = await self._handle_failure(diagnostics)
            if action == InterventionAction.SKIP:
                return VerificationLoopResult.skipped(
                    diagnostics=self._last_diagnostics,
                    attempts=self._attempts,
                    session_id=self._active_session_id,
                )
            continue

    async def _check_escalation(
        self,
        diagnostics: str,
        outcome: CommandOutcome | None = None,
    ) -> VerificationLoopResult | None:
        """Check escalation policy and prompt operator if threshold met (T066)."""
        current_attempt = self._attempts + 1
        policy = self._verification_config.bug_escalation_at

        should_escalate = False
        if policy == 0:
            should_escalate = False
        elif policy == -1:
            should_escalate = current_attempt >= self._max_attempts
        elif policy >= 1:
            should_escalate = (
                current_attempt >= policy
                or current_attempt >= self._max_attempts
            )

        if not should_escalate:
            return None

        output_lines = outcome.tail if outcome and outcome.tail else diagnostics
        exit_code = outcome.exit_code if outcome else 1
        termination_reason = outcome.termination_reason if outcome else None

        diagnostic = self._failure_analyser(
            output_lines=output_lines,
            exit_code=exit_code,
            termination_reason=termination_reason,
            config=self._verification_config,
        )

        report_text = render_diagnostic_report(
            diagnostic=diagnostic,
            token_count=self._last_token_count,
            token_budget=self._effective_token_budget,
            prompt_question=True,
        )

        self._publish_status(
            event_name="ESCALATION_EMITTED",
            run_state=RunState.ESCALATING,
            attempt=current_attempt,
            last_step_summary=f"Escalation emitted: {diagnostic.label}",
        )

        # Terminal prompt via InterventionGateway
        if self._state_coordinator is not None:
            self._state_coordinator.transition_to_waiting_for_user()

        answered_yes = False
        try:
            decision = self._intervention_gateway.prompt_escalation(
                ticket=self._ticket,
                report=report_text,
            )
            if inspect.iscoroutine(decision):
                decision = await decision
            answered_yes = bool(decision)
        except (NonInteractiveError, EOFError, OSError):
            answered_yes = False

        if answered_yes:
            return VerificationLoopResult.intervention_requested(
                failure_diagnostic=diagnostic,
                attempts=self._attempts,
                session_id=self._active_session_id,
                diagnostics=diagnostics,
                resources_accessed=frozenset(self._accumulated_resources),
            )

        # Operator declined or non-interactive: log diagnostic to .agent/logs/<ticket_id>_diagnostic.md
        try:
            diag_path = self._runtime_paths.diagnostic_log_path(self._ticket.id)
            diag_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(diag_path, report_text)
        except Exception as exc:
            logger.warning("Failed to write diagnostic log: %s", exc)

        return None


    async def _handle_failure(self, diagnostics: str) -> InterventionAction | None:
        """Handle attempt failure, evaluating budget exhaustion and intervention menu."""
        if self._attempts >= self._max_attempts:
            self._publish_status(
                event_name="CIRCUIT_BREAKER_TRIPPED",
                run_state=RunState.IDLE,
                attempt=self._attempts,
                last_step_summary="Circuit breaker tripped",
            )
            await self._trigger_event(
                "circuit_breaker_trip",
                f"Circuit breaker tripped for ticket '{self._ticket.id}' after {self._attempts} attempts.\n{diagnostics}",
            )
            if self._state_coordinator is not None:
                self._state_coordinator.transition_to_waiting_for_user()
            decision = self._intervention_gateway.request_intervention(
                ticket=self._ticket,
                diagnostics=diagnostics,
                attempt=self._attempts,
            )
            if inspect.iscoroutine(decision):
                decision = await decision

            if decision.action == InterventionAction.ABORT:
                if self._state_coordinator is not None:
                    self._state_coordinator.transition_to_circuit_breaker_tripped()
                raise UserAbortError(
                    f"Execution aborted by operator for ticket '{self._ticket.id}'."
                )

            if decision.action == InterventionAction.RETRY:
                # Reset attempt counter to full fresh budget
                self._attempts = 0
                if self._state_coordinator is not None:
                    self._state_coordinator.transition_to_working(
                        ticket_id=self._ticket.id,
                        session_id=self._active_session_id,
                        verification_attempts=0,
                    )
                self._pending_prompt = build_verification_failure_prompt(
                    ticket=self._ticket,
                    diagnostics=diagnostics,
                    hint=decision.hint,
                )
                return InterventionAction.RETRY

            if decision.action == InterventionAction.SKIP:
                return InterventionAction.SKIP

            raise ValueError(f"Unsupported intervention action: {decision.action}")

        # Budget not yet exhausted: prepare resume prompt with diagnostics for next attempt
        self._pending_prompt = build_verification_failure_prompt(
            ticket=self._ticket,
            diagnostics=diagnostics,
            hint=None,
            attempt=self._attempts,
        )
        return None


GatekeeperVerificationLoop = VerificationLoop
