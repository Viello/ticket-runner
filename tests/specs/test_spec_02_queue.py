"""Spec 02 Behavioral Test Suite: Directory-Based Ticket Queue and Gotchas Management.

Validates all relevant User Stories from docs/specs/02-queue-and-tickets.md:
  US 01: Individual ticket markdown files under docs/tickets/<spec-slug>/T<NNN>-<slug>.md
  US 02: Exclusive OS sentinel file lock (.queue.lock) held during active execution
  US 03: Sentinel lock released on pause to allow external text editor modifications
  US 04: Sentinel lock re-acquired and queue re-scanned on resume, picking up new tickets
  US 05: Strict sequential execution ordered by numeric ticket identifier
  US 07: Relocation of completed ticket to completed/ subfolder
  US 08: Completion timestamp header stamping and single atomic feature commit (ADR 0012)
  US 09: Global gotchas aggregation into docs/tickets/gotchas.md
  US 10: Skipped ticket working tree reset and relocation with failure details, no commit
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from runner.adapters.markdown.file_lock import QueueFileLock
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.git_operations import GitOperations
from runner.application.queue_orchestrator import (
    QueueOrchestrator,
    TicketOutcome,
)
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner


def _create_ticket_file(
    queue_dir: Path,
    spec_slug: str,
    ticket_filename: str,
    title: str,
    status: str = "pending",
    requirements: list[str] | None = None,
) -> Path:
    spec_folder = queue_dir / spec_slug
    spec_folder.mkdir(parents=True, exist_ok=True)
    ticket_path = spec_folder / ticket_filename

    req_lines = "\n".join(f"- {r}" for r in (requirements or ["Initial requirement"]))
    content = (
        f"# {title}\n"
        f"Status: {status}\n"
        f"Spec: docs/specs/{spec_slug}.md\n\n"
        f"### Requirements\n"
        f"{req_lines}\n\n"
        f"### Acceptance Criteria\n"
        f"- Criteria 1\n\n"
        f"### Gotchas\n"
    )
    with ticket_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return ticket_path


@pytest.fixture
def fake_runner() -> FakeCommandRunner:
    runner = FakeCommandRunner()
    runner.register(["git", "status", "--porcelain"], stdout="")
    runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    runner.register(["git", "add", "."], stdout="")
    runner.register(["git", "commit", "-m"], stdout="")
    runner.register(["git", "rev-parse", "HEAD"], stdout="f" * 40 + "\n")
    runner.register(["git", "reset", "--hard", "HEAD"], stdout="HEAD is now at fffffff\n")
    runner.register(["git", "clean", "-fd"], stdout="")
    return runner


@pytest.fixture
def workspace_tree(tmp_path: Path) -> dict[str, Path]:
    tickets_dir = tmp_path / "docs" / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    lock_path = tickets_dir / ".queue.lock"
    gotchas_path = tickets_dir / "gotchas.md"
    return {
        "root": tmp_path,
        "tickets": tickets_dir,
        "lock": lock_path,
        "gotchas": gotchas_path,
    }


# --- US 02 & US 05: Sentinel Lock Held During Active Run & Strict Sequential Ordering ---

def test_spec_02_us_02_and_05_sequential_execution_and_sentinel_lock(
    workspace_tree: dict[str, Path],
    fake_runner: FakeCommandRunner,
) -> None:
    tickets_dir = workspace_tree["tickets"]
    lock_path = workspace_tree["lock"]
    gotchas_path = workspace_tree["gotchas"]

    # Scaffold out-of-order tickets under 01-auth
    _create_ticket_file(tickets_dir, "01-auth", "T003-logout.md", "T003 — Logout Flow")
    _create_ticket_file(tickets_dir, "01-auth", "T001-setup.md", "T001 — Setup Auth")
    _create_ticket_file(tickets_dir, "01-auth", "T002-login.md", "T002 — Login Form")

    ticket_store = DirectoryTicketStore(root_dir=tickets_dir)
    queue_lock = QueueFileLock(lock_path=lock_path)
    gotchas_store = GotchasStore(path=gotchas_path)
    git_ops = GitOperations(runner=fake_runner)

    execution_history: list[tuple[str, str, bool]] = []

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        # Record ticket ID, event, and lock status during processing
        execution_history.append((ticket.id, "start", queue_lock.is_locked))
        await asyncio.sleep(0.01)
        execution_history.append((ticket.id, "finish", queue_lock.is_locked))
        return TicketOutcome.approved(changes=[f"Complete {ticket.id}"])

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_store,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    assert queue_lock.is_locked is False

    outcomes = asyncio.run(orchestrator.run_all())

    assert len(outcomes) == 3
    # Verify strict sequential order: T001 starts and finishes before T002 starts
    order_of_events = [(item[0], item[1]) for item in execution_history]
    assert order_of_events == [
        ("T001", "start"),
        ("T001", "finish"),
        ("T002", "start"),
        ("T002", "finish"),
        ("T003", "start"),
        ("T003", "finish"),
    ]

    # Verify sentinel lock was held during all active executions
    for ticket_id, event, is_locked in execution_history:
        assert is_locked is True, f"Lock was not held during {event} of {ticket_id}"

    # After queue drains, lock is released
    assert queue_lock.is_locked is False


# --- US 03 & US 04: Lock Released on Pause, Re-acquired on Resume, Picking Up Inserted Tickets ---

def test_spec_02_us_03_and_04_pause_release_and_resume_rescan(
    workspace_tree: dict[str, Path],
    fake_runner: FakeCommandRunner,
) -> None:
    tickets_dir = workspace_tree["tickets"]
    lock_path = workspace_tree["lock"]
    gotchas_path = workspace_tree["gotchas"]

    # Initial pending ticket: T002
    _create_ticket_file(tickets_dir, "02-feature", "T002-feature.md", "T002 — Feature Work")

    ticket_store = DirectoryTicketStore(root_dir=tickets_dir)
    queue_lock = QueueFileLock(lock_path=lock_path)
    gotchas_store = GotchasStore(path=gotchas_path)
    git_ops = GitOperations(runner=fake_runner)

    executed_tickets: list[str] = []

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        executed_tickets.append(ticket.id)
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_store,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    # US 03: Pause releases lock handle so external text editor can write
    orchestrator.pause()
    assert orchestrator.is_paused is True
    assert queue_lock.is_locked is False

    # External author creates T001 while paused
    _create_ticket_file(tickets_dir, "02-feature", "T001-hotfix.md", "T001 — Urgent Hotfix")

    # US 04: Resume re-acquires lock and re-scans directory
    orchestrator.resume()
    assert orchestrator.is_paused is False
    assert queue_lock.is_locked is True

    # Execute next ticket: should pick up T001 first
    outcome = asyncio.run(orchestrator.run_next())
    assert outcome is not None
    assert executed_tickets == ["T001"]

    # Execute remaining ticket: T002
    outcome_2 = asyncio.run(orchestrator.run_next())
    assert outcome_2 is not None
    assert executed_tickets == ["T001", "T002"]

    # Queue drained -> lock released
    assert queue_lock.is_locked is False


# --- US 07, US 08, US 09: Atomic Commit, Relocation to completed/, and Gotchas Aggregation ---

def test_spec_02_us_07_08_09_atomic_commit_relocation_and_gotchas(
    workspace_tree: dict[str, Path],
    fake_runner: FakeCommandRunner,
) -> None:
    tickets_dir = workspace_tree["tickets"]
    lock_path = workspace_tree["lock"]
    gotchas_path = workspace_tree["gotchas"]

    ticket_file = _create_ticket_file(
        tickets_dir,
        "03-billing",
        "T001-checkout.md",
        "T001 — Implement Checkout",
    )

    ticket_store = DirectoryTicketStore(root_dir=tickets_dir)
    queue_lock = QueueFileLock(lock_path=lock_path)
    gotchas_store = GotchasStore(path=gotchas_path)
    git_ops = GitOperations(runner=fake_runner)

    new_gotcha = "Stripe webhook events require idempotency key validation"

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        return TicketOutcome.approved(
            new_gotchas=[new_gotcha],
            changes=["Implement checkout API route", "Add stripe webhook handler"],
            scope="billing",
        )

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_store,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_approved is True
    assert outcome.commit_sha == "f" * 40

    # US 07 & US 08: Original ticket file is moved to completed/ with timestamp stamped
    assert not ticket_file.exists()
    relocated_file = tickets_dir / "03-billing" / "completed" / "T001-checkout.md"
    assert relocated_file.is_file()

    relocated_content = relocated_file.read_text(encoding="utf-8")
    assert "Status: completed" in relocated_content
    assert "Completed: 20" in relocated_content
    # ADR 0012: Never record commit SHA in ticket frontmatter
    assert "Commit:" not in relocated_content

    # US 09: Global gotchas appended to docs/tickets/gotchas.md
    gotchas_content = gotchas_store.load()
    assert "Stripe webhook events" in gotchas_content
    assert new_gotcha in gotchas_content

    # US 08: Exactly one conventional commit authored combining everything
    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 1
    commit_msg = commit_invocations[0].cmd[3]
    assert commit_msg.startswith("feat(billing): Implement Checkout")
    assert "- Implement checkout API route" in commit_msg
    assert "- Add stripe webhook handler" in commit_msg
    assert "T001" not in commit_msg


# --- US 10: Skipped Ticket Working Tree Reset and Relocation Without Commit ---

def test_spec_02_us_10_skipped_ticket_resets_working_tree_and_no_commit(
    workspace_tree: dict[str, Path],
    fake_runner: FakeCommandRunner,
) -> None:
    tickets_dir = workspace_tree["tickets"]
    lock_path = workspace_tree["lock"]
    gotchas_path = workspace_tree["gotchas"]

    ticket_file = _create_ticket_file(
        tickets_dir,
        "04-search",
        "T005-fuzzy.md",
        "T005 — Fuzzy Search Indexing",
    )

    ticket_store = DirectoryTicketStore(root_dir=tickets_dir)
    queue_lock = QueueFileLock(lock_path=lock_path)
    gotchas_store = GotchasStore(path=gotchas_path)
    git_ops = GitOperations(runner=fake_runner)

    failure_reason = "Circuit breaker tripped after 3 failed test attempts"

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        return TicketOutcome.skipped(details=failure_reason)

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_store,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    outcome = asyncio.run(orchestrator.run_next())

    assert outcome is not None
    assert outcome.is_skipped is True

    # Working tree was reset
    assert ["git", "reset", "--hard", "HEAD"] in fake_runner.commands
    assert ["git", "clean", "-fd"] in fake_runner.commands

    # Ticket relocated to completed with skipped status
    assert not ticket_file.exists()
    relocated_file = tickets_dir / "04-search" / "completed" / "T005-fuzzy.md"
    assert relocated_file.is_file()

    relocated_content = relocated_file.read_text(encoding="utf-8")
    assert "Status: skipped" in relocated_content
    assert "Failure: Circuit breaker tripped after 3 failed test attempts" in relocated_content

    # Zero commits authored
    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 0


# --- Empty Queue Behavior ---

def test_spec_02_empty_queue_returns_none(
    workspace_tree: dict[str, Path],
    fake_runner: FakeCommandRunner,
) -> None:
    tickets_dir = workspace_tree["tickets"]
    lock_path = workspace_tree["lock"]
    gotchas_path = workspace_tree["gotchas"]

    ticket_store = DirectoryTicketStore(root_dir=tickets_dir)
    queue_lock = QueueFileLock(lock_path=lock_path)
    gotchas_store = GotchasStore(path=gotchas_path)
    git_ops = GitOperations(runner=fake_runner)

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        return TicketOutcome.approved()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_store,
        lock=queue_lock,
        gotchas_store=gotchas_store,
        git_operations=git_ops,
        processor=fake_processor,
    )

    outcome = asyncio.run(orchestrator.run_next())
    assert outcome is None
    assert queue_lock.is_locked is False
