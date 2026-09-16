"""Unit tests for QueueOrchestrator interactor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.markdown.file_lock import QueueFileLock
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.application.git_operations import GitOperations
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
    TicketOutcomeStatus,
)
from runner.domain.config import LifecycleConfig
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

    with pytest.raises(RuntimeError, match="No ticket processor configured. Worker execution will arrive in Spec 03."):
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

    with pytest.raises(RuntimeError, match="No ticket processor configured. Worker execution will arrive in Spec 03."):
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
