"""Unit tests for QueueFileLock and sentinel queue coordinator."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest

from runner.adapters.markdown.file_lock import DEFAULT_LOCK_PATH, QueueFileLock
from runner.domain.exceptions import QueueLockError, TicketRunnerError


def test_queue_lock_error_inherits_ticket_runner_error() -> None:
    """Verify QueueLockError inherits from TicketRunnerError."""
    assert issubclass(QueueLockError, TicketRunnerError)
    err = QueueLockError("Failed to lock")
    assert "Failed to lock" in str(err)


def test_sentinel_file_created_on_demand_and_remains_empty(tmp_path: Path) -> None:
    """Verify sentinel lock file is created on demand if missing and remains 0 bytes."""
    lock_file = tmp_path / "docs" / "tickets" / ".queue.lock"
    assert not lock_file.exists()

    lock = QueueFileLock(lock_path=lock_file)
    assert not lock.is_locked
    assert lock.lock_path == lock_file

    lock.acquire()
    try:
        assert lock.is_locked
        assert lock_file.is_file()
        assert lock_file.stat().st_size == 0
    finally:
        lock.release()

    assert not lock.is_locked
    assert lock_file.stat().st_size == 0


def test_lock_acquire_and_release(tmp_path: Path) -> None:
    """Verify acquiring sets state and releasing frees resources."""
    lock_file = tmp_path / ".queue.lock"
    lock = QueueFileLock(lock_path=lock_file)

    assert not lock.is_locked
    lock.acquire()
    assert lock.is_locked

    lock.release()
    assert not lock.is_locked


def test_reacquisition_after_release(tmp_path: Path) -> None:
    """Verify re-acquiring works after release on same or different instances."""
    lock_file = tmp_path / ".queue.lock"
    lock1 = QueueFileLock(lock_path=lock_file)

    # First acquisition
    lock1.acquire()
    assert lock1.is_locked
    lock1.release()
    assert not lock1.is_locked

    # Same instance re-acquisition
    lock1.acquire()
    assert lock1.is_locked
    lock1.release()
    assert not lock1.is_locked

    # Different instance acquisition
    lock2 = QueueFileLock(lock_path=lock_file)
    lock2.acquire()
    assert lock2.is_locked
    lock2.release()
    assert not lock2.is_locked


def test_conflict_fails_fast_with_queue_lock_error(tmp_path: Path) -> None:
    """Verify second lock instance fails fast with QueueLockError when lock is held."""
    lock_file = tmp_path / ".queue.lock"
    lock1 = QueueFileLock(lock_path=lock_file)
    lock2 = QueueFileLock(lock_path=lock_file)

    lock1.acquire()
    try:
        with pytest.raises(QueueLockError) as exc_info:
            lock2.acquire()

        assert "already held" in str(exc_info.value).lower() or "failed to acquire" in str(exc_info.value).lower()
        assert str(lock_file) in str(exc_info.value)
        assert not lock2.is_locked
    finally:
        lock1.release()

    # Now lock2 can acquire successfully
    lock2.acquire()
    assert lock2.is_locked
    lock2.release()


def test_second_instance_closes_handle_on_conflict(tmp_path: Path) -> None:
    """Verify failed acquisition closes its handle so no leaked descriptors remain."""
    lock_file = tmp_path / ".queue.lock"
    lock1 = QueueFileLock(lock_path=lock_file)
    lock2 = QueueFileLock(lock_path=lock_file)

    lock1.acquire()
    try:
        with pytest.raises(QueueLockError):
            lock2.acquire()
        # Internal handle must be None on failed acquire
        assert lock2._file is None
        assert not lock2.is_locked
    finally:
        lock1.release()


def test_calling_acquire_when_already_locked_raises(tmp_path: Path) -> None:
    """Verify calling acquire() twice on the same instance raises QueueLockError."""
    lock_file = tmp_path / ".queue.lock"
    lock = QueueFileLock(lock_path=lock_file)

    lock.acquire()
    try:
        with pytest.raises(QueueLockError, match="already"):
            lock.acquire()
    finally:
        lock.release()


def test_release_when_not_locked_is_idempotent(tmp_path: Path) -> None:
    """Verify calling release() without acquiring is safe and idempotent."""
    lock_file = tmp_path / ".queue.lock"
    lock = QueueFileLock(lock_path=lock_file)
    # Calling release when not locked should not raise
    lock.release()
    lock.release()
    assert not lock.is_locked


def test_context_manager_acquires_and_releases(tmp_path: Path) -> None:
    """Verify context manager automatically acquires on enter and releases on exit."""
    lock_file = tmp_path / ".queue.lock"
    lock = QueueFileLock(lock_path=lock_file)

    with lock as ctx:
        assert ctx is lock
        assert lock.is_locked
        # Inside context, second lock should conflict
        lock2 = QueueFileLock(lock_path=lock_file)
        with pytest.raises(QueueLockError):
            lock2.acquire()

    assert not lock.is_locked

    # After exit, lock2 can acquire
    lock2 = QueueFileLock(lock_path=lock_file)
    lock2.acquire()
    assert lock2.is_locked
    lock2.release()


def test_context_manager_releases_on_exception(tmp_path: Path) -> None:
    """Verify context manager releases the lock even when the body raises an exception."""
    lock_file = tmp_path / ".queue.lock"
    lock = QueueFileLock(lock_path=lock_file)

    with pytest.raises(RuntimeError, match="deliberate failure"):
        with lock:
            assert lock.is_locked
            raise RuntimeError("deliberate failure")

    assert not lock.is_locked

    # Verify lock can immediately be re-acquired
    lock2 = QueueFileLock(lock_path=lock_file)
    lock2.acquire()
    assert lock2.is_locked
    lock2.release()


def test_default_lock_path() -> None:
    """Verify default lock path points to docs/tickets/.queue.lock."""
    lock = QueueFileLock()
    assert lock.lock_path == DEFAULT_LOCK_PATH
    assert lock.lock_path == Path("docs/tickets/.queue.lock")


def test_posix_branch_mocking(tmp_path: Path) -> None:
    """Verify POSIX locking branch calls fcntl.flock properly."""
    lock_file = tmp_path / ".queue.lock"
    mock_fcntl = MagicMock()

    with patch("runner.adapters.markdown.file_lock.sys.platform", "linux"):
        with patch("runner.adapters.markdown.file_lock.fcntl", mock_fcntl):
            lock = QueueFileLock(lock_path=lock_file)
            lock.acquire()
            assert lock.is_locked
            assert mock_fcntl.flock.called

            lock.release()
            assert not lock.is_locked


def test_posix_conflict_raises_queue_lock_error(tmp_path: Path) -> None:
    """Verify POSIX BlockingIOError on flock translates to QueueLockError."""
    lock_file = tmp_path / ".queue.lock"
    mock_fcntl = MagicMock()
    mock_fcntl.flock.side_effect = BlockingIOError(11, "Resource temporarily unavailable")

    with patch("runner.adapters.markdown.file_lock.sys.platform", "linux"):
        with patch("runner.adapters.markdown.file_lock.fcntl", mock_fcntl):
            lock = QueueFileLock(lock_path=lock_file)
            with pytest.raises(QueueLockError, match="already held"):
                lock.acquire()
            assert not lock.is_locked
            assert lock._file is None


def test_git_status_porcelain_clean_with_sentinel_lock(tmp_path: Path) -> None:
    """Verify sentinel lock file does not appear in git status with proper .gitignore."""
    # Set up an isolated git repository in tmp_path
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=tmp_path, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    # Write .gitignore with the same patterns as the real repo
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text(".queue.lock\n**/.queue.lock\n")

    # Create initial commit so git status works
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path, capture_output=True, check=True,
    )

    # Create and acquire the sentinel lock inside the tmp repo
    lock_dir = tmp_path / "docs" / "tickets"
    lock_dir.mkdir(parents=True)
    lock_path = lock_dir / ".queue.lock"

    lock = QueueFileLock(lock_path=lock_path)
    lock.acquire()
    try:
        status_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        # .queue.lock must NOT appear in git status --porcelain
        assert ".queue.lock" not in status_proc.stdout
    finally:
        lock.release()

