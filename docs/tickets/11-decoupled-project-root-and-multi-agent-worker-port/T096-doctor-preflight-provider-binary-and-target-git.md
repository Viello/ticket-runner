# T096 — Doctor Pre-Flight Verification for Configured Provider Binary and Target Project Root
Status: pending
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
Blocked by: T095
Security: required
Reasoning: medium

### Requirements
- Extend `Doctor` in `runner/application/doctor.py` to inspect the binary corresponding to `config.worker.provider`:
  - If `opencode`: verify `opencode` binary exists in PATH (via `shutil.which` or injectable resolver).
  - If `antigravity`: verify `agy` binary exists in PATH.
- Add pre-flight check in `Doctor` verifying that the target project directory exists, is a directory, and is a valid git repository (via `git rev-parse --is-inside-work-tree` through `GitOperations` or `CommandRunner`).
- Provide clear, actionable failure and remediation messages for both checks.
- Update `README.md` Pre-Flight Checks (Doctor) section describing the new provider binary and git repository checks.
- Jump-start:
  - Files to touch: `runner/application/doctor.py`, `README.md`, `tests/unit/application/test_doctor.py`.
  - Seams: `Doctor._check_worker_binary()`, `Doctor._check_target_git_repo()`.
  - Verification: `pytest tests/unit/application/test_doctor.py`.

### Acceptance Criteria
- Doctor pre-flight checks verify `opencode` when `provider == "opencode"` and `agy` when `provider == "antigravity"`.
- Doctor verifies target directory is an existing directory containing a valid git worktree.
- Failed checks return clear remediation instructions and non-zero report status.
- `README.md` documents both new Doctor verification checks.
- Security verification: Target directory path is checked safely without executing untrusted shell commands or scripts.

### Smoke Scenarios
**Scenario: Doctor Provider Binary and Target Repo Validation**
- Setup: None (runs from repo root).
- Why: Verify that Doctor detects missing binaries or non-git target paths and outputs helpful remediation messages.
- Steps:
  1. Run PowerShell verification testing Doctor with mock binaries and synthetic invalid directories:
     ```powershell
     python -c @"
     import asyncio
     from pathlib import Path
     from runner.application.doctor import Doctor
     from runner.domain.config import RunnerConfig, WorkerConfig, ProjectConfig, VerificationConfig, TokenBudgetConfig, PresenceConfig, DiscordConfig, LifecycleConfig, GitConfig
     cfg = RunnerConfig(
         project=ProjectConfig(name='test', branch='main', base_branch='main'),
         worker=WorkerConfig(execution_skill='.agents/skills/implement/SKILL.md', provider='antigravity'),
         verification=VerificationConfig(test_cmd='pytest'),
         tokens=TokenBudgetConfig(),
         presence=PresenceConfig(),
         discord=DiscordConfig(enabled=False),
         lifecycle=LifecycleConfig(),
         git=GitConfig(),
     )
     doctor = Doctor(config_loader=type('MockLoader', (), {'load': lambda self, p: cfg})(), which_fn=lambda cmd: None)
     report = asyncio.run(doctor.run(local_only=True))
     failed_names = [c.name for c in report.failed_checks]
     assert 'worker_binary' in failed_names or 'antigravity' in failed_names, f'Expected worker binary failure, got: {failed_names}'
     print('PASS: Doctor provider binary and repo checks verified.')
     "@
     ```
  2. Run `pytest tests/unit/application/test_doctor.py`.
- Expected: Doctor passes for valid environments and fails with actionable remediation for missing binaries or invalid git directories.

### Gotchas
- Binary path resolver must remain injectable (e.g. `shutil.which`) to keep unit tests fast and independent of host environment.
