"""Handoff coordinator application interactor for OpenCode Worker sessions (T021/T022)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
import inspect
from pathlib import Path
import time
from typing import Any

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.markdown.atomic_write import atomic_write_text
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecExcerpt, SpecMarkdownParser
from runner.application.git_operations import GitOperations
from runner.application.prompt_builder import PromptBuilder
from runner.application.worker_supervisor import (
    RunTerminationReason,
    SessionRunResult,
    WorkerSupervisor,
)
from runner.domain.config import TokenBudgetConfig, WorkerConfig
from runner.domain.runtime_paths import (
    TICKET_ID_PATTERN,
    RuntimePaths,
    is_valid_session_id,
)
from runner.domain.telemetry import BudgetAction
from runner.domain.ticket import Ticket

CLOCK_SLACK_SECONDS: float = 2.0
"""Clock slack in seconds for checkpoint freshness validation (ADR 0014).

Filesystem timestamps can round to one second depending on filesystem precision
(FAT32, ext3, NTFS). A 2-second slack window prevents false stale failures
when the handoff request and checkpoint write happen within the same second.
"""

HANDOFF_PROMPT_TEMPLATE: str = (
    "Context budget threshold reached (135k tokens). Execute the handoff skill at "
    ".agents/skills/handoff/SKILL.md. Save the handoff document directly to "
    "{checkpoint_path}. Include modified files, architectural decisions, test "
    "status, and immediate next steps. Then exit."
)

RESUME_PROMPT_TEMPLATE: str = (
    "Read the context handoff document at `{checkpoint_path}`, inspect `git status`, "
    "then continue working on ticket {ticket_id}."
)

NUDGE_PROMPT_TEMPLATE: str = (
    "You exited without writing `.agent/signals/{ticket_id}_ready.json`. "
    "Write it with your `self_review_notes`, or report the blocker, then exit."
)


class SingleCycleStatus(str, Enum):
    """Outcome status of a single worker handoff cycle."""

    READY = "READY"
    CEILING = "CEILING"
    CHECKPOINT_MISSING = "CHECKPOINT_MISSING"
    CHECKPOINT_STALE = "CHECKPOINT_STALE"
    STALLED = "STALLED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"


# Module-level aliases for direct comparison convenience
READY = SingleCycleStatus.READY
CEILING = SingleCycleStatus.CEILING
CHECKPOINT_MISSING = SingleCycleStatus.CHECKPOINT_MISSING
CHECKPOINT_STALE = SingleCycleStatus.CHECKPOINT_STALE
ESCALATED = SingleCycleStatus.ESCALATED


@dataclass(frozen=True)
class EscalationNotice:
    """Structured payload for Worker escalation events (US13/US14)."""

    ticket_id: str
    reason: str
    session_id: str | None = None
    occupancy: int = 0
    stderr_tail: str = ""
    timestamp: float = 0.0
    message: str = ""

    def __str__(self) -> str:
        """Presentation-free structured notice string."""
        sid = self.session_id if self.session_id else "none"
        return (
            f"[{self.ticket_id}] Escalation: {self.reason} "
            f"(session={sid}, occupancy={self.occupancy})"
        )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (str, SingleCycleStatus)):
            val = other.value if isinstance(other, SingleCycleStatus) else other
            return self.reason == val or str(self) == val
        return super().__eq__(other)


def default_recovery_confirmation(escalation: EscalationNotice | Any) -> bool:
    """Default interactive terminal prompt mirroring CleanSlateArchiver's confirmation.

    Safely declines (returns False) on closed stdin, EOF, OSError, or non-interactive runs.
    """
    ticket_id = getattr(escalation, "ticket_id", str(escalation))
    reason = getattr(escalation, "reason", "")
    prompt = (
        f"\n[Escalation] Worker interrupted on ticket {ticket_id} ({reason}).\n"
        f"Synthesize emergency checkpoint and resume with a fresh session? [Y/n]: "
    )
    try:
        response = input(prompt).strip().lower()
        return response in ("y", "yes", "")
    except (EOFError, KeyboardInterrupt, OSError):
        return False


@dataclass(frozen=True)
class SingleCycleResult:
    """Outcome of a single worker execution and handoff cycle."""

    status: SingleCycleStatus
    session_id: str | None = None
    resumed_session_id: str | None = None
    session_ids: tuple[str, ...] = ()
    occupancy: int = 0
    ready_signal_present: bool = False
    handoff_requested_at: float | None = None
    checkpoint_path: Path | None = None
    run_results: tuple[SessionRunResult, ...] = ()
    escalation: EscalationNotice | None = None

    # Module-level enum member convenience on class
    ESCALATED: SingleCycleStatus = SingleCycleStatus.ESCALATED
    READY: SingleCycleStatus = SingleCycleStatus.READY

    @property
    def is_ready(self) -> bool:
        """Whether the cycle ended with an accepted ready signal."""
        return self.status == SingleCycleStatus.READY

    @property
    def is_escalated(self) -> bool:
        """Whether the cycle ended in escalation."""
        return self.status == SingleCycleStatus.ESCALATED

    @property
    def handoffs(self) -> int:
        """Number of handoff instruction runs dispatched in this cycle."""
        return 1 if self.handoff_requested_at is not None else 0

    @property
    def last_run(self) -> SessionRunResult | None:
        """The most recent SessionRunResult in this cycle."""
        return self.run_results[-1] if self.run_results else None

    def __eq__(self, other: object) -> bool:
        """Allow ergonomic comparison against SingleCycleStatus enum or string value."""
        if isinstance(other, (str, SingleCycleStatus)):
            val = other.value if isinstance(other, SingleCycleStatus) else other
            if self.status == val:
                return True
            if self.escalation is not None and self.escalation.reason == val:
                return True
            return False
        return super().__eq__(other)


WorkerRunResult = SingleCycleResult


def is_checkpoint_fresh(
    checkpoint_path: Path,
    handoff_requested_at: float,
    slack: float = CLOCK_SLACK_SECONDS,
) -> bool:
    """Check if a checkpoint file exists and was authored fresh since handoff was requested.

    Follows ADR 0014:
    Acceptance requires existence and mtime >= (handoff_requested_at - slack).
    """
    if not checkpoint_path.is_file():
        return False
    try:
        mtime = checkpoint_path.stat().st_mtime
    except OSError:
        return False
    return mtime >= (handoff_requested_at - slack)


class HandoffCoordinator:
    """Coordinates OpenCode Worker execution cycles with context handoff, recovery, and escalation."""

    def __init__(
        self,
        supervisor: WorkerSupervisor | None = None,
        prompt_builder: PromptBuilder | None = None,
        runtime_paths: RuntimePaths | None = None,
        gotchas_store: GotchasStore | None = None,
        spec_parser: SpecMarkdownParser | None = None,
        worker_config: WorkerConfig | None = None,
        budget_config: TokenBudgetConfig | None = None,
        clock: Callable[[], float] = time.time,
        notify: Callable[[str | EscalationNotice], None] | None = None,
        git_operations: GitOperations | None = None,
        confirm_recovery: Callable[[EscalationNotice], bool | Awaitable[bool]] | None = None,
    ) -> None:
        self._supervisor = supervisor or WorkerSupervisor(
            runtime_paths=runtime_paths, notify=notify, budget_config=budget_config
        )
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._runtime_paths = runtime_paths or self._supervisor.runtime_paths
        self._gotchas_store = gotchas_store or GotchasStore()
        self._spec_parser = spec_parser or SpecMarkdownParser()
        self._worker_config = worker_config or WorkerConfig(
            execution_skill=".agents/skills/implement/SKILL.md"
        )
        self._budget_config = budget_config or TokenBudgetConfig()
        self._clock = clock
        self._notify = notify
        self._git_operations = git_operations or GitOperations(
            runner=getattr(self._supervisor, "command_runner", SubprocessRunner()),
            cwd=getattr(self._supervisor, "cwd", None),
        )
        self._confirm_recovery = (
            confirm_recovery
            if confirm_recovery is not None
            else default_recovery_confirmation
        )

    @property
    def runtime_paths(self) -> RuntimePaths:
        """Runtime paths value object used by this coordinator."""
        return self._runtime_paths

    @property
    def supervisor(self) -> WorkerSupervisor:
        """Worker supervisor used by this coordinator."""
        return self._supervisor

    @property
    def git_operations(self) -> GitOperations:
        """GitOperations interactor used by this coordinator."""
        return self._git_operations

    @property
    def confirm_recovery(self) -> Callable[[EscalationNotice], bool | Awaitable[bool]]:
        """Injected confirmation callable for emergency recovery escalation."""
        return self._confirm_recovery

    def build_initial_prompt(
        self,
        ticket: Ticket,
        spec_excerpt: SpecExcerpt | str | None = None,
    ) -> str:
        """Build pure initial prompt for Session A using T017 PromptBuilder."""
        resolved_excerpt: SpecExcerpt | str
        if spec_excerpt is not None:
            resolved_excerpt = spec_excerpt
        elif ticket.spec_path and Path(ticket.spec_path).is_file():
            try:
                resolved_excerpt = self._spec_parser.extract_excerpt(ticket.spec_path)
            except Exception:
                resolved_excerpt = f"Full specification reference: `{ticket.spec_path}`"
        else:
            resolved_excerpt = f"Full specification reference: `{ticket.spec_path}`"

        global_gotchas = self._gotchas_store.load()

        return self._prompt_builder.build(
            ticket=ticket,
            spec_excerpt=resolved_excerpt,
            global_gotchas=global_gotchas,
            execution_skill=self._worker_config.execution_skill,
        )

    def build_handoff_prompt(self, ticket: Ticket) -> str:
        """Build the fixed handoff instruction prompt per Spec 03."""
        checkpoint_path = self._runtime_paths.checkpoint_path(ticket.id).as_posix()
        return HANDOFF_PROMPT_TEMPLATE.format(checkpoint_path=checkpoint_path)

    def build_resume_prompt(self, ticket: Ticket, checkpoint_path: Path | str) -> str:
        """Build the resume continuation prompt for Session B per Spec 03."""
        posix_path = Path(checkpoint_path).as_posix()
        return RESUME_PROMPT_TEMPLATE.format(
            checkpoint_path=posix_path, ticket_id=ticket.id
        )

    def build_nudge_prompt(self, ticket: Ticket) -> str:
        """Build the single-nudge instruction prompt for exit 0 without ready signal."""
        return NUDGE_PROMPT_TEMPLATE.format(ticket_id=ticket.id)

    def build_crash_retry_prompt(self, ticket: Ticket, stderr_tail: str) -> str:
        """Build same-session crash retry prompt embedding trimmed stderr tail."""
        tail = stderr_tail.strip() if stderr_tail else "(empty stderr)"
        return (
            f"The previous Worker process crashed or reported an error.\n\n"
            f"Stderr tail:\n```\n{tail}\n```\n\n"
            f"Please diagnose and resolve the issue, continue implementing ticket {ticket.id}, "
            f"and write `.agent/signals/{ticket.id}_ready.json` upon completion, then exit."
        )

    def format_synthetic_checkpoint(
        self,
        ticket_id: str,
        reason: str,
        source_session_id: str | None,
        timestamp: float | str,
        porcelain_status: str,
        diff_stat: str,
    ) -> str:
        """Format emergency synthetic checkpoint markdown document (pure data, no execution)."""
        sid = source_session_id if source_session_id else "none"
        return (
            f"# Context Handoff: {ticket_id}\n\n"
            f"synthesized — no Worker handoff\n\n"
            f"- Ticket: {ticket_id}\n"
            f"- Reason: {reason}\n"
            f"- Source Session: {sid}\n"
            f"- Timestamp: {timestamp}\n\n"
            f"## Working Tree Status (`git status --porcelain`)\n\n"
            f"```\n"
            f"{porcelain_status.strip()}\n"
            f"```\n\n"
            f"## Working Tree Diff Stat (`git diff --stat`)\n\n"
            f"```\n"
            f"{diff_stat.strip()}\n"
            f"```\n"
        )

    def validate_checkpoint(
        self, ticket_id: str, handoff_requested_at: float
    ) -> SingleCycleStatus:
        """Validate existence, containment, and freshness of a checkpoint file."""
        if not isinstance(ticket_id, str) or not TICKET_ID_PATTERN.match(ticket_id):
            return SingleCycleStatus.CHECKPOINT_MISSING

        checkpoint_path = self._runtime_paths.checkpoint_path(ticket_id)

        try:
            resolved_checkpoint = checkpoint_path.resolve()
            resolved_dir = self._runtime_paths.checkpoints_dir.resolve()
            if not resolved_checkpoint.is_relative_to(resolved_dir):
                return SingleCycleStatus.CHECKPOINT_MISSING
        except (ValueError, RuntimeError):
            return SingleCycleStatus.CHECKPOINT_MISSING

        if not checkpoint_path.is_file():
            return SingleCycleStatus.CHECKPOINT_MISSING

        if not is_checkpoint_fresh(checkpoint_path, handoff_requested_at):
            return SingleCycleStatus.CHECKPOINT_STALE

        return SingleCycleStatus.READY

    async def _handle_escalation(
        self,
        ticket: Ticket,
        reason: SingleCycleStatus | str,
        source_session_id: str | None,
        current_occupancy: int,
        observed_session_ids: list[str],
        session_runs: list[SessionRunResult],
        valid_checkpoint_recorded: bool,
        last_stderr_tail: str = "",
    ) -> SingleCycleResult:
        """Route failure through the escalation notice, confirmation, and recovery synthesis flow."""
        reason_str = reason.value if isinstance(reason, SingleCycleStatus) else str(reason)
        escalation = EscalationNotice(
            ticket_id=ticket.id,
            reason=reason_str,
            session_id=source_session_id,
            occupancy=current_occupancy,
            stderr_tail=last_stderr_tail,
            timestamp=self._clock(),
            message=f"Escalation triggered for ticket {ticket.id}: {reason_str}",
        )

        # 1. Emit escalation notice through T019 notify seam
        if self._notify is not None:
            try:
                self._notify(escalation)
            except Exception:
                try:
                    self._notify(str(escalation))
                except Exception:
                    pass

        # 2. Call injectable confirm_recovery(escalation) -> bool
        if inspect.iscoroutinefunction(self._confirm_recovery):
            confirmed = await self._confirm_recovery(escalation)
        else:
            res = self._confirm_recovery(escalation)
            if asyncio.iscoroutine(res):
                confirmed = await res
            else:
                confirmed = bool(res)

        # 3. Declined or unanswered confirmation: returns ESCALATED, working tree untouched, no synthesis file
        if not confirmed:
            return SingleCycleResult(
                status=SingleCycleStatus.ESCALATED,
                session_id=source_session_id,
                session_ids=tuple(observed_session_ids),
                occupancy=current_occupancy,
                ready_signal_present=False,
                run_results=tuple(session_runs),
                escalation=escalation,
            )

        # 4. Confirmed: synthesize .agent/checkpoints/{ticket_id}/handoff.md (unless valid checkpoint exists)
        checkpoint_path = self._runtime_paths.checkpoint_path(ticket.id)

        # Security check: path traversal prevention
        try:
            resolved_checkpoint = checkpoint_path.resolve()
            resolved_dir = self._runtime_paths.checkpoints_dir.resolve()
            if not resolved_checkpoint.is_relative_to(resolved_dir):
                return SingleCycleResult(
                    status=SingleCycleStatus.ESCALATED,
                    session_id=source_session_id,
                    session_ids=tuple(observed_session_ids),
                    occupancy=current_occupancy,
                    ready_signal_present=False,
                    run_results=tuple(session_runs),
                    escalation=escalation,
                )
        except (ValueError, RuntimeError):
            return SingleCycleResult(
                status=SingleCycleStatus.ESCALATED,
                session_id=source_session_id,
                session_ids=tuple(observed_session_ids),
                occupancy=current_occupancy,
                ready_signal_present=False,
                run_results=tuple(session_runs),
                escalation=escalation,
            )

        # Gotcha: emergency synthesis must not overwrite a valid checkpoint from current cycle
        if not (valid_checkpoint_recorded and checkpoint_path.is_file()):
            try:
                porcelain_status = await self._git_operations.status_porcelain()
            except Exception as e:
                porcelain_status = f"git status error: {e}"

            try:
                diff_stat = await self._git_operations.diff_stat()
            except Exception as e:
                diff_stat = f"git diff error: {e}"

            synthetic_content = self.format_synthetic_checkpoint(
                ticket_id=ticket.id,
                reason=reason_str,
                source_session_id=source_session_id,
                timestamp=escalation.timestamp,
                porcelain_status=porcelain_status,
                diff_stat=diff_stat,
            )

            self._runtime_paths.ensure_checkpoint_dir(ticket.id)
            atomic_write_text(checkpoint_path, synthetic_content)

        # 5. Resume with a fresh session
        resume_prompt = self.build_resume_prompt(ticket, checkpoint_path)
        resumed_run = await self._supervisor.run(
            ticket=ticket,
            prompt=resume_prompt,
            session_id=None,
        )
        session_runs.append(resumed_run)
        if (
            resumed_run.session_id
            and resumed_run.session_id not in observed_session_ids
            and is_valid_session_id(resumed_run.session_id)
        ):
            observed_session_ids.append(resumed_run.session_id)

        current_occupancy = max(current_occupancy, resumed_run.occupancy)

        if (
            resumed_run.ready_signal_present
            or self._runtime_paths.ready_signal_path(ticket.id).is_file()
        ):
            return SingleCycleResult(
                status=SingleCycleStatus.READY,
                session_id=source_session_id,
                resumed_session_id=resumed_run.session_id,
                session_ids=tuple(observed_session_ids),
                occupancy=current_occupancy,
                ready_signal_present=True,
                checkpoint_path=checkpoint_path,
                run_results=tuple(session_runs),
                escalation=escalation,
            )

        return SingleCycleResult(
            status=SingleCycleStatus.ESCALATED,
            session_id=source_session_id,
            resumed_session_id=resumed_run.session_id,
            session_ids=tuple(observed_session_ids),
            occupancy=current_occupancy,
            ready_signal_present=False,
            checkpoint_path=checkpoint_path,
            run_results=tuple(session_runs),
            escalation=escalation,
        )

    async def run_cycle(
        self,
        ticket: Ticket,
        *,
        spec_excerpt: SpecExcerpt | str | None = None,
        session_id: str | None = None,
    ) -> SingleCycleResult:
        """Execute a single worker cycle with automated recovery and escalation paths.

        Args:
            ticket: Active Ticket domain entity.
            spec_excerpt: Optional pre-parsed or mock SpecExcerpt.
            session_id: Optional existing session ID when resuming an ongoing session.

        Returns:
            SingleCycleResult indicating READY or ESCALATED.
        """
        if not isinstance(ticket.id, str) or not TICKET_ID_PATTERN.match(ticket.id):
            raise ValueError(f"Invalid ticket ID format: '{ticket.id}'")

        handoff_requested_at: list[float | None] = [None]
        session_runs: list[SessionRunResult] = []
        observed_session_ids: list[str] = []
        valid_checkpoint_recorded: bool = False
        if session_id is not None and is_valid_session_id(session_id):
            observed_session_ids.append(session_id)

        active_supervisor = self._supervisor
        previous_budget_action = active_supervisor.on_budget_action

        def _handle_budget_action(action: BudgetAction, occupancy: int) -> None:
            if previous_budget_action is not None:
                try:
                    previous_budget_action(action, occupancy)
                except Exception:
                    pass

            if action == BudgetAction.CEILING:
                active_supervisor.request_kill(RunTerminationReason.KILLED_CEILING)
            elif action == BudgetAction.HANDOFF:
                handoff_requested_at[0] = self._clock()
                active_supervisor.request_kill(RunTerminationReason.KILLED_HANDOFF)

        active_supervisor.on_budget_action = _handle_budget_action

        try:
            # 1. Run Session A with initial prompt
            initial_prompt = self.build_initial_prompt(
                ticket, spec_excerpt=spec_excerpt
            )
            result_a = await active_supervisor.run(
                ticket=ticket,
                prompt=initial_prompt,
                session_id=session_id,
            )
            session_runs.append(result_a)
            if (
                result_a.session_id
                and result_a.session_id not in observed_session_ids
                and is_valid_session_id(result_a.session_id)
            ):
                observed_session_ids.append(result_a.session_id)

            current_occupancy = result_a.occupancy
            source_session_id = result_a.session_id or (
                session_id if session_id and is_valid_session_id(session_id) else None
            )

            # 2. Check for CEILING breach on Session A
            if (
                result_a.reason == RunTerminationReason.KILLED_CEILING
                or current_occupancy >= self._budget_config.ceiling
            ):
                return await self._handle_escalation(
                    ticket=ticket,
                    reason=SingleCycleStatus.CEILING,
                    source_session_id=source_session_id,
                    current_occupancy=current_occupancy,
                    observed_session_ids=observed_session_ids,
                    session_runs=session_runs,
                    valid_checkpoint_recorded=valid_checkpoint_recorded,
                    last_stderr_tail=result_a.stderr_tail,
                )

            # 3. Check for STALL on Session A
            if result_a.reason == RunTerminationReason.STALLED:
                return await self._handle_escalation(
                    ticket=ticket,
                    reason=SingleCycleStatus.STALLED,
                    source_session_id=source_session_id,
                    current_occupancy=current_occupancy,
                    observed_session_ids=observed_session_ids,
                    session_runs=session_runs,
                    valid_checkpoint_recorded=valid_checkpoint_recorded,
                    last_stderr_tail=result_a.stderr_tail,
                )

            # 4. Check for HANDOFF threshold reaction
            if result_a.reason == RunTerminationReason.KILLED_HANDOFF:
                learned_session_id = result_a.session_id
                if not learned_session_id or not is_valid_session_id(learned_session_id):
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.FAILED,
                        source_session_id=source_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                    )

                # Execute same-session handoff instruction run
                handoff_prompt = self.build_handoff_prompt(ticket)
                handoff_result = await active_supervisor.run(
                    ticket=ticket,
                    prompt=handoff_prompt,
                    session_id=learned_session_id,
                    bounded=True,
                )
                session_runs.append(handoff_result)
                current_occupancy = max(current_occupancy, handoff_result.occupancy)

                # Check if ceiling breached during handoff run
                if (
                    handoff_result.reason == RunTerminationReason.KILLED_CEILING
                    or current_occupancy >= self._budget_config.ceiling
                ):
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.CEILING,
                        source_session_id=learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=handoff_result.stderr_tail,
                    )

                # Check if stalled during handoff run
                if handoff_result.reason == RunTerminationReason.STALLED:
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.STALLED,
                        source_session_id=learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=handoff_result.stderr_tail,
                    )

                # Checkpoint validation strictly AFTER handoff process has exited
                checkpoint_path = self._runtime_paths.checkpoint_path(ticket.id)
                req_time = (
                    handoff_requested_at[0]
                    if handoff_requested_at[0] is not None
                    else self._clock()
                )

                # Validate checkpoint
                val_status = self.validate_checkpoint(ticket.id, req_time)
                if val_status == SingleCycleStatus.CHECKPOINT_MISSING:
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.CHECKPOINT_MISSING,
                        source_session_id=learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=False,
                    )
                elif val_status == SingleCycleStatus.CHECKPOINT_STALE:
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.CHECKPOINT_STALE,
                        source_session_id=learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=False,
                    )

                # Checkpoint is accepted!
                valid_checkpoint_recorded = True

                # 5. Launch Session B (fresh session without --session)
                resume_prompt = self.build_resume_prompt(ticket, checkpoint_path)
                session_b_result = await active_supervisor.run(
                    ticket=ticket,
                    prompt=resume_prompt,
                    session_id=None,
                )
                session_runs.append(session_b_result)
                if (
                    session_b_result.session_id
                    and session_b_result.session_id not in observed_session_ids
                    and is_valid_session_id(session_b_result.session_id)
                ):
                    observed_session_ids.append(session_b_result.session_id)

                current_occupancy = max(current_occupancy, session_b_result.occupancy)

                if (
                    session_b_result.reason == RunTerminationReason.KILLED_CEILING
                    or current_occupancy >= self._budget_config.ceiling
                ):
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.CEILING,
                        source_session_id=session_b_result.session_id or learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=session_b_result.stderr_tail,
                    )

                if session_b_result.reason == RunTerminationReason.STALLED:
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.STALLED,
                        source_session_id=session_b_result.session_id or learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=session_b_result.stderr_tail,
                    )

                if (
                    session_b_result.ready_signal_present
                    or self._runtime_paths.ready_signal_path(ticket.id).is_file()
                ):
                    return SingleCycleResult(
                        status=SingleCycleStatus.READY,
                        session_id=learned_session_id,
                        resumed_session_id=session_b_result.session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        ready_signal_present=True,
                        handoff_requested_at=req_time,
                        checkpoint_path=checkpoint_path,
                        run_results=tuple(session_runs),
                    )

                # Session B crashed:
                if session_b_result.is_crash:
                    if session_b_result.session_id and is_valid_session_id(session_b_result.session_id):
                        retry_prompt = self.build_crash_retry_prompt(ticket, session_b_result.stderr_tail)
                        retry_result = await active_supervisor.run(
                            ticket=ticket,
                            prompt=retry_prompt,
                            session_id=session_b_result.session_id,
                            bounded=True,
                        )
                        session_runs.append(retry_result)
                        current_occupancy = max(current_occupancy, retry_result.occupancy)
                        if retry_result.is_crash:
                            return await self._handle_escalation(
                                ticket=ticket,
                                reason="CRASH_AFTER_RETRY",
                                source_session_id=session_b_result.session_id,
                                current_occupancy=current_occupancy,
                                observed_session_ids=observed_session_ids,
                                session_runs=session_runs,
                                valid_checkpoint_recorded=valid_checkpoint_recorded,
                                last_stderr_tail=retry_result.stderr_tail,
                            )
                        if (
                            retry_result.ready_signal_present
                            or self._runtime_paths.ready_signal_path(ticket.id).is_file()
                        ):
                            return SingleCycleResult(
                                status=SingleCycleStatus.READY,
                                session_id=learned_session_id,
                                resumed_session_id=session_b_result.session_id,
                                session_ids=tuple(observed_session_ids),
                                occupancy=current_occupancy,
                                ready_signal_present=True,
                                handoff_requested_at=req_time,
                                checkpoint_path=checkpoint_path,
                                run_results=tuple(session_runs),
                            )
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.FAILED,
                        source_session_id=session_b_result.session_id or learned_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=session_b_result.stderr_tail,
                    )

                # Session B exit 0 without ready signal:
                if session_b_result.session_id and is_valid_session_id(session_b_result.session_id):
                    nudge_prompt = self.build_nudge_prompt(ticket)
                    nudge_result = await active_supervisor.run(
                        ticket=ticket,
                        prompt=nudge_prompt,
                        session_id=session_b_result.session_id,
                        bounded=True,
                    )
                    session_runs.append(nudge_result)
                    current_occupancy = max(current_occupancy, nudge_result.occupancy)
                    if (
                        nudge_result.ready_signal_present
                        or self._runtime_paths.ready_signal_path(ticket.id).is_file()
                    ):
                        return SingleCycleResult(
                            status=SingleCycleStatus.READY,
                            session_id=learned_session_id,
                            resumed_session_id=session_b_result.session_id,
                            session_ids=tuple(observed_session_ids),
                            occupancy=current_occupancy,
                            ready_signal_present=True,
                            handoff_requested_at=req_time,
                            checkpoint_path=checkpoint_path,
                            run_results=tuple(session_runs),
                        )
                return await self._handle_escalation(
                    ticket=ticket,
                    reason="NO_SIGNAL_AFTER_NUDGE",
                    source_session_id=session_b_result.session_id or learned_session_id,
                    current_occupancy=current_occupancy,
                    observed_session_ids=observed_session_ids,
                    session_runs=session_runs,
                    valid_checkpoint_recorded=valid_checkpoint_recorded,
                )

            # 6. Session A exited without handoff: check if ready signal was already written
            if (
                result_a.ready_signal_present
                or self._runtime_paths.ready_signal_path(ticket.id).is_file()
            ):
                return SingleCycleResult(
                    status=SingleCycleStatus.READY,
                    session_id=result_a.session_id,
                    session_ids=tuple(observed_session_ids),
                    occupancy=current_occupancy,
                    ready_signal_present=True,
                    run_results=tuple(session_runs),
                )

            # 7. Session A did not write ready signal. Check for CRASH vs EXIT 0:
            if result_a.is_crash:
                # Recovery Path 2: Crash (non-zero exit or stream error event)
                # Exactly one same-session resume-retry whose prompt includes the trimmed stderr tail
                if not source_session_id or not is_valid_session_id(source_session_id):
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.FAILED,
                        source_session_id=source_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=result_a.stderr_tail,
                    )

                retry_prompt = self.build_crash_retry_prompt(ticket, result_a.stderr_tail)
                retry_result = await active_supervisor.run(
                    ticket=ticket,
                    prompt=retry_prompt,
                    session_id=source_session_id,
                    bounded=True,
                )
                session_runs.append(retry_result)
                current_occupancy = max(current_occupancy, retry_result.occupancy)

                # Second crash: escalates without a third spawn
                if retry_result.is_crash:
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason="CRASH_AFTER_RETRY",
                        source_session_id=source_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=retry_result.stderr_tail,
                    )

                if (
                    retry_result.reason == RunTerminationReason.KILLED_CEILING
                    or current_occupancy >= self._budget_config.ceiling
                ):
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.CEILING,
                        source_session_id=source_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=retry_result.stderr_tail,
                    )

                if retry_result.reason == RunTerminationReason.STALLED:
                    return await self._handle_escalation(
                        ticket=ticket,
                        reason=SingleCycleStatus.STALLED,
                        source_session_id=source_session_id,
                        current_occupancy=current_occupancy,
                        observed_session_ids=observed_session_ids,
                        session_runs=session_runs,
                        valid_checkpoint_recorded=valid_checkpoint_recorded,
                        last_stderr_tail=retry_result.stderr_tail,
                    )

                if (
                    retry_result.ready_signal_present
                    or self._runtime_paths.ready_signal_path(ticket.id).is_file()
                ):
                    return SingleCycleResult(
                        status=SingleCycleStatus.READY,
                        session_id=source_session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        ready_signal_present=True,
                        run_results=tuple(session_runs),
                    )

                # Retry exited 0 without signal -> escalate
                return await self._handle_escalation(
                    ticket=ticket,
                    reason="NO_SIGNAL_AFTER_NUDGE",
                    source_session_id=source_session_id,
                    current_occupancy=current_occupancy,
                    observed_session_ids=observed_session_ids,
                    session_runs=session_runs,
                    valid_checkpoint_recorded=valid_checkpoint_recorded,
                    last_stderr_tail=retry_result.stderr_tail,
                )

            # 8. Recovery Path 1: Exit 0 without a ready signal
            # Exactly one nudge run on the same session
            if not source_session_id or not is_valid_session_id(source_session_id):
                return await self._handle_escalation(
                    ticket=ticket,
                    reason="NO_SIGNAL_AFTER_NUDGE",
                    source_session_id=source_session_id,
                    current_occupancy=current_occupancy,
                    observed_session_ids=observed_session_ids,
                    session_runs=session_runs,
                    valid_checkpoint_recorded=valid_checkpoint_recorded,
                )

            nudge_prompt = self.build_nudge_prompt(ticket)
            nudge_result = await active_supervisor.run(
                ticket=ticket,
                prompt=nudge_prompt,
                session_id=source_session_id,
                bounded=True,
            )
            session_runs.append(nudge_result)
            current_occupancy = max(current_occupancy, nudge_result.occupancy)

            if (
                nudge_result.ready_signal_present
                or self._runtime_paths.ready_signal_path(ticket.id).is_file()
            ):
                return SingleCycleResult(
                    status=SingleCycleStatus.READY,
                    session_id=source_session_id,
                    session_ids=tuple(observed_session_ids),
                    occupancy=current_occupancy,
                    ready_signal_present=True,
                    run_results=tuple(session_runs),
                )

            # A signal written during the nudge ends READY; otherwise escalate.
            return await self._handle_escalation(
                ticket=ticket,
                reason="NO_SIGNAL_AFTER_NUDGE",
                source_session_id=source_session_id,
                current_occupancy=current_occupancy,
                observed_session_ids=observed_session_ids,
                session_runs=session_runs,
                valid_checkpoint_recorded=valid_checkpoint_recorded,
                last_stderr_tail=nudge_result.stderr_tail,
            )

        finally:
            active_supervisor.on_budget_action = previous_budget_action

    run = run_cycle
