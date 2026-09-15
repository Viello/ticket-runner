# T002 — Pre-push git hook guardrail installer
Status: completed
Completed: 2026-09-15T08:08:09Z
Commit: 88e667a66bc0ccb33bc2cde9bb047515b16c7dad
Spec: docs/specs/01-doctor-and-git-ops.md

### Requirements
- Author POSIX shell guardrail template in `scripts/pre-push.sh` that checks if the active branch is `agent/ticket-runner` and exits with code 1 to physically block remote pushes.
- Implement `PrePushHookInstaller` adapter in `runner/adapters/git/pre_push_hook.py` that manages `.git/hooks/pre-push`.
- When `.git/hooks/pre-push` is absent, write `scripts/pre-push.sh` and set executable permissions (`0o755`).
- When `.git/hooks/pre-push` exists, check for unique signature delimiter comments (`# BEGIN TICKET RUNNER GUARDRAIL` and `# END TICKET RUNNER GUARDRAIL`). If missing, non-destructively append the guardrail block to preserve any existing user-defined hooks.
- Provide `is_installed(git_dir: Path) -> bool` to verify the presence of the signature in the active hook file.
- Jump-start:
  - Files to touch: `scripts/pre-push.sh`, `runner/adapters/git/__init__.py`, `runner/adapters/git/pre_push_hook.py`, `tests/unit/adapters/test_pre_push_hook.py`.
  - Seams: Direct file operations in `.git/hooks/pre-push` isolated using pytest temporary directory fixtures.
  - Anchor patterns: ADR 0005 (Local pre-push git hook guardrails) and Spec 01 §29.
  - Verification: `pytest tests/unit/adapters/test_pre_push_hook.py`.

### Acceptance Criteria
- `scripts/pre-push.sh` uses POSIX shell syntax compatible with Git for Windows' bundled `sh.exe`.
- Installer creates `.git/hooks/pre-push` with correct permissions if the file does not exist.
- Installer non-destructively appends guardrail logic if `.git/hooks/pre-push` already contains user code.
- Installer is idempotent: re-running installation on an already-guarded hook produces no duplicate blocks.
- Unit tests verify creation, appending, and idempotency across temporary directories.

### Gotchas
- Windows filesystems do not natively support POSIX executable permission bits, but `os.chmod(hook_path, 0o755)` should still be called so the bit is set if run on Linux or Git Bash.
- Never overwrite existing hook files; always append between signed delimiters.
