# T008 — Sentinel queue lock coordinator
Status: completed
Completed: 2026-09-16T06:05:00Z
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Implement `QueueFileLock` in `runner/adapters/markdown/file_lock.py` managing an exclusive OS file lock on the sentinel `docs/tickets/.queue.lock` while a ticket executes (user story 2).
- Acquire the lock using platform-specific primitives: non-blocking `msvcrt.locking` on Windows and an `fcntl.flock` fallback on POSIX (ADR 0007/0010).
- Provide `acquire()`, `release()`, and context-manager support; releasing closes the lock handle so external editors can modify queue files freely once the Runner pauses, answers a question, or trips the Circuit Breaker (user story 3); re-acquiring works after release so the Runner can resume, re-scan, and continue (user story 4).
- Fail fast with a descriptive `QueueLockError` (inheriting `TicketRunnerError`) when the lock is already held by another process; never block indefinitely.
- Ensure the sentinel file is created when missing and can never dirty the git tree or be staged by `git add .`: add `docs/tickets/.queue.lock` and pending-write temp patterns to root `.gitignore`.
- Jump-start:
  - Files to touch: `runner/adapters/markdown/file_lock.py`, `runner/domain/exceptions.py`, `.gitignore`, `tests/unit/adapters/test_file_lock.py`.
  - Seams: `runner/adapters/markdown/file_lock.py:QueueFileLock` (`acquire`, `release`, `__enter__`, `__exit__`).
  - Anchor patterns: ADR 0007 pause-release semantics and ADR 0010 sentinel lock decision; platform-branching style in `runner/adapters/cli/subprocess_runner.py`.
  - Verification: `pytest tests/unit/adapters/test_file_lock.py`.

### Acceptance Criteria
- A second `QueueFileLock` instance on the same sentinel path fails fast with a clear conflict error while the first holds the lock.
- `release()` frees the lock and allows immediate re-acquisition by the same or another instance.
- The context manager releases the lock even when its body raises.
- The sentinel file is created on demand at `docs/tickets/.queue.lock` and remains empty.
- Locking uses `msvcrt` on Windows and a POSIX fallback elsewhere; tests exercise the real filesystem and skip gracefully where a primitive is unavailable.
- `.gitignore` contains entries for the sentinel lock and ticket temp files, and a `git status --porcelain` check confirms a held or released lock never shows as a change.

### Gotchas
- `msvcrt.locking` locks a byte range starting at the current file position; seek to 0 and lock a fixed 1-byte range, and open the file in a mode that permits locking (`a+b`/`r+b` after creation).
- On Windows an open handle can block deletion/replacement of the lock file; always close handles on release and in test teardown.
- `fcntl` is unavailable on Windows — import it lazily inside the POSIX branch so module import never fails.
- Without the `.gitignore` entry, the Gatekeeper's `git add .` would commit the sentinel and Doctor's clean-tree check could fail mid-run.
