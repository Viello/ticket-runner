# T005a — Add CLI to `runner/adapters/git/pre_push_hook.py`
**Type:** wayfinder:task (AFK)
Status: completed
Completed: 2026-10-04T14:15:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: low

### Question

Expose `PrePushHookInstaller.install()` as a module-level entry point so external
scaffolders (T005b's `runner.tools.scaffold_sandbox`) and ad-hoc shell users can
invoke the installer without writing inline Python. Today the installer is a
classmethod on `PrePushHookInstaller` (`runner/adapters/git/pre_push_hook.py:53`)
that only the Doctor (`runner/application/doctor.py`) calls.

### Why this matters

T005 locks `D:\Sandbox\ticket-runner-live-target\` as a persistent user-facing
onboarding sandbox whose pre-push hook must be installed by T006's scaffolder
script. Without a CLI, T005b has two bad options:

- Inline `python -c "from runner.adapters.git.pre_push_hook import
  PrePushHookInstaller; PrePushHookInstaller.install(git_dir=...)"`, which is
  fragile to quote escaping in `cmd.exe` (the documented Windows shell).
- Import `PrePushHookInstaller` from `runner.tools.scaffold_sandbox` and call the
  classmethod directly, which is fine for T005b but discourages ad-hoc installs.

A 6-line CLI module unblocks both.

### Requirements

- Add an `if __name__ == "__main__":` block to
  `runner/adapters/git/pre_push_hook.py` (the existing adapter file; no new
  module).
- Use `argparse` with a single subcommand (`install`) and a required
  `--git-dir <path>` argument pointing at the target `.git/` directory.
- Honor an optional `--template-path <path>` argument (forwarded to
  `PrePushHookInstaller.install`); default `None` → use `DEFAULT_STANDALONE_HOOK`
  per T005's lock.
- Print a one-line success message on completion (e.g.
  `Installed pre-push guardrail into <path>.git/hooks/pre-push`).
- Exit non-zero if `git_dir` does not exist or is not a directory.
- Add a unit test at `tests/unit/adapters/test_pre_push_hook_cli.py` covering:
  - Happy path: `python -m runner.adapters.git.pre_push_hook install --git-dir
    <tmpdir>/.git` exits 0 and creates `pre-push` with the BEGIN/END signature
    block.
  - Idempotent re-run on an already-installed hook: exit 0, no overwrite of
    existing content.
  - Missing `--git-dir` argument: exit non-zero with a usage message.
  - Non-existent `--git-dir`: exit non-zero with a clear error.

### Acceptance Criteria

- `python -m runner.adapters.git.pre_push_hook install --git-dir <path>` works from
  any CWD.
- The CLI re-uses the existing `PrePushHookInstaller.install()` classmethod
  (no duplication of guardrail text).
- All 4 new unit tests pass; existing `tests/unit/adapters/test_pre_push_hook.py`
  (or equivalent) still passes.
- A gotcha entry is added to `docs/tickets/gotchas.md` summarizing the CLI's
  `--git-dir`-vs-`--target-dir` naming choice (the T006 originally-suggested
  `--target-dir` was renamed to `--git-dir` for consistency with the installer's
  `git_dir` parameter).

### Smoke Scenarios

**Scenario: Pre-push hook installer CLI works end-to-end**

- Setup: A temp directory containing an empty `.git/` subdir.
- Why: Verify the CLI installs the guardrail correctly without going through
  Doctor.
- Steps:
  1. Run `python -m runner.adapters.git.pre_push_hook install --git-dir
     <tmpdir>/.git`.
  2. Confirm `<tmpdir>/.git/hooks/pre-push` exists and contains the
     `# BEGIN TICKET RUNNER GUARDRAIL` / `# END TICKET RUNNER GUARDRAIL`
     signature block.
  3. Confirm the file is executable (mode `0o755` on POSIX, or has the
     executable-bit-equivalent on Windows).
- Expected: All three steps succeed.

### Gotchas

- Do not introduce a separate `cli.py` module — keeping the entry point in
  `pre_push_hook.py` matches how `Doctor` calls the installer and avoids a
  second import surface to keep in sync.
- The CLI argument is `--git-dir`, not `--target-dir`. The Doctor and the
  classmethod use `git_dir`; reusing the name keeps the vocabulary consistent.
- Idempotency is delegated to `PrePushHookInstaller.install()` (which already
  short-circuits when the signature is present); the CLI does not add its own
  state-tracking.
