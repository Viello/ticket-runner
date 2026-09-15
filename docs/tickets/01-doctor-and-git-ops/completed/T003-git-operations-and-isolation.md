# T003 — Git operations adapter and working tree isolation interactor
Status: completed
Completed: 2026-09-15T13:57:00Z
Spec: docs/specs/01-doctor-and-git-ops.md

### Requirements
- Implement `GitClient` adapter in `runner/adapters/git/git_client.py` wrapping core git CLI commands through the injected `CommandRunner` port.
- Implement `GitOperations` interactor in `runner/application/git_operations.py` providing:
  - `check_clean_working_tree() -> bool`: Runs `git status --porcelain` and verifies the output is empty.
  - `ensure_branch(branch_name: str = "agent/ticket-runner") -> None`: Strictly checks tree cleanliness first, then checks active branch via `git symbolic-ref --short HEAD`. If not already on `branch_name`, checks out existing branch or creates it from current HEAD (`git checkout -b`).
  - `commit_ticket(scope: str, title: str, changes: list[str]) -> str`: Stages modified files (`git add .`), authors conventional commit (`<commit_prefix>(<scope>): <Title>\n\n- <change 1>\n- <change 2>...`), and extracts the 40-character commit SHA (`git rev-parse HEAD`). No ticket numbers appear in commit title or body.
  - `reset_working_tree() -> None`: Performs hard reset and clean (`git reset --hard HEAD` and `git clean -fd`) to return working tree to pristine state when skipping or aborting tickets.
- Jump-start:
  - Files to touch: `runner/adapters/git/git_client.py`, `runner/application/__init__.py`, `runner/application/git_operations.py`, `tests/unit/application/test_git_operations.py`.
  - Seams: Injected `CommandRunner` protocol.
  - Anchor patterns: ADR 0006 (`CommandRunner` seam) and Spec 01 §21-23.
  - Verification: `pytest tests/unit/application/test_git_operations.py`.

### Acceptance Criteria
- `check_clean_working_tree` returns True on clean tree, False when modified or untracked files are present.
- `ensure_branch` checks out or creates `agent/ticket-runner` without modifying `main`, enforcing clean tree check first.
- `commit_ticket` stages all files, creates structured conventional commit (`<type>(<scope>): <Title>` with bulleted changes and no ticket numbers), and returns the full commit SHA.
- `reset_working_tree` triggers both `git reset --hard` and `git clean -fd`.
- All operations are thoroughly tested using `FakeCommandRunner` without invoking real git binaries.

### Gotchas
- `git status --porcelain` includes untracked files with prefix `??`. Ensure runtime directories (like `.agent/`) are git-ignored so temporary runtime state does not trigger false dirty-tree failures.
