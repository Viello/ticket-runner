"""Queue orchestrator coordinating lock lifecycle, processor seam, and atomic commits."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
import time
from typing import Any, Protocol, runtime_checkable

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.markdown.file_lock import DEFAULT_LOCK_PATH, QueueFileLock
from runner.adapters.markdown.gotchas_store import DEFAULT_GOTCHAS_PATH, GotchasStore
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.clean_slate import CleanSlateArchiver
from runner.application.git_operations import GitOperations
from runner.application.state_coordinator import StateCoordinator
from runner.domain.config import LifecycleConfig, RunnerConfig
from runner.domain.exceptions import UserAbortError
from runner.domain.state import StateStatus
from runner.domain.ticket import Ticket
from runner.ports.terminal_display import UiEventSink
from runner.ports.ticket_repository import TicketRepository

DEFAULT_TICKETS_DIR = Path("docs/tickets")
STANDBY_BANNER = (
    "[Queue] All tickets processed. Standing by watching docs/tickets/ for new tickets "
    "(standby, Ctrl+C to exit)."
)


class TicketOutcomeStatus(str, Enum):
    """Result status of a processed ticket."""

    APPROVED = "approved"
    SKIPPED = "skipped"
    ABORTED = "aborted"
    INTERVENTION_REQUESTED = "intervention_requested"


@dataclass(frozen=True)
class TicketOutcome:
    """Outcome emitted after a Ticket is processed through the worker/gatekeeper seam."""

    status: TicketOutcomeStatus
    new_gotchas: Sequence[str] = ()
    changes: Sequence[str] = ()
    scope: str | None = None
    commit_prefix: str | None = None
    details: str | Mapping[str, Any] | None = None
    commit_sha: str | None = None
    tokens_consumed: int = 0

    def __post_init__(self) -> None:
        if isinstance(self.status, str) and not isinstance(self.status, TicketOutcomeStatus):
            object.__setattr__(self, "status", TicketOutcomeStatus(self.status))

    @property
    def is_approved(self) -> bool:
        """Return True if ticket was approved by Gatekeeper."""
        return self.status == TicketOutcomeStatus.APPROVED

    @property
    def is_skipped(self) -> bool:
        """Return True if ticket was skipped."""
        return self.status == TicketOutcomeStatus.SKIPPED

    @property
    def is_aborted(self) -> bool:
        """Return True if ticket execution was aborted by operator."""
        return self.status == TicketOutcomeStatus.ABORTED

    @property
    def is_intervention_requested(self) -> bool:
        """Return True if operator intervention was requested."""
        return self.status == TicketOutcomeStatus.INTERVENTION_REQUESTED

    @classmethod
    def intervention_requested(
        cls,
        diagnostic: Any = None,
        details: str | None = None,
    ) -> TicketOutcome:
        """Construct an INTERVENTION_REQUESTED outcome."""
        return cls(
            status=TicketOutcomeStatus.INTERVENTION_REQUESTED,
            details=details if details is not None else (str(diagnostic) if diagnostic is not None else None),
        )


    def with_commit_sha(self, commit_sha: str) -> TicketOutcome:
        """Return a clone of this outcome with commit SHA populated."""
        return replace(self, commit_sha=commit_sha)

    @classmethod
    def approved(
        cls,
        new_gotchas: Sequence[str] = (),
        changes: Sequence[str] = (),
        scope: str | None = None,
        commit_prefix: str | None = None,
        commit_sha: str | None = None,
        tokens_consumed: int = 0,
    ) -> TicketOutcome:
        """Construct an approved ticket outcome."""
        return cls(
            status=TicketOutcomeStatus.APPROVED,
            new_gotchas=tuple(new_gotchas),
            changes=tuple(changes),
            scope=scope,
            commit_prefix=commit_prefix,
            commit_sha=commit_sha,
            tokens_consumed=tokens_consumed,
        )

    @classmethod
    def skipped(
        cls,
        details: str | Mapping[str, Any] | None = None,
        tokens_consumed: int = 0,
    ) -> TicketOutcome:
        """Construct a skipped ticket outcome with failure details."""
        return cls(
            status=TicketOutcomeStatus.SKIPPED,
            details=details,
            tokens_consumed=tokens_consumed,
        )

    @classmethod
    def aborted(
        cls,
        details: str | Mapping[str, Any] | None = None,
        tokens_consumed: int = 0,
    ) -> TicketOutcome:
        """Construct an aborted ticket outcome with failure details."""
        return cls(
            status=TicketOutcomeStatus.ABORTED,
            details=details,
            tokens_consumed=tokens_consumed,
        )


def format_celebration_banner(tickets_committed: int, total_tokens: int) -> str:
    """Format the verbatim Spec 06 double-bordered celebration banner.

    Args:
        tickets_committed: Count of tickets committed in the lifecycle run ({n}).
        total_tokens: Total tokens accumulated across sessions, rounded to nearest thousand ({k}).

    Returns:
        Exact 4-line boxed banner formatted in double-line border characters.
    """
    k = (total_tokens + 500) // 1000 if total_tokens >= 0 else 0
    middle = f"  {tickets_committed} tickets  ·  0 failed  ·  ~{k}k tokens"
    pad = " " * max(0, 50 - len(middle))
    return (
        "╔══════════════════════════════════════════════════╗\n"
        "║  🎉  Queue complete! All tickets committed.      ║\n"
        f"║{middle}{pad}║\n"
        "╚══════════════════════════════════════════════════╝"
    )


@runtime_checkable
class TicketProcessor(Protocol):
    """Protocol for processing a single ticket (injected worker/gatekeeper seam)."""

    async def __call__(self, ticket: Ticket) -> TicketOutcome:
        """Execute and verify a single ticket, returning its outcome."""
        ...


class QueueOrchestrator:
    """Orchestrates sequential ticket queue execution with lock and commit lifecycle."""

    def __init__(
        self,
        ticket_store: TicketRepository | None = None,
        lock: QueueFileLock | None = None,
        gotchas_store: GotchasStore | None = None,
        git_operations: GitOperations | None = None,
        processor: TicketProcessor | Callable[[Ticket], Awaitable[TicketOutcome]] | None = None,
        tickets_dir: Path | str | None = None,
        lock_path: Path | str | None = None,
        gotchas_path: Path | str | None = None,
        commit_scope: str = "queue",
        spec_slug: str | None = None,
        cwd: Path | None = None,
        clean_slate_archiver: CleanSlateArchiver | None = None,
        clock: Callable[[], float] | None = None,
        state_coordinator: StateCoordinator | None = None,
        ui_event_sink: UiEventSink | None = None,
        discord_thread_manager: Any | None = None,
        discord_logger: Any | None = None,
        presence_coordinator: Any | None = None,
        runner_config: Any | None = None,
    ) -> None:
        self._cwd = cwd
        self._clock: Callable[[], float] = clock or time.monotonic
        self._lifecycle_outcomes: list[TicketOutcome] = []
        self._lifecycle_start_time: float | None = None
        self._summary_printed: bool = False
        self._state_coordinator = state_coordinator
        self._ui_event_sink = ui_event_sink
        self._discord_thread_manager = discord_thread_manager
        self._discord_logger = discord_logger
        self._presence_coordinator = presence_coordinator
        self._runner_config = runner_config
        if tickets_dir is not None:
            self._tickets_dir = Path(tickets_dir)
        elif self._cwd:
            self._tickets_dir = self._cwd / DEFAULT_TICKETS_DIR
        else:
            self._tickets_dir = DEFAULT_TICKETS_DIR

        self._ticket_store = ticket_store or DirectoryTicketStore(root_dir=self._tickets_dir)

        if lock_path is not None:
            self._lock_path = Path(lock_path)
        elif self._cwd:
            self._lock_path = self._cwd / DEFAULT_LOCK_PATH
        else:
            self._lock_path = DEFAULT_LOCK_PATH

        self._lock = lock or QueueFileLock(lock_path=self._lock_path)

        if gotchas_path is not None:
            self._gotchas_path = Path(gotchas_path)
        elif self._cwd:
            self._gotchas_path = self._cwd / DEFAULT_GOTCHAS_PATH
        else:
            self._gotchas_path = DEFAULT_GOTCHAS_PATH

        self._gotchas_store = gotchas_store or GotchasStore(path=self._gotchas_path)

        if git_operations is not None:
            self._git_operations = git_operations
        else:
            self._git_operations = GitOperations(runner=SubprocessRunner(), cwd=self._cwd)

        self._processor = processor
        if self._processor is not None:
            if hasattr(self._processor, "discord_thread_manager") and getattr(self._processor, "discord_thread_manager", None) is None:
                self._processor.discord_thread_manager = discord_thread_manager
            if hasattr(self._processor, "discord_logger") and getattr(self._processor, "discord_logger", None) is None:
                self._processor.discord_logger = discord_logger
            if hasattr(self._processor, "presence_coordinator") and getattr(self._processor, "presence_coordinator", None) is None:
                self._processor.presence_coordinator = presence_coordinator
            if hasattr(self._processor, "runner_config") and getattr(self._processor, "runner_config", None) is None:
                self._processor.runner_config = runner_config

        self._commit_scope = commit_scope
        self._spec_slug = spec_slug
        self._is_paused: bool = False
        self._clean_slate_archiver = clean_slate_archiver or CleanSlateArchiver(
            git_operations=self._git_operations,
            gotchas_store=self._gotchas_store,
            tickets_dir=self._tickets_dir,
            cwd=self._cwd,
        )
        self._processed_spec_slugs: set[str] = set()
        self._cleaned_spec_slugs: set[str] = set()
        self._deferred_clean_slate: bool = False
        self._last_outcome: TicketOutcome | None = None
        self._accumulated_tokens: int = 0

    @property
    def cwd(self) -> Path | None:
        """Configured working directory for queue orchestration."""
        return self._cwd

    @property
    def discord_thread_manager(self) -> Any | None:
        """DiscordThreadManager instance associated with queue orchestrator."""
        return self._discord_thread_manager

    @property
    def discord_logger(self) -> Any | None:
        """DiscordLogger instance associated with queue orchestrator."""
        return self._discord_logger

    @property
    def presence_coordinator(self) -> Any | None:
        """PresenceCoordinator instance associated with queue orchestrator."""
        return self._presence_coordinator

    @property
    def runner_config(self) -> Any | None:
        """RunnerConfig composite configuration."""
        return self._runner_config

    @property
    def has_deferred_clean_slate(self) -> bool:
        """Return True if interactive clean-slate archival was deferred at queue drain."""
        return self._deferred_clean_slate

    @property
    def lifecycle_outcomes(self) -> list[TicketOutcome]:
        """List of ticket outcomes collected across the current or most recent lifecycle run."""
        return list(self._lifecycle_outcomes)

    @property
    def last_outcome(self) -> TicketOutcome | None:
        """Outcome of the most recently processed ticket."""
        return self._last_outcome

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed across all sessions in this lifecycle run."""
        outcomes_tokens = sum(o.tokens_consumed for o in self._lifecycle_outcomes)
        total = self._accumulated_tokens + outcomes_tokens
        if total > 0:
            return total
        if self.supervisor is not None and hasattr(self.supervisor, "cumulative_tokens"):
            return int(getattr(self.supervisor, "cumulative_tokens", 0))
        if self._state_coordinator is not None:
            state = self._state_coordinator.current_state
            if state and state.tokens.current > 0:
                return state.tokens.current
        return 0

    def record_tokens(self, count: int) -> None:
        """Accumulate token consumption into this lifecycle run."""
        self._accumulated_tokens += max(0, count)

    def format_celebration_banner(
        self,
        tickets_committed: int | None = None,
        total_tokens: int | None = None,
    ) -> str:
        """Render the verbatim completion banner with current or provided metrics."""
        committed = (
            tickets_committed
            if tickets_committed is not None
            else sum(1 for o in self._lifecycle_outcomes if o.is_approved)
        )
        tokens = total_tokens if total_tokens is not None else self.total_tokens
        return format_celebration_banner(tickets_committed=committed, total_tokens=tokens)

    async def print_celebration_banner(
        self,
        printer: Callable[[str], None] = print,
        console: Any | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
        delay: float = 2.0,
        tickets_committed: int | None = None,
        total_tokens: int | None = None,
    ) -> None:
        """Render celebration banner in bold green and pause before clean exit."""
        banner = self.format_celebration_banner(
            tickets_committed=tickets_committed,
            total_tokens=total_tokens,
        )
        if console is not None:
            console.print(banner, style="bold green")
            if printer is not print:
                for line in banner.splitlines():
                    printer(line)
        else:
            if printer is print:
                from rich.console import Console

                Console().print(banner, style="bold green")
            else:
                for line in banner.splitlines():
                    printer(line)

        active_sleep = sleep_fn or asyncio.sleep
        if delay > 0:
            await active_sleep(delay)

    @property
    def is_paused(self) -> bool:
        """Return True if queue execution is paused, False otherwise."""
        return self._is_paused

    async def print_completion_summary(
        self,
        printer: Callable[[str], None] = print,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Print compact completion summary on graceful exit."""
        if self._summary_printed:
            return
        self._summary_printed = True

        approved = sum(1 for o in self._lifecycle_outcomes if o.is_approved)
        skipped = sum(1 for o in self._lifecycle_outcomes if o.is_skipped)
        aborted = sum(1 for o in self._lifecycle_outcomes if o.is_aborted)
        total = len(self._lifecycle_outcomes)

        commit_shas = [o.commit_sha[:7] for o in self._lifecycle_outcomes if o.commit_sha]
        commits_str = ", ".join(commit_shas) if commit_shas else "none"

        try:
            branch = await self._git_operations.get_current_branch()
            branch = branch.strip() if branch else "unknown"
        except Exception:
            branch = "unknown"

        active_clock = clock or self._clock
        start = (
            self._lifecycle_start_time
            if self._lifecycle_start_time is not None
            else active_clock()
        )
        duration = max(0.0, active_clock() - start)

        printer("[Queue] --- Completion Summary ---")
        printer(
            f"[Queue] Tickets processed: {total} "
            f"({approved} approved, {skipped} skipped, {aborted} aborted)"
        )
        printer(f"[Queue] Commits authored: {commits_str}")
        printer(f"[Queue] Working branch: {branch}")
        printer(f"[Queue] Elapsed time: {duration:.1f}s")
        printer("[Queue] --------------------------")

    @property
    def is_locked(self) -> bool:
        """Return True if the sentinel lock is held by this instance."""
        return self._lock.is_locked

    @property
    def clean_slate_archiver(self) -> CleanSlateArchiver:
        """Archiver handling ephemeral clean-slate lifecycle."""
        return self._clean_slate_archiver

    @property
    def lock(self) -> QueueFileLock:
        """The sentinel lock manager instance."""
        return self._lock

    @property
    def ticket_store(self) -> TicketRepository:
        """Backing ticket repository."""
        return self._ticket_store

    @property
    def gotchas_store(self) -> GotchasStore:
        """Backing gotchas store."""
        return self._gotchas_store

    @property
    def git_operations(self) -> GitOperations:
        """Underlying git operations interactor."""
        return self._git_operations

    @property
    def processor(self) -> TicketProcessor | Callable[[Ticket], Awaitable[TicketOutcome]] | None:
        """Injected ticket processor seam."""
        return self._processor

    @property
    def commit_scope(self) -> str:
        """Default architectural subsystem commit scope."""
        return self._commit_scope

    @property
    def state_coordinator(self) -> StateCoordinator | None:
        """Coordinating service for durable runner state persistence."""
        return self._state_coordinator

    def transition_to_gatekeeper(self, attempts: int | None = None) -> None:
        """Transition runner state to GATEKEEPER if coordinator is present."""
        if self._state_coordinator is not None:
            self._state_coordinator.transition_to_gatekeeper(verification_attempts=attempts)

    @property
    def supervisor(self) -> Any:
        """Underlying WorkerSupervisor if available through processor."""
        if self._processor is not None and hasattr(self._processor, "supervisor"):
            return self._processor.supervisor
        return None

    def acquire_lock(self) -> None:
        """Acquire the sentinel queue lock if not already held."""
        if not self._lock.is_locked:
            self._lock.acquire()

    def release_lock(self) -> None:
        """Release the sentinel queue lock if held."""
        if self._lock.is_locked:
            self._lock.release()

    @property
    def ui_event_sink(self) -> UiEventSink | None:
        """UiEventSink telemetry sink."""
        return self._ui_event_sink

    @ui_event_sink.setter
    def ui_event_sink(self, value: UiEventSink | None) -> None:
        self._ui_event_sink = value

    def pause(self) -> None:
        """Pause queue progression and release the sentinel lock for external edits."""
        self._is_paused = True
        if self._state_coordinator is not None:
            self._state_coordinator.transition_to_pause_requested()
        if self._ui_event_sink is not None:
            try:
                self._ui_event_sink.emit("runner", "Queue execution paused")
            except Exception:
                pass
        self.release_lock()

    def resume(self) -> None:
        """Resume queue progression and re-acquire sentinel lock."""
        self._is_paused = False
        if self._state_coordinator is not None:
            try:
                state = self._state_coordinator.get_or_create_state()
                if state.status == StateStatus.PAUSE_REQUESTED:
                    if state.active_ticket_id:
                        self._state_coordinator.transition_to_working(
                            ticket_id=state.active_ticket_id,
                            session_id=state.opencode_session_id,
                            verification_attempts=state.verification_attempts,
                        )
                    else:
                        self._state_coordinator.transition_to_idle()
            except Exception:
                pass
        if self._ui_event_sink is not None:
            try:
                self._ui_event_sink.emit("runner", "Queue execution resumed")
            except Exception:
                pass
        self.acquire_lock()

    def close(self) -> None:
        """Release any held lock handles upon shutdown."""
        self.release_lock()

    def __enter__(self) -> QueueOrchestrator:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    async def __aenter__(self) -> QueueOrchestrator:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.close()

    async def run_next(
        self,
        processor: TicketProcessor | Callable[[Ticket], Awaitable[TicketOutcome]] | None = None,
    ) -> TicketOutcome | None:
        """Execute the next pending ticket in sequence.

        Returns:
            The finalized TicketOutcome, or None if queue is paused or exhausted.

        Raises:
            RuntimeError: If no processor is configured.
            QueueLockError: If sentinel lock acquisition fails.
            TicketFormatError: If ticket serialization or relocation fails.
            GitError: If git operations fail.
        """
        if self._is_paused:
            return None

        active_processor = processor or self._processor
        if active_processor is None:
            raise RuntimeError("No ticket processor configured.")

        self.acquire_lock()

        ticket = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
        if ticket is None:
            if self._state_coordinator is not None:
                self._state_coordinator.transition_to_idle()
            self.release_lock()
            return None

        if self._state_coordinator is not None:
            self._state_coordinator.transition_to_working(ticket_id=ticket.id)
            if (
                hasattr(active_processor, "state_coordinator")
                and getattr(active_processor, "state_coordinator", None) is None
            ):
                active_processor.state_coordinator = self._state_coordinator

        if self._ui_event_sink is not None:
            try:
                self._ui_event_sink.emit("runner", f"Starting ticket {ticket.id}")
            except Exception:
                pass

        slug = None
        if ticket.spec_path:
            slug = Path(ticket.spec_path).stem
        elif ticket.path:
            parent_name = ticket.path.parent.name
            slug = parent_name if parent_name != "completed" else ticket.path.parent.parent.name
        if slug:
            self._processed_spec_slugs.add(slug)
            self._cleaned_spec_slugs.discard(slug)

        try:
            outcome = await active_processor(ticket)
        except UserAbortError as exc:
            self._last_outcome = TicketOutcome.aborted(details=str(exc))
            self.release_lock()
            raise
        except Exception:
            self.release_lock()
            raise

        if outcome.is_approved:
            # 1. Relocate ticket to completed/ with timestamp
            self._ticket_store.finalize_completed(ticket)

            # 2. Append new gotchas atomically
            if outcome.new_gotchas:
                self._gotchas_store.append(outcome.new_gotchas)

            # 3. Stage and author single atomic commit
            scope = outcome.scope or self._commit_scope
            prefix = outcome.commit_prefix or self._git_operations.commit_prefix
            changes = list(outcome.changes)
            sha = await self._git_operations.commit_ticket(
                scope=scope,
                title=ticket.title,
                changes=changes,
                commit_prefix=prefix,
            )
            final_outcome = outcome.with_commit_sha(sha)
            self._last_outcome = final_outcome

            if self._ui_event_sink is not None:
                try:
                    self._ui_event_sink.emit("runner", f"Authoring commit: {prefix}: {ticket.title}")
                    self._ui_event_sink.emit("runner", f"Ticket {ticket.id} approved")
                except Exception:
                    pass

        elif outcome.is_skipped:
            # 1. Reset working tree to pristine state
            await self._git_operations.reset_working_tree()

            # 2. Relocate ticket to completed/ with failure details
            self._ticket_store.finalize_skipped(ticket, details=outcome.details)
            final_outcome = outcome
            self._last_outcome = final_outcome

            if self._ui_event_sink is not None:
                try:
                    self._ui_event_sink.emit("runner", f"Ticket {ticket.id} skipped")
                except Exception:
                    pass

        elif outcome.is_aborted:
            self._last_outcome = outcome
            self.release_lock()
            msg = (
                str(outcome.details)
                if outcome.details is not None
                else f"Execution aborted for ticket '{ticket.id}'."
            )
            raise UserAbortError(msg)

        else:
            raise ValueError(f"Unsupported ticket outcome status: {outcome.status}")

        # If queue is now empty, release lock
        remaining = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
        if remaining is None:
            if self._state_coordinator is not None:
                self._state_coordinator.transition_to_idle()
            self.release_lock()

        return final_outcome

    async def run_all(
        self,
        processor: TicketProcessor | Callable[[Ticket], Awaitable[TicketOutcome]] | None = None,
    ) -> list[TicketOutcome]:
        """Execute all pending tickets in sequence until queue is exhausted or paused."""
        outcomes: list[TicketOutcome] = []
        while not self._is_paused:
            outcome = await self.run_next(processor=processor)
            if outcome is None:
                break
            outcomes.append(outcome)
        return outcomes

    async def _handle_clean_slate(
        self,
        policy: str,
        printer: Callable[[str], None],
    ) -> None:
        """Trigger ephemeral clean-slate archival for exhausted spec queues."""
        if policy == "never":
            return

        target_slugs: list[str] = []
        if self._spec_slug:
            target_slugs = [self._spec_slug]
        elif self._processed_spec_slugs:
            target_slugs = sorted(self._processed_spec_slugs)

        for slug in target_slugs:
            if slug in self._cleaned_spec_slugs:
                continue
            slug_dir = self._tickets_dir / slug
            if slug_dir.is_dir():
                res = await self._clean_slate_archiver.clean_slate(
                    spec_slug=slug,
                    policy=policy,
                    printer=printer,
                )
                if res:
                    self._cleaned_spec_slugs.add(slug)

    async def run_lifecycle(
        self,
        processor: TicketProcessor | Callable[[Ticket], Awaitable[TicketOutcome]] | None = None,
        lifecycle: LifecycleConfig | RunnerConfig | str | None = None,
        poll_interval: float | None = None,
        printer: Callable[[str], None] = print,
        stop_event: asyncio.Event | None = None,
        max_standby_iterations: int | None = None,
        clean_slate_policy: str | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
        banner_delay: float = 2.0,
        console: Any | None = None,
        total_tokens: int | None = None,
    ) -> int:
        """Drive full queue lifecycle respecting queue_completion policy (standby/terminate).

        Args:
            processor: Injected ticket processor seam. Defaults to self.processor.
            lifecycle: Policy specification (RunnerConfig, LifecycleConfig, or "standby"/"terminate").
            poll_interval: Idle standby polling interval in seconds (default: 5.0 or from config).
            printer: Output callback for console notifications.
            stop_event: Optional asyncio.Event to gracefully exit standby loop.
            max_standby_iterations: Optional iteration limit for tests.
            clean_slate_policy: Optional override for clean_slate policy (e.g. 'always' / 'never').
            sleep_fn: Optional injected async sleep callable for deterministic clock tests.
            clock: Optional injected clock callable for deterministic duration tests.
            banner_delay: Delay in seconds to display celebration banner before clean exit.
            console: Optional Rich Console for bold green banner formatting.
            total_tokens: Optional total tokens consumed override for tests.

        Returns:
            Exit status code (0 clean terminate/stop, 1 runtime error, 2 abort, 130 SIGINT).

        Raises:
            RuntimeError: If pending tickets exist or arrive without a configured processor.
            ValueError: If an unknown lifecycle policy is specified.
        """
        active_processor = processor or self._processor
        active_sleep = sleep_fn or asyncio.sleep
        self._lifecycle_outcomes = []
        self._accumulated_tokens = 0
        self._summary_printed = False
        self._deferred_clean_slate = False
        self._cleaned_spec_slugs.clear()
        active_clock = clock or self._clock
        self._lifecycle_start_time = active_clock()

        config_poll_interval = 5.0
        if isinstance(lifecycle, RunnerConfig):
            policy = lifecycle.lifecycle.queue_completion
            active_clean_slate = clean_slate_policy or lifecycle.lifecycle.clean_slate
            config_poll_interval = lifecycle.lifecycle.poll_interval
        elif isinstance(lifecycle, LifecycleConfig):
            policy = lifecycle.queue_completion
            active_clean_slate = clean_slate_policy or lifecycle.clean_slate
            config_poll_interval = lifecycle.poll_interval
        elif isinstance(lifecycle, str):
            policy = lifecycle.strip().lower()
            active_clean_slate = clean_slate_policy or "never"
        elif lifecycle is None:
            policy = "standby"
            active_clean_slate = clean_slate_policy or "never"
        else:
            raise ValueError(f"Unsupported lifecycle configuration type: {type(lifecycle)}")

        effective_poll_interval = poll_interval if poll_interval is not None else config_poll_interval

        if policy not in ("standby", "terminate"):
            raise ValueError(f"Unsupported queue completion policy: '{policy}'")

        try:
            # 1. Check if there are pending tickets without a processor
            pending = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
            if pending is not None and active_processor is None:
                raise RuntimeError("No ticket processor configured.")

            # 2. Process initial queue until empty, waiting if paused
            if active_processor is not None:
                while not (stop_event is not None and stop_event.is_set()):
                    if self._is_paused:
                        self.release_lock()
                        if stop_event is not None and sleep_fn is None:
                            try:
                                await asyncio.wait_for(stop_event.wait(), timeout=effective_poll_interval)
                                break
                            except asyncio.TimeoutError:
                                pass
                        else:
                            await active_sleep(effective_poll_interval)
                        continue

                    outcome = await self.run_next(processor=active_processor)
                    if outcome is None:
                        break
                    self._lifecycle_outcomes.append(outcome)

            pending = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
            if pending is not None and (stop_event is not None and stop_event.is_set()):
                # Execution was stopped before queue drained
                self.release_lock()
                await self.print_completion_summary(printer=printer, clock=active_clock)
                return 0

            # 3. Queue is exhausted
            printer("[Queue] Queue exhausted: no pending tickets.")
            if self._ui_event_sink is not None:
                try:
                    self._ui_event_sink.emit("runner", "Queue complete: all tickets processed")
                except Exception:
                    pass
            if self._state_coordinator is not None:
                self._state_coordinator.transition_to_idle()

            # 4. Apply lifecycle policy
            if policy == "terminate":
                self.release_lock()
                await self._handle_clean_slate(policy=active_clean_slate, printer=printer)
                printer("[Queue] Lifecycle policy 'terminate': Queue complete. Exiting.")
                await self.print_completion_summary(printer=printer, clock=active_clock)
                await self.print_celebration_banner(
                    printer=printer,
                    console=console,
                    sleep_fn=active_sleep,
                    delay=banner_delay,
                    total_tokens=total_tokens,
                )
                return 0

            # Standby mode: archive at drain for 'always', defer prompt for 'interactive'
            if active_clean_slate == "always":
                self.release_lock()
                await self._handle_clean_slate(policy="always", printer=printer)
            elif active_clean_slate == "interactive":
                self._deferred_clean_slate = True

            self.release_lock()
            printer(STANDBY_BANNER)
            iteration = 0
            while not (stop_event is not None and stop_event.is_set()):
                if max_standby_iterations is not None and iteration >= max_standby_iterations:
                    break

                if self._is_paused:
                    self.release_lock()
                    if stop_event is not None and sleep_fn is None:
                        try:
                            await asyncio.wait_for(stop_event.wait(), timeout=effective_poll_interval)
                            break
                        except asyncio.TimeoutError:
                            pass
                    else:
                        try:
                            await active_sleep(effective_poll_interval)
                        except asyncio.CancelledError:
                            raise
                    continue

                if stop_event is not None and sleep_fn is None:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=effective_poll_interval)
                        break
                    except asyncio.TimeoutError:
                        pass
                else:
                    try:
                        await active_sleep(effective_poll_interval)
                    except asyncio.CancelledError:
                        raise

                iteration += 1

                if stop_event is not None and stop_event.is_set():
                    break

                pending = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
                if pending is not None:
                    printer(f"[Queue] Detected new pending ticket '{pending.id}'. Resuming queue execution...")
                    if active_processor is None:
                        raise RuntimeError("No ticket processor configured.")
                    while not (stop_event is not None and stop_event.is_set()):
                        if self._is_paused:
                            self.release_lock()
                            if stop_event is not None and sleep_fn is None:
                                try:
                                    await asyncio.wait_for(stop_event.wait(), timeout=effective_poll_interval)
                                    break
                                except asyncio.TimeoutError:
                                    pass
                            else:
                                await active_sleep(effective_poll_interval)
                            continue
                        outcome = await self.run_next(processor=active_processor)
                        if outcome is None:
                            break
                        self._lifecycle_outcomes.append(outcome)

                    remaining = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
                    if remaining is None:
                        printer("[Queue] Queue exhausted: no pending tickets.")
                        if self._state_coordinator is not None:
                            self._state_coordinator.transition_to_idle()
                        if active_clean_slate == "always":
                            self.release_lock()
                            await self._handle_clean_slate(policy="always", printer=printer)
                        elif active_clean_slate == "interactive":
                            self._deferred_clean_slate = True

                    if stop_event is not None and stop_event.is_set():
                        break

                    self.release_lock()
                    printer(STANDBY_BANNER)

            self.release_lock()
            if self._deferred_clean_slate:
                self._deferred_clean_slate = False
                await self._handle_clean_slate(policy="interactive", printer=printer)
            await self.print_completion_summary(printer=printer, clock=active_clock)
            return 0
        except KeyboardInterrupt:
            self.release_lock()
            printer("\n[Queue] Interrupted by SIGINT.")
            if self._deferred_clean_slate:
                self._deferred_clean_slate = False
                await self._handle_clean_slate(policy="interactive", printer=printer)
            elif policy == "terminate" and active_clean_slate != "never":
                await self._handle_clean_slate(policy=active_clean_slate, printer=printer)
            await self.print_completion_summary(printer=printer, clock=active_clock)
            return 130
        except UserAbortError as exc:
            if self._last_outcome is None or not self._last_outcome.is_aborted:
                self._last_outcome = TicketOutcome.aborted(details=str(exc))
            if self._last_outcome not in self._lifecycle_outcomes:
                self._lifecycle_outcomes.append(self._last_outcome)
            printer(f"\n[Queue] Aborted by operator: {exc}")
            return 2
        except RuntimeError as exc:
            if str(exc) == "No ticket processor configured.":
                raise
            self.release_lock()
            printer(f"\n[Queue] Runtime error: {exc}")
            return 1
        finally:
            self.release_lock()

