"""Unit tests for QueueOrchestrator interactor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.markdown.file_lock import QueueFileLock
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.git_operations import GitOperations
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
    TicketOutcomeStatus,
)
from runner.application.state_coordinator import StateCoordinator
from runner.domain.config import LifecycleConfig
from runner.domain.exceptions import UserAbortError
from runner.domain.state import StateStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_ticket_repository import FakeTicketRepository


def _make_ticket(
    ticket_id: str,
    title: str = "Test Ticket",
    status: TicketStatus = TicketStatus.PENDING,
    spec_path: str = "docs/specs/test.md",
    path: Path | None = None,
) -> Ticket:
    p = path or Path(f"docs/tickets/test/{ticket_id}-test.md")
    return Ticket(
        id=ticket_id,
        title=title,
        status=status,
        spec_path=spec_path,
        requirements=("Requirement 1",),
        acceptance_criteria=("Criteria 1",),
        gotchas=(),
        path=p,
    )


@pytest.fixture
def fake_runner() -> FakeCommandRunner:
    runner = FakeCommandRunner()
    # Script status porcelain clean
    runner.register(["git", "status", "--porcelain"], stdout="")
    # Script symbolic-ref
    runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    # Script add all
    runner.register(["git", "add", "."], stdout="")
    # Script commit
    runner.register(["git", "commit", "-m"], stdout="")
    # Script rev-parse HEAD
    runner.register(["git", "rev-parse", "HEAD"], stdout="a" * 40 + "\n")
    # Script reset hard
    runner.register(["git", "reset", "--hard", "HEAD"], stdout="HEAD is now at aaaaaaa\n")
    # Script clean
    runner.register(["git", "clean", "-fd"], stdout="")
    return runner


@pytest.fixture
def git_ops(fake_runner: FakeCommandRunner) -> GitOperations:
    return GitOperations(runner=fake_runner)


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def lock_path(temp_dir: Path) -> Path:
    return temp_dir / ".queue.lock"


@pytest.fixture
def gotchas_path(temp_dir: Path) -> Path:
    return temp_dir / "gotchas.md"


@pytest.fixture
def queue_lock(lock_path: Path) -> QueueFileLock:
    return QueueFileLock(lock_path=lock_path)


@pytest.fixture
def gotchas_store(gotchas_path: Path) -> GotchasStore:
    return GotchasStore(path=gotchas_path)


# --- Basic Initialization & Processor Seam ---

def test_run_next_without_processor_raises(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([_make_ticket("T001")])
    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    with pytest.raises(RuntimeError, match="No ticket processor configured"):
        asyncio.run(orchestrator.run_next())


def test_empty_queue_returns_none_and_lock_not_held(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])

    async def dummy_processor(ticket: Ticket) -> TicketOutcome:
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=dummy_processor,
    )

    result = asyncio.run(orchestrator.run_next())
    assert result is None
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


# --- Sequential Execution Order ---

def test_sequential_execution_order(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    t3 = _make_ticket("T003", title="Third Ticket")
    t1 = _make_ticket("T001", title="First Ticket")
    t2 = _make_ticket("T002", title="Second Ticket")

    ticket_repo = FakeTicketRepository([t3, t1, t2])
    executed_order: list[str] = []

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        executed_order.append(ticket.id)
        return TicketOutcome.approved(changes=[f"Implemented {ticket.id}"])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    outcomes = asyncio.run(orchestrator.run_all())

    assert len(outcomes) == 3
    assert executed_order == ["T001", "T002", "T003"]
    assert all(o.is_approved for o in outcomes)


# --- Approved Ticket Lifecycle: Atomic Commit, Relocation, Gotchas ---

def test_approved_ticket_lifecycle(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    ticket = _make_ticket("T001", title="Add admin table")
    ticket_repo = FakeTicketRepository([ticket])

    new_gotcha_text = "Table virtualizer requires explicit rowHeight"

    async def fake_processor(t: Ticket) -> TicketOutcome:
        return TicketOutcome.approved(
            new_gotchas=[new_gotcha_text],
            changes=["Add virtualized admin table component", "Add integration tests"],
            scope="ui",
        )

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True
    assert outcome.commit_sha == "a" * 40

    # 1. Relocated to completed
    assert ticket.status == TicketStatus.COMPLETED
    assert "completed" in str(ticket.path)

    # 2. Gotchas appended
    gotchas_content = gotchas_store.load()
    assert new_gotcha_text in gotchas_content

    # 3. Single commit authored with conventional commit format
    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 1
    commit_msg = commit_invocations[0].cmd[3]
    assert commit_msg.startswith("feat(ui): Add admin table")
    assert "- Add virtualized admin table component" in commit_msg
    assert "- Add integration tests" in commit_msg
    assert "T001" not in commit_msg


def test_approved_ticket_default_scope(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    ticket = _make_ticket("T005", title="Refactor queue scan")
    ticket_repo = FakeTicketRepository([ticket])

    async def fake_processor(t: Ticket) -> TicketOutcome:
        # No scope specified; should fallback to default commit_scope
        return TicketOutcome.approved(changes=["Improve scan speed"])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
        commit_scope="queue",
    )

    outcome = asyncio.run(orchestrator.run_next())
    assert outcome is not None
    assert outcome.is_approved

    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 1
    assert commit_invocations[0].cmd[3].startswith("feat(queue): Refactor queue scan")


# --- Skipped Ticket Lifecycle: Reset & Relocate Without Commit ---

def test_skipped_ticket_lifecycle(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    ticket = _make_ticket("T002", title="Flaky worker task")
    ticket_repo = FakeTicketRepository([ticket])

    async def fake_processor(t: Ticket) -> TicketOutcome:
        return TicketOutcome.skipped(details="Circuit breaker tripped after 3 failed attempts")

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_skipped is True

    # 1. Working tree was reset
    assert ["git", "reset", "--hard", "HEAD"] in fake_runner.commands
    assert ["git", "clean", "-fd"] in fake_runner.commands

    # 2. Relocated to completed with skipped status
    assert ticket.status == TicketStatus.SKIPPED
    assert "completed" in str(ticket.path)

    # 3. No commit was authored
    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 0


# --- Lock Lifecycle: Held During Processing, Released on Pause, Re-acquired on Resume ---

def test_sentinel_lock_held_during_processing(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([ticket])
    lock_was_held: list[bool] = []

    async def fake_processor(t: Ticket) -> TicketOutcome:
        lock_was_held.append(queue_lock.is_locked)
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    assert queue_lock.is_locked is False
    outcome = asyncio.run(orchestrator.run_next())
    assert outcome is not None
    assert lock_was_held == [True]
    # Queue is now empty, lock should be released
    assert queue_lock.is_locked is False


def test_pause_releases_lock_and_resume_reacquires(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([ticket])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    # Acquire lock initially
    orchestrator.acquire_lock()
    assert orchestrator.is_locked is True
    assert queue_lock.is_locked is True

    # Pause releases lock handle
    orchestrator.pause()
    assert orchestrator.is_paused is True
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False

    # Resume re-acquires lock
    orchestrator.resume()
    assert orchestrator.is_paused is False
    assert orchestrator.is_locked is True
    assert queue_lock.is_locked is True

    orchestrator.release_lock()
    assert orchestrator.is_locked is False


def test_pause_prevents_run_next(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([ticket])
    processor_invoked = False

    async def fake_processor(t: Ticket) -> TicketOutcome:
        nonlocal processor_invoked
        processor_invoked = True
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    orchestrator.pause()
    result = asyncio.run(orchestrator.run_next())
    assert result is None
    assert processor_invoked is False


def test_resume_picks_up_inserted_ticket(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    t2 = _make_ticket("T002", title="Second Ticket")
    ticket_repo = FakeTicketRepository([t2])

    executed_tickets: list[str] = []

    async def fake_processor(t: Ticket) -> TicketOutcome:
        executed_tickets.append(t.id)
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    # Pause runner
    orchestrator.pause()
    assert queue_lock.is_locked is False

    # External author inserts T001 into repository during pause
    t1 = _make_ticket("T001", title="Urgent First Ticket")
    ticket_repo.add_ticket(t1)

    # Resume runner
    orchestrator.resume()
    assert queue_lock.is_locked is True

    # Next ticket executed should be T001
    outcome = asyncio.run(orchestrator.run_next())
    assert outcome is not None
    assert executed_tickets == ["T001"]


# --- Context Manager Support ---

def test_context_manager_cleans_up_lock(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])

    with QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    ) as orchestrator:
        orchestrator.acquire_lock()
        assert queue_lock.is_locked is True

    assert queue_lock.is_locked is False


# --- Lifecycle Support: Standby, Terminate, and Fail-Fast Seams ---

def test_run_lifecycle_terminate_empty_queue(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    printed: list[str] = []

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    exit_code = asyncio.run(
        orchestrator.run_lifecycle(lifecycle="terminate", printer=printed.append)
    )

    assert exit_code == 0
    assert any("Queue exhausted" in p for p in printed)
    assert any("terminate" in p.lower() for p in printed)
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_terminate_after_draining_queue(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    t1 = _make_ticket("T001", title="First Ticket")
    t2 = _make_ticket("T002", title="Second Ticket")
    ticket_repo = FakeTicketRepository([t1, t2])
    executed: list[str] = []
    printed: list[str] = []

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        executed.append(ticket.id)
        return TicketOutcome.approved(changes=[f"Work {ticket.id}"])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    exit_code = asyncio.run(
        orchestrator.run_lifecycle(lifecycle="terminate", printer=printed.append)
    )

    assert exit_code == 0
    assert executed == ["T001", "T002"]
    assert any("Queue exhausted" in p for p in printed)
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_standby_polls_and_resumes_when_ticket_added(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    executed: list[str] = []
    printed: list[str] = []
    stop_event = asyncio.Event()

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        executed.append(ticket.id)
        # Stop standby loop once ticket is processed
        stop_event.set()
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    async def scenario() -> int:
        async def add_ticket_later() -> None:
            await asyncio.sleep(0.02)
            ticket_repo.add_ticket(_make_ticket("T001", title="Appeared in Standby"))

        add_task = asyncio.create_task(add_ticket_later())
        run_task = asyncio.create_task(
            orchestrator.run_lifecycle(
                lifecycle="standby",
                poll_interval=0.01,
                printer=printed.append,
                stop_event=stop_event,
            )
        )
        await add_task
        return await run_task

    exit_code = asyncio.run(scenario())
    assert exit_code == 0
    assert executed == ["T001"]
    assert any("standby" in p.lower() for p in printed)
    assert any("Resuming" in p or "Detected" in p for p in printed)
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_standby_is_cancellable(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    async def scenario() -> None:
        task = asyncio.create_task(
            orchestrator.run_lifecycle(lifecycle="standby", poll_interval=1.0)
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_pending_without_processor_raises_before_lock(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    ticket = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([ticket])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=None,
    )

    with pytest.raises(RuntimeError, match="No ticket processor configured."):
        asyncio.run(orchestrator.run_lifecycle())

    # Invariants: lock not acquired, no git commands executed, ticket untouched
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False
    assert len(fake_runner.invocations) == 0
    assert ticket.status == TicketStatus.PENDING


def test_run_lifecycle_standby_raises_when_ticket_appears_without_processor(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=None,
    )

    async def scenario() -> None:
        async def add_ticket_later() -> None:
            await asyncio.sleep(0.02)
            ticket_repo.add_ticket(_make_ticket("T001"))

        add_task = asyncio.create_task(add_ticket_later())
        run_task = asyncio.create_task(
            orchestrator.run_lifecycle(lifecycle="standby", poll_interval=0.01)
        )
        await add_task
        await run_task

    with pytest.raises(RuntimeError, match="No ticket processor configured."):
        asyncio.run(scenario())

    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_supports_lifecycle_config_object(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    config = LifecycleConfig(queue_completion="terminate")
    exit_code = asyncio.run(orchestrator.run_lifecycle(lifecycle=config))
    assert exit_code == 0


def test_run_lifecycle_clean_slate_always_on_queue_exhaustion(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-clean"
    spec_dir.mkdir(parents=True, exist_ok=True)
    ticket_file = spec_dir / "T001-work.md"
    ticket_file.write_text("# T001 — Work\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-clean.md", path=ticket_file)
    ticket_repo = FakeTicketRepository([t1])

    clean_slate_invoked: list[str] = []

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            clean_slate_invoked.append(spec_slug)
            return True

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="terminate", clean_slate="always")
    exit_code = asyncio.run(orchestrator.run_lifecycle(lifecycle=config))

    assert exit_code == 0
    assert clean_slate_invoked == ["02-clean"]


def test_run_lifecycle_abort_records_outcome_releases_lock_and_returns_code_2(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    ticket = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([ticket])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.aborted(details="Operator abort requested")),
    )

    exit_code = asyncio.run(orchestrator.run_lifecycle(lifecycle="terminate"))

    assert exit_code == 2
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False
    assert orchestrator.last_outcome is not None
    assert orchestrator.last_outcome.is_aborted is True
    assert orchestrator.last_outcome.status == TicketOutcomeStatus.ABORTED
    assert "Operator abort requested" in str(orchestrator.last_outcome.details)

    # Invariants: no finalize (ticket remains pending), no git reset, no commit
    assert ticket.status == TicketStatus.PENDING
    assert ticket_repo.select_next_pending() is not None
    assert ticket_repo.select_next_pending().id == "T001"
    for invocation in fake_runner.invocations:
        assert "commit" not in invocation.argv
        assert "reset" not in invocation.argv


def test_run_lifecycle_standby_abort_stops_lifecycle_and_returns_code_2(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.aborted(details="Standby abort")),
    )

    async def scenario() -> int:
        async def add_ticket_later() -> None:
            await asyncio.sleep(0.02)
            ticket_repo.add_ticket(_make_ticket("T001"))

        add_task = asyncio.create_task(add_ticket_later())
        run_task = asyncio.create_task(
            orchestrator.run_lifecycle(lifecycle="standby", poll_interval=0.01)
        )
        await add_task
        return await run_task

    exit_code = asyncio.run(scenario())

    assert exit_code == 2
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False
    assert orchestrator.last_outcome is not None
    assert orchestrator.last_outcome.is_aborted is True


def test_run_next_abort_records_last_outcome_releases_lock_and_raises_abort_error(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    ticket = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([ticket])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.aborted(details="Direct abort")),
    )

    with pytest.raises(UserAbortError, match="Direct abort"):
        asyncio.run(orchestrator.run_next())

    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False
    assert orchestrator.last_outcome is not None
    assert orchestrator.last_outcome.is_aborted is True
    assert ticket.status == TicketStatus.PENDING
    for invocation in fake_runner.invocations:
        assert "commit" not in invocation.argv
        assert "reset" not in invocation.argv


def test_run_lifecycle_standby_prints_banner_once_and_polls_configured_interval(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    printed: list[str] = []
    recorded_sleeps: list[float] = []
    lock_states_at_print: list[bool] = []

    def recording_printer(msg: str) -> None:
        if "watching docs/tickets/" in msg or "standing by" in msg.lower():
            lock_states_at_print.append(queue_lock.is_locked)
        printed.append(msg)

    async def fake_sleep(duration: float) -> None:
        recorded_sleeps.append(duration)

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    config = LifecycleConfig(queue_completion="standby", poll_interval=8.5)
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
            sleep_fn=fake_sleep,
            max_standby_iterations=1,
        )
    )

    assert exit_code == 0
    banner_lines = [
        p for p in printed
        if "all tickets processed" in p.lower()
        and "watching docs/tickets/" in p.lower()
        and "ctrl+c" in p.lower()
    ]
    assert len(banner_lines) == 1
    assert lock_states_at_print == [False]
    assert recorded_sleeps == [8.5]
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_standby_re_entry_prints_banner_once_per_entry(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    printed: list[str] = []
    stop_event = asyncio.Event()
    sleep_count = 0

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        return TicketOutcome.approved()

    async def fake_sleep(duration: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 1:
            ticket_repo.add_ticket(_make_ticket("T001", title="Standby Ticket"))
        elif sleep_count == 3:
            stop_event.set()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle="standby",
            poll_interval=0.01,
            printer=printed.append,
            sleep_fn=fake_sleep,
            stop_event=stop_event,
        )
    )

    assert exit_code == 0
    banner_lines = [
        p for p in printed
        if "all tickets processed" in p.lower()
        and "watching docs/tickets/" in p.lower()
        and "ctrl+c" in p.lower()
    ]
    assert len(banner_lines) == 2
    assert sleep_count >= 3
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_standby_honors_poll_interval_override(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    ticket_repo = FakeTicketRepository([])
    recorded_sleeps: list[float] = []

    async def fake_sleep(duration: float) -> None:
        recorded_sleeps.append(duration)

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
    )

    config = LifecycleConfig(queue_completion="standby", poll_interval=10.0)
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            poll_interval=0.25,
            sleep_fn=fake_sleep,
            max_standby_iterations=1,
        )
    )

    assert exit_code == 0
    assert recorded_sleeps == [0.25]


# --- T041: Completion Summary and Exit Code Contract ---

def test_run_lifecycle_prints_completion_summary_on_terminate(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    t1 = _make_ticket("T001", title="Approved Ticket")
    t2 = _make_ticket("T002", title="Skipped Ticket")
    ticket_repo = FakeTicketRepository([t1, t2])
    printed: list[str] = []

    current_time = [100.0]

    def fake_clock() -> float:
        val = current_time[0]
        current_time[0] += 7.75
        return val

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        if ticket.id == "T001":
            return TicketOutcome.approved(changes=["change1"])
        return TicketOutcome.skipped(details="skipped reason")

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
        clock=fake_clock,
    )

    exit_code = asyncio.run(
        orchestrator.run_lifecycle(lifecycle="terminate", printer=printed.append, clock=fake_clock)
    )

    assert exit_code == 0
    # Assert summary elements
    assert any("Completion Summary" in p for p in printed)
    assert any("2 (1 approved, 1 skipped, 0 aborted)" in p for p in printed)
    assert any("aaaaaaa" in p for p in printed)
    assert any("agent/ticket-runner" in p for p in printed)
    assert any("Elapsed time:" in p for p in printed)
    assert len(orchestrator.lifecycle_outcomes) == 2


def test_run_lifecycle_preserves_outcomes_across_standby_drain_and_resume(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    fake_runner: FakeCommandRunner,
) -> None:
    t1 = _make_ticket("T001", title="Initial Ticket")
    ticket_repo = FakeTicketRepository([t1])
    printed: list[str] = []
    stop_event = asyncio.Event()

    fake_runner.register(["git", "commit", "-m"], stdout="")
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="b" * 40 + "\n")

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        if ticket.id == "T003":
            stop_event.set()
            return TicketOutcome.skipped(details="Skipped T003")
        return TicketOutcome.approved(changes=[f"Change {ticket.id}"])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    async def scenario() -> int:
        async def add_tickets_later() -> None:
            await asyncio.sleep(0.02)
            ticket_repo.add_ticket(_make_ticket("T002", title="Second Ticket"))
            ticket_repo.add_ticket(_make_ticket("T003", title="Third Ticket"))

        add_task = asyncio.create_task(add_tickets_later())
        run_task = asyncio.create_task(
            orchestrator.run_lifecycle(
                lifecycle="standby",
                poll_interval=0.01,
                printer=printed.append,
                stop_event=stop_event,
            )
        )
        await add_task
        return await run_task

    exit_code = asyncio.run(scenario())
    assert exit_code == 0
    assert len(orchestrator.lifecycle_outcomes) == 3
    assert orchestrator.lifecycle_outcomes[0].is_approved
    assert orchestrator.lifecycle_outcomes[1].is_approved
    assert orchestrator.lifecycle_outcomes[2].is_skipped

    assert any("Completion Summary" in p for p in printed)
    assert any("3 (2 approved, 1 skipped, 0 aborted)" in p for p in printed)
    assert any("bbbbbbb" in p for p in printed)


def test_run_lifecycle_keyboard_interrupt_prints_summary_and_returns_130(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    t1 = _make_ticket("T001", title="Interrupted Ticket")
    ticket_repo = FakeTicketRepository([t1])
    printed: list[str] = []

    async def interrupt_processor(ticket: Ticket) -> TicketOutcome:
        raise KeyboardInterrupt()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=interrupt_processor,
    )

    exit_code = asyncio.run(
        orchestrator.run_lifecycle(lifecycle="terminate", printer=printed.append)
    )

    assert exit_code == 130
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False
    assert any("Completion Summary" in p for p in printed)


def test_run_lifecycle_runtime_error_returns_1(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    t1 = _make_ticket("T001", title="Failing Ticket")
    ticket_repo = FakeTicketRepository([t1])
    printed: list[str] = []

    async def failing_processor(ticket: Ticket) -> TicketOutcome:
        raise RuntimeError("Unexpected pipeline failure during execution")

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=failing_processor,
    )

    exit_code = asyncio.run(
        orchestrator.run_lifecycle(lifecycle="terminate", printer=printed.append)
    )

    assert exit_code == 1
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False
    assert any("Runtime error" in p for p in printed)


# --- T042: Defer Interactive Clean-Slate Prompt Until Exit ---

def test_run_lifecycle_standby_interactive_defers_prompt_until_exit(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    ticket_file = spec_dir / "T001-test.md"
    ticket_file.write_text("# T001 — Test\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-test.md", path=ticket_file)
    ticket_repo = FakeTicketRepository([t1])

    printed: list[str] = []
    actions: list[str] = []
    lock_state_at_prompt: list[bool] = []
    stop_event = asyncio.Event()

    def recording_printer(msg: str) -> None:
        if "Completion Summary" in msg:
            actions.append("summary")
        printed.append(msg)

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            lock_state_at_prompt.append(queue_lock.is_locked)
            actions.append(f"clean_slate:{spec_slug}:{policy}")
            return True

    async def fake_sleep(duration: float) -> None:
        # Standby is active and polling; trigger stop
        assert actions == []
        assert any("standing by watching docs/tickets/" in p.lower() for p in printed)
        stop_event.set()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="standby", clean_slate="interactive")
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
            sleep_fn=fake_sleep,
            stop_event=stop_event,
        )
    )

    assert exit_code == 0
    # Clean slate was called only once at exit, before summary, and with lock released
    assert actions == ["clean_slate:02-test:interactive", "summary"]
    assert lock_state_at_prompt == [False]
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_standby_interactive_sigint_fires_prompt_before_summary(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    ticket_file = spec_dir / "T001-test.md"
    ticket_file.write_text("# T001 — Test\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-test.md", path=ticket_file)
    ticket_repo = FakeTicketRepository([t1])

    printed: list[str] = []
    actions: list[str] = []
    lock_state_at_prompt: list[bool] = []

    def recording_printer(msg: str) -> None:
        if "Completion Summary" in msg:
            actions.append("summary")
        printed.append(msg)

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            lock_state_at_prompt.append(queue_lock.is_locked)
            actions.append(f"clean_slate:{spec_slug}:{policy}")
            return True

    async def fake_sleep(duration: float) -> None:
        # Simulate SIGINT during standby polling
        assert actions == []
        raise KeyboardInterrupt()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="standby", clean_slate="interactive")
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
            sleep_fn=fake_sleep,
        )
    )

    assert exit_code == 130
    assert actions == ["clean_slate:02-test:interactive", "summary"]
    assert lock_state_at_prompt == [False]
    assert orchestrator.is_locked is False
    assert queue_lock.is_locked is False


def test_run_lifecycle_standby_resume_cycle_does_not_prompt_mid_watch(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "T001-test.md").write_text("# T001 — Test\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-test.md", path=spec_dir / "T001-test.md")
    ticket_repo = FakeTicketRepository([t1])

    printed: list[str] = []
    actions: list[str] = []
    stop_event = asyncio.Event()
    sleep_count = 0

    def recording_printer(msg: str) -> None:
        if "Completion Summary" in msg:
            actions.append("summary")
        printed.append(msg)

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            actions.append(f"clean_slate:{spec_slug}:{policy}")
            return True

    async def fake_sleep(duration: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 1:
            # Add new ticket during standby watch
            t2_file = spec_dir / "T002-test.md"
            t2_file.write_text("# T002 — Test\nStatus: pending\n", encoding="utf-8")
            ticket_repo.add_ticket(_make_ticket("T002", spec_path="docs/specs/02-test.md", path=t2_file))
        elif sleep_count == 2:
            # After resume and second drain, stop standby
            stop_event.set()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="standby", clean_slate="interactive")
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
            sleep_fn=fake_sleep,
            stop_event=stop_event,
        )
    )

    assert exit_code == 0
    # No prompts mid-watch: exactly one clean_slate at exit, followed by summary
    assert actions == ["clean_slate:02-test:interactive", "summary"]
    banner_lines = [p for p in printed if "watching docs/tickets/" in p.lower()]
    assert len(banner_lines) == 2


def test_run_lifecycle_standby_always_archives_at_drain_and_not_on_exit(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "T001-test.md").write_text("# T001 — Test\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-test.md", path=spec_dir / "T001-test.md")
    ticket_repo = FakeTicketRepository([t1])

    actions: list[str] = []
    lock_state_at_archive: list[bool] = []
    stop_event = asyncio.Event()

    def recording_printer(msg: str) -> None:
        if "Completion Summary" in msg:
            actions.append("summary")

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            lock_state_at_archive.append(queue_lock.is_locked)
            actions.append(f"clean_slate:{spec_slug}:{policy}")
            return True

    async def fake_sleep(duration: float) -> None:
        # At this point, archival should have already happened at drain
        assert actions == ["clean_slate:02-test:always"]
        stop_event.set()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="standby", clean_slate="always")
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
            sleep_fn=fake_sleep,
            stop_event=stop_event,
        )
    )

    assert exit_code == 0
    # Archival occurred once at drain, not again at exit
    assert actions == ["clean_slate:02-test:always", "summary"]
    assert lock_state_at_archive == [False]


def test_run_lifecycle_standby_never_skips_entirely(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "T001-test.md").write_text("# T001 — Test\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-test.md", path=spec_dir / "T001-test.md")
    ticket_repo = FakeTicketRepository([t1])

    actions: list[str] = []
    stop_event = asyncio.Event()

    def recording_printer(msg: str) -> None:
        if "Completion Summary" in msg:
            actions.append("summary")

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            actions.append(f"clean_slate:{spec_slug}:{policy}")
            return True

    async def fake_sleep(duration: float) -> None:
        stop_event.set()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="standby", clean_slate="never")
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
            sleep_fn=fake_sleep,
            stop_event=stop_event,
        )
    )

    assert exit_code == 0
    assert actions == ["summary"]


def test_run_lifecycle_terminate_interactive_prompts_at_drain_with_lock_released(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
    temp_dir: Path,
) -> None:
    tickets_dir = temp_dir / "docs" / "tickets"
    spec_dir = tickets_dir / "02-test"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "T001-test.md").write_text("# T001 — Test\nStatus: pending\n", encoding="utf-8")

    t1 = _make_ticket("T001", spec_path="docs/specs/02-test.md", path=spec_dir / "T001-test.md")
    ticket_repo = FakeTicketRepository([t1])

    actions: list[str] = []
    lock_state_at_prompt: list[bool] = []

    def recording_printer(msg: str) -> None:
        if "Completion Summary" in msg:
            actions.append("summary")

    class FakeArchiver:
        async def clean_slate(self, spec_slug: str, policy: str, printer: Any = None) -> Any:
            lock_state_at_prompt.append(queue_lock.is_locked)
            actions.append(f"clean_slate:{spec_slug}:{policy}")
            return True

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        tickets_dir=tickets_dir,
        clean_slate_archiver=FakeArchiver(),  # type: ignore[arg-type]
        processor=lambda t: asyncio.sleep(0.001, result=TicketOutcome.approved()),
    )

    config = LifecycleConfig(queue_completion="terminate", clean_slate="interactive")
    exit_code = asyncio.run(
        orchestrator.run_lifecycle(
            lifecycle=config,
            printer=recording_printer,
        )
    )

    assert exit_code == 0
    assert actions == ["clean_slate:02-test:interactive", "summary"]
    assert lock_state_at_prompt == [False]


# --- StateCoordinator Integration Tests ---


class _InMemoryStateStore:
    def __init__(self) -> None:
        self.doc: dict[str, Any] | None = None

    def read(self) -> dict[str, Any] | None:
        return dict(self.doc) if self.doc is not None else None

    def write(self, document: Any) -> None:
        self.doc = dict(document)


def test_queue_orchestrator_state_transitions(
    git_ops: GitOperations,
    queue_lock: QueueFileLock,
    gotchas_store: GotchasStore,
) -> None:
    store = _InMemoryStateStore()
    coordinator = StateCoordinator(state_store=store, branch="agent/ticket-runner")  # type: ignore[arg-type]

    t1 = _make_ticket("T001")
    ticket_repo = FakeTicketRepository([t1])

    statuses_during_processor: list[StateStatus | None] = []

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        # Check status when beginning ticket: should be WORKING
        statuses_during_processor.append(
            coordinator.current_state.status if coordinator.current_state else None
        )
        # Transition to gatekeeper during verification
        orchestrator.transition_to_gatekeeper(attempts=1)
        statuses_during_processor.append(
            coordinator.current_state.status if coordinator.current_state else None
        )
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_repo,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        state_coordinator=coordinator,
        processor=fake_processor,
    )

    # 1. Run ticket: begins in WORKING, transitions to GATEKEEPER, drains to IDLE
    outcome = asyncio.run(orchestrator.run_next())
    assert outcome is not None
    assert outcome.is_approved
    assert statuses_during_processor == [StateStatus.WORKING, StateStatus.GATEKEEPER]

    # Queue is now drained, so state must be IDLE
    assert coordinator.current_state is not None
    assert coordinator.current_state.status == StateStatus.IDLE
    assert store.doc is not None
    assert store.doc["status"] == "IDLE"

    # 2. Pause transitions state to PAUSE_REQUESTED
    orchestrator.pause()
    assert coordinator.current_state.status == StateStatus.PAUSE_REQUESTED
    assert store.doc["status"] == "PAUSE_REQUESTED"




