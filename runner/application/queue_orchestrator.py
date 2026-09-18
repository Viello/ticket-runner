"""Queue orchestrator coordinating lock lifecycle, processor seam, and atomic commits."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.markdown.file_lock import DEFAULT_LOCK_PATH, QueueFileLock
from runner.adapters.markdown.gotchas_store import DEFAULT_GOTCHAS_PATH, GotchasStore
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.clean_slate import CleanSlateArchiver
from runner.application.git_operations import GitOperations
from runner.domain.config import LifecycleConfig, RunnerConfig
from runner.domain.exceptions import UserAbortError
from runner.domain.ticket import Ticket
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
    ) -> TicketOutcome:
        """Construct an approved ticket outcome."""
        return cls(
            status=TicketOutcomeStatus.APPROVED,
            new_gotchas=tuple(new_gotchas),
            changes=tuple(changes),
            scope=scope,
            commit_prefix=commit_prefix,
            commit_sha=commit_sha,
        )

    @classmethod
    def skipped(
        cls,
        details: str | Mapping[str, Any] | None = None,
    ) -> TicketOutcome:
        """Construct a skipped ticket outcome with failure details."""
        return cls(
            status=TicketOutcomeStatus.SKIPPED,
            details=details,
        )

    @classmethod
    def aborted(
        cls,
        details: str | Mapping[str, Any] | None = None,
    ) -> TicketOutcome:
        """Construct an aborted ticket outcome with failure details."""
        return cls(
            status=TicketOutcomeStatus.ABORTED,
            details=details,
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
    ) -> None:
        self._cwd = cwd
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
        self._last_outcome: TicketOutcome | None = None

    @property
    def last_outcome(self) -> TicketOutcome | None:
        """Outcome of the most recently processed ticket."""
        return self._last_outcome

    @property
    def is_paused(self) -> bool:
        """Return True if queue execution is paused, False otherwise."""
        return self._is_paused

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

    def acquire_lock(self) -> None:
        """Acquire the sentinel queue lock if not already held."""
        if not self._lock.is_locked:
            self._lock.acquire()

    def release_lock(self) -> None:
        """Release the sentinel queue lock if held."""
        if self._lock.is_locked:
            self._lock.release()

    def pause(self) -> None:
        """Pause queue progression and release the sentinel lock for external edits."""
        self._is_paused = True
        self.release_lock()

    def resume(self) -> None:
        """Resume queue progression and re-acquire sentinel lock."""
        self._is_paused = False
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
            self.release_lock()
            return None

        slug = None
        if ticket.spec_path:
            slug = Path(ticket.spec_path).stem
        elif ticket.path:
            parent_name = ticket.path.parent.name
            slug = parent_name if parent_name != "completed" else ticket.path.parent.parent.name
        if slug:
            self._processed_spec_slugs.add(slug)

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

        elif outcome.is_skipped:
            # 1. Reset working tree to pristine state
            await self._git_operations.reset_working_tree()

            # 2. Relocate ticket to completed/ with failure details
            self._ticket_store.finalize_skipped(ticket, details=outcome.details)
            final_outcome = outcome
            self._last_outcome = final_outcome

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
            slug_dir = self._tickets_dir / slug
            if slug_dir.is_dir():
                await self._clean_slate_archiver.clean_slate(
                    spec_slug=slug,
                    policy=policy,
                    printer=printer,
                )

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

        Returns:
            Exit status code (0 for clean termination or standby exit).

        Raises:
            RuntimeError: If pending tickets exist or arrive without a configured processor.
            ValueError: If an unknown lifecycle policy is specified.
        """
        active_processor = processor or self._processor
        active_sleep = sleep_fn or asyncio.sleep

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

            # 2. Process initial queue until empty or paused
            if active_processor is not None:
                while not self._is_paused:
                    outcome = await self.run_next(processor=active_processor)
                    if outcome is None:
                        break

            if self._is_paused:
                return 0

            # 3. Queue is exhausted
            printer("[Queue] Queue exhausted: no pending tickets.")

            # Ephemeral clean-slate archival
            await self._handle_clean_slate(policy=active_clean_slate, printer=printer)

            # 4. Apply lifecycle policy
            if policy == "terminate":
                printer("[Queue] Lifecycle policy 'terminate': Queue complete. Exiting.")
                return 0

            # Standby mode: release sentinel lock before entering idle watch loop
            self.release_lock()
            printer(STANDBY_BANNER)
            iteration = 0
            while not self._is_paused:
                if stop_event is not None and stop_event.is_set():
                    break
                if max_standby_iterations is not None and iteration >= max_standby_iterations:
                    break

                try:
                    await active_sleep(effective_poll_interval)
                except asyncio.CancelledError:
                    raise

                iteration += 1

                if self._is_paused or (stop_event is not None and stop_event.is_set()):
                    break

                pending = self._ticket_store.select_next_pending(spec_slug=self._spec_slug)
                if pending is not None:
                    printer(f"[Queue] Detected new pending ticket '{pending.id}'. Resuming queue execution...")
                    if active_processor is None:
                        raise RuntimeError("No ticket processor configured.")
                    while not self._is_paused:
                        outcome = await self.run_next(processor=active_processor)
                        if outcome is None:
                            break

                    if self._is_paused:
                        break

                    printer("[Queue] Queue exhausted: no pending tickets.")
                    await self._handle_clean_slate(policy=active_clean_slate, printer=printer)
                    if policy == "terminate":
                        printer("[Queue] Lifecycle policy 'terminate': Queue complete. Exiting.")
                        return 0

                    self.release_lock()
                    printer(STANDBY_BANNER)

            return 0
        except UserAbortError as exc:
            if self._last_outcome is None or not self._last_outcome.is_aborted:
                self._last_outcome = TicketOutcome.aborted(details=str(exc))
            printer(f"\n[Queue] Aborted by operator: {exc}")
            return 2
        finally:
            self.release_lock()

