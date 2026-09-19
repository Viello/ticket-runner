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
import shutil
import sys
from typing import Any, Callable, Protocol, runtime_checkable

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.application.handoff_coordinator import SingleCycleStatus, WorkerRunResult
from runner.application.state_coordinator import StateCoordinator
from runner.domain.config import VerificationConfig
from runner.domain.exceptions import SignalFormatError, UserAbortError
from runner.domain.signal import ReadySignal
from runner.domain.ticket import Ticket
from runner.ports.command_runner import CommandRunner
from runner.ports.intervention import (
    InterventionAction,
    InterventionDecision,
    InterventionGateway,
)
from runner.ports.signal_repository import SignalRepository

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
    """

    label: str
    command: str
    exit_code: int | None
    timed_out: bool
    tail: str
    not_found: str | None = None

    @property
    def passed(self) -> bool:
        """A command passes only when it exited with code 0 and never timed out."""
        return not self.timed_out and self.exit_code == 0 and self.not_found is None


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


def _format_diagnostic(outcome: CommandOutcome, timeout_seconds: int) -> str:
    """Render one failed command block: header, status line, then the output tail."""
    if outcome.not_found is not None:
        status = f"command not found: '{outcome.not_found}'"
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
    ) -> None:
        self._command_runner = command_runner or SubprocessRunner()
        self._cwd = cwd
        self._platform = platform if platform is not None else sys.platform
        self._path_resolver = path_resolver or shutil.which

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
                BUILD_LABEL, config.build_cmd, config.timeout_seconds
            )
            results.append(build_outcome)
            if not build_outcome.passed:
                diagnostics.append(
                    _format_diagnostic(build_outcome, config.timeout_seconds)
                )
                skipped.append(config.test_cmd)
                return VerificationReport(
                    passed=False,
                    results=tuple(results),
                    diagnostics=tuple(diagnostics),
                    skipped_commands=tuple(skipped),
                )

        test_outcome = await self._execute(
            TEST_LABEL, config.test_cmd, config.timeout_seconds
        )
        results.append(test_outcome)
        if not test_outcome.passed:
            diagnostics.append(_format_diagnostic(test_outcome, config.timeout_seconds))

        return VerificationReport(
            passed=all(outcome.passed for outcome in results),
            results=tuple(results),
            diagnostics=tuple(diagnostics),
            skipped_commands=tuple(skipped),
        )

    async def _execute(
        self, label: str, command: str, timeout_seconds: int
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
        argv = build_shell_argv(command, self._platform)
        handle = await self._command_runner.spawn(argv, cwd=self._cwd)

        stdout_lines: deque[str] = deque(maxlen=TAIL_LINE_LIMIT)

        async def _consume_stdout() -> None:
            async for line in handle.stdout_lines():
                stdout_lines.append(line.rstrip("\r\n"))

        stdout_task = asyncio.ensure_future(_consume_stdout())
        wait_task = asyncio.ensure_future(handle.wait())
        exit_code: int | None = None
        timed_out = False

        _, pending = await asyncio.wait(
            {stdout_task, wait_task},
            timeout=float(timeout_seconds),
            return_when=asyncio.ALL_COMPLETED,
        )
        if pending:
            timed_out = True
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
            stdout_task.result()

        tail_source = list(stdout_lines)
        tail_source.extend(handle.stderr.splitlines()[-TAIL_LINE_LIMIT:])

        return CommandOutcome(
            label=label,
            command=command,
            exit_code=exit_code,
            timed_out=timed_out,
            tail="\n".join(tail_source[-TAIL_LINE_LIMIT:]),
        )


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
                report = await self._executor.verify(self._verification_config)
                if report.passed:
                    self._attempts += 1
                    return VerificationLoopResult.passed(
                        ready_signal=ready_signal,
                        report=report,
                        attempts=self._attempts,
                        session_id=self._active_session_id,
                        resources_accessed=frozenset(self._accumulated_resources),
                    )

                # Verification failed
                diagnostics = "\n\n".join(report.diagnostics)
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

    async def _handle_failure(self, diagnostics: str) -> InterventionAction | None:
        """Handle attempt failure, evaluating budget exhaustion and intervention menu."""
        if self._attempts >= self._max_attempts:
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
