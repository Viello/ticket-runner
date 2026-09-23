# T097 — External Project Root Plumbing in Container and Storage Adapters
Status: pending
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
Blocked by: T094
Security: required
Reasoning: medium

### Requirements
- Update `build_container()` in `runner/container.py` to accept `project_dir: Path | None = None` (defaulting to current working directory).
- Route `project_dir` to:
  - `RuntimePaths(root_dir=project_dir / ".agent")`
  - `DirectoryTicketStore(root_dir=project_dir / "docs" / "tickets")`
  - `GotchasStore(path=project_dir / "docs" / "tickets" / "gotchas.md")`
  - `QueueFileLock(lock_path=project_dir / "docs" / "tickets" / ".queue.lock")`
  - `GitOperations(cwd=project_dir)`
  - `GatekeeperCommandExecutor(cwd=project_dir)`
  - `WorkerSupervisor(cwd=project_dir)`
- Ensure `RuntimePaths` and all storage adapters resolve paths accurately when provided an external directory path.
- Update `ARCHITECTURE.md` component diagrams and docstrings clarifying external directory resolution across storage adapters and composition root.
- Jump-start:
  - Files to touch: `runner/container.py`, `runner/domain/runtime_paths.py`, `runner/adapters/markdown/ticket_store.py`, `ARCHITECTURE.md`, `tests/unit/domain/test_runtime_paths.py`, `tests/unit/container/test_container.py`.
  - Seams: `build_container(project_dir=...)`, `RuntimePaths(root_dir=...)`.
  - Verification: `pytest tests/unit/domain/test_runtime_paths.py tests/unit/container/test_container.py`.

### Acceptance Criteria
- `build_container(project_dir=Path("/custom/project"))` configures all runtime paths, ticket queues, locks, gotchas, git operations, and gatekeeper executors relative to `/custom/project`.
- When `project_dir` is omitted, behavior is strictly backwards-compatible with current working directory.
- `ARCHITECTURE.md` documents `--project-dir` resolution in the composition root.
- Security verification: `RuntimePaths` prevents path traversal outside the designated `.agent` directory tree.

### Smoke Scenarios
**Scenario: Container External Path Resolution**
- Setup: A temporary directory outside the repository representing a target project.
- Why: Ensure `build_container` routes all runtime signals, locks, gotchas, and ticket queries to the target directory without touching the runner's workspace.
- Steps:
  1. Run PowerShell verification script creating a temporary directory structure and instantiating `build_container(project_dir=temp_dir)`:
     ```powershell
     python -c @"
     import tempfile
     from pathlib import Path
     from runner.container import build_container
     with tempfile.TemporaryDirectory() as tmp:
         target = Path(tmp).resolve()
         container = build_container(project_dir=target)
         assert container.runtime_paths.root_dir == target / '.agent'
         assert container.ticket_store.root_dir == target / 'docs' / 'tickets'
         assert container.gotchas_store.path == target / 'docs' / 'tickets' / 'gotchas.md'
         assert container.lock.lock_path == target / 'docs' / 'tickets' / '.queue.lock'
         print('PASS: Container resolves all paths relative to external project_dir.')
     "@
     ```
  2. Run `pytest tests/unit/domain/test_runtime_paths.py tests/unit/container/test_container.py`.
- Expected: All components resolve inside `temp_dir`, zero files created in runner workspace, tests pass with exit code 0.

### Gotchas
- Ensure both relative and absolute paths passed as `project_dir` are resolved via `.resolve()` to avoid ambiguity during subprocess cwd changes.
