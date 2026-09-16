"""Handoff coordinator application interactor for OpenCode Worker sessions (T021)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time
from typing import Callable

from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecExcerpt, SpecMarkdownParser
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


class SingleCycleStatus(str, Enum):
    """Outcome status of a single worker handoff cycle."""

    READY = "READY"
    CEILING = "CEILING"
    CHECKPOINT_MISSING = "CHECKPOINT_MISSING"
    CHECKPOINT_STALE = "CHECKPOINT_STALE"
    STALLED = "STALLED"
    FAILED = "FAILED"


# Module-level aliases for direct comparison convenience
READY = SingleCycleStatus.READY
CEILING = SingleCycleStatus.CEILING
CHECKPOINT_MISSING = SingleCycleStatus.CHECKPOINT_MISSING
CHECKPOINT_STALE = SingleCycleStatus.CHECKPOINT_STALE


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

    @property
    def is_ready(self) -> bool:
        """Whether the cycle ended with an accepted ready signal."""
        return self.status == SingleCycleStatus.READY

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
            return self.status == other
        return super().__eq__(other)


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
    """Coordinates a single OpenCode Worker execution cycle with context handoff."""

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
        notify: Callable[[str], None] | None = None,
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

    @property
    def runtime_paths(self) -> RuntimePaths:
        """Runtime paths value object used by this coordinator."""
        return self._runtime_paths

    @property
    def supervisor(self) -> WorkerSupervisor:
        """Worker supervisor used by this coordinator."""
        return self._supervisor

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

    async def run_cycle(
        self,
        ticket: Ticket,
        *,
        spec_excerpt: SpecExcerpt | str | None = None,
        session_id: str | None = None,
    ) -> SingleCycleResult:
        """Execute a single worker cycle: Session A -> (Handoff -> Checkpoint -> Session B).

        Args:
            ticket: Active Ticket domain entity.
            spec_excerpt: Optional pre-parsed or mock SpecExcerpt.
            session_id: Optional existing session ID when resuming an ongoing session.

        Returns:
            SingleCycleResult indicating READY or failure reason (CEILING, CHECKPOINT_MISSING, CHECKPOINT_STALE).
        """
        if not isinstance(ticket.id, str) or not TICKET_ID_PATTERN.match(ticket.id):
            raise ValueError(f"Invalid ticket ID format: '{ticket.id}'")

        handoff_requested_at: list[float | None] = [None]
        session_runs: list[SessionRunResult] = []
        observed_session_ids: list[str] = []
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

            # 2. Check for CEILING breach on Session A
            if (
                result_a.reason == RunTerminationReason.KILLED_CEILING
                or current_occupancy >= self._budget_config.ceiling
            ):
                return SingleCycleResult(
                    status=SingleCycleStatus.CEILING,
                    session_id=result_a.session_id,
                    session_ids=tuple(observed_session_ids),
                    occupancy=current_occupancy,
                    ready_signal_present=result_a.ready_signal_present,
                    run_results=tuple(session_runs),
                )

            # 3. Check for HANDOFF threshold reaction
            if result_a.reason == RunTerminationReason.KILLED_HANDOFF:
                learned_session_id = result_a.session_id
                if not learned_session_id or not is_valid_session_id(learned_session_id):
                    return SingleCycleResult(
                        status=SingleCycleStatus.FAILED,
                        session_id=learned_session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        run_results=tuple(session_runs),
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
                    return SingleCycleResult(
                        status=SingleCycleStatus.CEILING,
                        session_id=learned_session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        handoff_requested_at=handoff_requested_at[0],
                        run_results=tuple(session_runs),
                    )

                # Checkpoint validation strictly AFTER handoff process has exited
                checkpoint_path = self._runtime_paths.checkpoint_path(ticket.id)
                req_time = (
                    handoff_requested_at[0]
                    if handoff_requested_at[0] is not None
                    else self._clock()
                )

                # Security check: containment in checkpoints_dir
                try:
                    if not checkpoint_path.resolve().is_relative_to(
                        self._runtime_paths.checkpoints_dir.resolve()
                    ):
                        return SingleCycleResult(
                            status=SingleCycleStatus.CHECKPOINT_MISSING,
                            session_id=learned_session_id,
                            session_ids=tuple(observed_session_ids),
                            occupancy=current_occupancy,
                            handoff_requested_at=req_time,
                            checkpoint_path=checkpoint_path,
                            run_results=tuple(session_runs),
                        )
                except (ValueError, RuntimeError):
                    return SingleCycleResult(
                        status=SingleCycleStatus.CHECKPOINT_MISSING,
                        session_id=learned_session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        handoff_requested_at=req_time,
                        checkpoint_path=checkpoint_path,
                        run_results=tuple(session_runs),
                    )

                if not checkpoint_path.is_file():
                    return SingleCycleResult(
                        status=SingleCycleStatus.CHECKPOINT_MISSING,
                        session_id=learned_session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        handoff_requested_at=req_time,
                        checkpoint_path=checkpoint_path,
                        run_results=tuple(session_runs),
                    )

                if not is_checkpoint_fresh(checkpoint_path, req_time):
                    return SingleCycleResult(
                        status=SingleCycleStatus.CHECKPOINT_STALE,
                        session_id=learned_session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        handoff_requested_at=req_time,
                        checkpoint_path=checkpoint_path,
                        run_results=tuple(session_runs),
                    )

                # 4. Checkpoint is accepted! Launch Session B (fresh session without --session)
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
                    return SingleCycleResult(
                        status=SingleCycleStatus.CEILING,
                        session_id=learned_session_id,
                        resumed_session_id=session_b_result.session_id,
                        session_ids=tuple(observed_session_ids),
                        occupancy=current_occupancy,
                        ready_signal_present=session_b_result.ready_signal_present,
                        handoff_requested_at=req_time,
                        checkpoint_path=checkpoint_path,
                        run_results=tuple(session_runs),
                    )

                if session_b_result.ready_signal_present:
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

                return SingleCycleResult(
                    status=SingleCycleStatus.FAILED
                    if session_b_result.exit_code != 0
                    else SingleCycleStatus.READY
                    if session_b_result.ready_signal_present
                    else SingleCycleStatus.FAILED,
                    session_id=learned_session_id,
                    resumed_session_id=session_b_result.session_id,
                    session_ids=tuple(observed_session_ids),
                    occupancy=current_occupancy,
                    ready_signal_present=session_b_result.ready_signal_present,
                    handoff_requested_at=req_time,
                    checkpoint_path=checkpoint_path,
                    run_results=tuple(session_runs),
                )

            # 5. Session A exited under thresholds
            if result_a.ready_signal_present:
                return SingleCycleResult(
                    status=SingleCycleStatus.READY,
                    session_id=result_a.session_id,
                    session_ids=tuple(observed_session_ids),
                    occupancy=current_occupancy,
                    ready_signal_present=True,
                    run_results=tuple(session_runs),
                )

            return SingleCycleResult(
                status=SingleCycleStatus.FAILED,
                session_id=result_a.session_id,
                session_ids=tuple(observed_session_ids),
                occupancy=current_occupancy,
                ready_signal_present=False,
                run_results=tuple(session_runs),
            )

        finally:
            active_supervisor.on_budget_action = previous_budget_action

    run = run_cycle
