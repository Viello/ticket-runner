"""Sentinel queue lock coordinator for exclusive directory-based execution."""

from __future__ import annotations

from pathlib import Path
import sys
from types import TracebackType
from typing import IO

from runner.domain.exceptions import QueueLockError

# Platform-specific OS file locking primitives
if sys.platform == "win32":
    import msvcrt
    fcntl = None
else:
    msvcrt = None
    try:
        import fcntl
    except ImportError:  # pragma: no cover
        fcntl = None

DEFAULT_LOCK_PATH = Path("docs/tickets/.queue.lock")


class QueueFileLock:
    """Manages an exclusive OS file lock on the queue sentinel file.

    Guarantees that only one Ticket Runner process executes against the queue
    directory at any given moment. External editors can modify queue files freely
    when the lock is released (such as during interactive pauses, user questions,
    or circuit breaker trips), and re-acquisition is supported upon resumption.
    """

    def __init__(self, lock_path: Path | str = DEFAULT_LOCK_PATH) -> None:
        """Initialize QueueFileLock with sentinel path.

        Args:
            lock_path: Path to sentinel lock file. Defaults to docs/tickets/.queue.lock.
        """
        self._lock_path = Path(lock_path)
        self._file: IO[bytes] | None = None
        self._is_locked: bool = False

    @property
    def lock_path(self) -> Path:
        """Sentinel lock file path."""
        return self._lock_path

    @property
    def is_locked(self) -> bool:
        """Return True if the lock is currently held, False otherwise."""
        return self._is_locked

    def _platform_lock(self, file_obj: IO[bytes]) -> None:
        """Acquire non-blocking OS lock on open binary file handle."""
        if sys.platform == "win32":
            file_obj.seek(0)
            # Lock byte 0 to 1 non-blocking
            msvcrt.locking(file_obj.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            if fcntl is None:
                raise QueueLockError("No supported OS file locking primitive available on this platform")
            fcntl.flock(file_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _platform_unlock(self, file_obj: IO[bytes]) -> None:
        """Release OS lock on open binary file handle."""
        if sys.platform == "win32":
            try:
                file_obj.seek(0)
                msvcrt.locking(file_obj.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            if fcntl is not None:
                try:
                    fcntl.flock(file_obj.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass

    def acquire(self) -> None:
        """Acquire exclusive non-blocking lock on sentinel file.

        Creates sentinel file on demand if missing without modifying its contents.

        Raises:
            QueueLockError: If the lock is already held by another process or this instance.
        """
        if self._is_locked:
            raise QueueLockError(f"Queue lock is already held by this instance: '{self._lock_path}'")

        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        file_obj = open(self._lock_path, "a+b")

        try:
            self._platform_lock(file_obj)
        except (BlockingIOError, PermissionError, OSError) as exc:
            file_obj.close()
            raise QueueLockError(
                f"Failed to acquire queue lock on '{self._lock_path}': "
                f"Lock is already held by another process."
            ) from exc
        except Exception:
            file_obj.close()
            raise

        self._file = file_obj
        self._is_locked = True

    def release(self) -> None:
        """Release exclusive lock and close handle so external editors can modify queue files."""
        if self._file is None:
            self._is_locked = False
            return

        file_obj = self._file
        self._file = None
        self._is_locked = False

        try:
            self._platform_unlock(file_obj)
        finally:
            file_obj.close()

    def __enter__(self) -> QueueFileLock:
        """Acquire lock upon entering context block."""
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Release lock upon exiting context block, even if an exception was raised."""
        self.release()

    def __del__(self) -> None:
        """Clean up lock handle on garbage collection."""
        try:
            self.release()
        except Exception:
            pass

    def __repr__(self) -> str:
        status = "locked" if self._is_locked else "unlocked"
        return f"QueueFileLock(path={self._lock_path!r}, status={status!r})"
