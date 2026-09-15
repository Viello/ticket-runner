# T005 — Doctor pre-flight verification coordinator and CLI entry point
Status: completed
Completed: 2026-09-15T16:01:00Z
Spec: docs/specs/01-doctor-and-git-ops.md

### Requirements
- Implement `Doctor` interactor in `runner/application/doctor.py` returning strongly-typed `DoctorReport(passed: bool, checks: list[CheckResult])`, where each `CheckResult` contains `name: str`, `passed: bool`, `message: str`, and `remediation: str | None`. It executes 6 pre-flight checks:
  1. OpenCode CLI check: runs `opencode --version` via `CommandRunner` and verifies exit code 0.
  2. Git cleanliness: verifies clean working tree and active checkout on `agent/ticket-runner` using `GitOperations`.
  3. Queue validation: verifies `docs/tickets/` directory contains at least one pending ticket file.
  4. Config validation: loads and validates `config.yaml` using `ConfigLoader`.
  5. Hook verification: verifies pre-push hook is installed with `PrePushHookInstaller.is_installed()`.
  6. Discord verification: unless `local_only=True` or `discord.enabled=False`, checks that the environment variable named in `config.discord.token_env` exists and is non-empty in `os.environ`.
- Generate clear, human-actionable remediation messages for each check failure and exit with non-zero status without modifying workspace state.
- Implement CLI entry point in `ticket_runner.py` with `argparse` supporting `doctor` command and `--local-only` flag.
- Create comprehensive spec-level behavioral test suite in `tests/specs/test_spec_01_doctor.py` validating all 12 user stories with `FakeCommandRunner` and temporary fixtures.
- Jump-start:
  - Files to touch: `runner/application/doctor.py`, `ticket_runner.py`, `tests/specs/__init__.py`, `tests/specs/test_spec_01_doctor.py`.
  - Seams: `runner/application/doctor.py:Doctor` composing `CommandRunner`, `GitOperations`, `ConfigLoader`, `PrePushHookInstaller`.
  - Anchor patterns: Spec 01 §1-25 and ARCHITECTURE.md §35.
  - Verification: `pytest tests/specs/test_spec_01_doctor.py`.

### Acceptance Criteria
- Doctor succeeds when all prerequisites are satisfied: OpenCode installed, working tree clean on `agent/ticket-runner`, `docs/tickets/` has pending tickets, `config.yaml` valid, pre-push hook active, and Discord env var set.
- Doctor halts immediately with diagnostic remediation message if OpenCode binary is missing.
- Doctor halts immediately if git working tree has uncommitted modifications.
- Doctor halts immediately if active branch is not `agent/ticket-runner`.
- Doctor halts immediately if `docs/tickets/` has zero pending tickets.
- Doctor halts immediately if `config.yaml` fails schema validation.
- Doctor halts immediately if `.git/hooks/pre-push` lacks the guardrail signature.
- Specifying `--local-only` bypasses Discord credentials verification.
- Comprehensive tests in `test_spec_01_doctor.py` verify all 12 user stories.

### Gotchas
- The Doctor is strictly read-only and non-destructive: it must never auto-stash, auto-commit, or auto-modify files when a check fails.
