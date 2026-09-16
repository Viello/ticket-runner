# T015 — Runtime paths value object and git inspection commands
Status: pending
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add `runner/domain/runtime_paths.py`: a frozen value object resolving `.agent/` artifact paths — ready signal, question file, Checkpoint (`.agent/checkpoints/{ticket_id}/handoff.md`), and session logs (`.agent/logs/{ticket_id}_session_{session_id}.jsonl` plus stderr sidecar) — with directory-creation helpers for callers. Pure path computation, no process or network I/O; Specs 04–06 will extend it.
- Extend `GitOperations` (backed by `GitClient`) with `status_porcelain() -> str` and `diff_stat() -> str`; `GitClient.status_porcelain` already exists, add `git diff --stat` alongside it.
- Jump-start:
  - Files to touch: `runner/domain/runtime_paths.py`, `runner/adapters/git/git_client.py`, `runner/application/git_operations.py`, `tests/unit/domain/test_runtime_paths.py`, `tests/unit/application/test_git_operations.py`.
  - Seams: `GitOperations` constructor takes a `CommandRunner` or `GitClient`; existing `DEFAULT_*` path constants in `queue_orchestrator.py`, `file_lock.py`, `gotchas_store.py`, `clean_slate.py` show the convention to consolidate around.
  - Anchor patterns: `tests/unit/application/test_git_operations.py` asserts recorded git invocations through `FakeCommandRunner`.
  - Verification: `pytest tests/unit/domain/test_runtime_paths.py tests/unit/application/test_git_operations.py`.

### Acceptance Criteria
- All `.agent/` paths resolve exactly as specified; callers can create missing parent directories on demand; no call site needs string concatenation of runtime paths.
- `status_porcelain` and `diff_stat` return command stdout and are asserted as `git status --porcelain` and `git diff --stat` invocations through `FakeCommandRunner`.
- Unit tests for the value object assert ticket/session values are embedded only through the object and cover the empty-path edge.

### Gotchas
- `.agent/` is already git-ignored — add no new ignore rules and write nothing to disk at import time.
- Keep the object free of behavior beyond path resolution and directory creation; state persistence (`state.json`) is Spec 06's extension.
- The emergency synthesis consumer (T022) relies on `diff_stat` failing loudly via `GitError` when git errors — do not swallow errors.
