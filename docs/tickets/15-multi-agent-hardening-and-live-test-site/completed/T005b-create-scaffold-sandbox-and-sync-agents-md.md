# T005b — Create `runner.tools.scaffold_sandbox` and `scripts/sync_agents_md.py`
**Type:** wayfinder:task (AFK)
Status: completed
Completed: 2026-10-04T14:28:36Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T005, T005a, T005c
Reasoning: medium

### Question

Implement the two pieces of scaffolding infrastructure that T005's plan requires
but does not write code for:

1. **`runner.tools.scaffold_sandbox`** — a module under `runner/tools/` (alongside
   the planned package, mirroring the project's layer convention of
   `runner/application/`, `runner/adapters/`, `runner/ports/`) that scaffolds
   `D:\Sandbox\ticket-runner-live-target\` to the layout T005 locked.
2. **`scripts/sync_agents_md.py`** — a one-way upstream-to-sandbox drift detector
   for the curated `AGENTS.md` copy.

### Why this matters

T006 is currently described as the executor of T005's locked layout, but the actual
heavy lifting — generating the directory tree, writing `ticket-runner.yaml`,
copying four skills, generating `AGENTS.md` from the curated subset, installing the
pre-push hook, and authoring the initial scaffold commit — should live in a
testable tool, not in the ticket body. Lifting it into `runner.tools` lets T006 be
a short invocation and keeps the scaffold shape under unit-test discipline.

The sync script is the maintenance burden's escape valve: when
`D:\Projects/AGENTS.md` invariants change, an operator can detect drift between
upstream and the sandbox copy without manual diffing.

### Requirements

**`runner.tools.scaffold_sandbox`** (`runner/tools/scaffold_sandbox.py`):

- Public API:
  - `def scaffold(target_dir: Path, *, force: bool = False) -> None: ...`
  - `def main(argv: list[str] | None = None) -> int: ...` (for
    `python -m runner.tools.scaffold_sandbox`).
- CLI surface:
  - `python -m runner.tools.scaffold_sandbox [--target-dir <path>]
    [--force] [--non-interactive]`
  - `--target-dir` defaults to `D:\Sandbox\ticket-runner-live-target\` on Windows
    and `~/Sandbox/ticket-runner-live-target` on POSIX (use
    `platform.system()`); `--force` wipes the directory before scaffolding.
  - `--non-interactive` skips the "this will wipe everything" confirmation
    prompt; required for CI/AFK execution.
- Default mode (no `--force`) is idempotent: existing files are preserved, only
  missing files are created. `--force` removes everything under `target_dir`
  except `target_dir/.git/` and `target_dir/.agent/` (runtime state) before
  regenerating.
- Creates the full T005-locked tree:
  - `.agent/{signals,questions,logs,checkpoints,evidence,archive}/`
  - `.agents/skills/{implement,code-review,diagnosing-bugs,handoff}/SKILL.md`
    copied from `D:\Projects\.agents\skills/<name>/SKILL.md`
    (or `Path(__file__).resolve().parent.parent.parent / ".agents/skills"` —
    whichever resolves; document the fallback).
  - `docs/tickets/00-welcome/` (empty directory + the `T001-hello-world.md` ticket
    content baked in, per T005's resolution).
  - `src/sample_app/__init__.py` (trivial `greet(name: str) -> str` function).
  - `tests/test_smoke.py` (one `pytest` asserting `greet("world") == "hello,
    world!"`).
  - `AGENTS.md` (5-line preamble + curated subset from upstream, per T005c).
  - `ticket-runner.yaml` (provider: antigravity, execution_skill:
    `.agents/skills/implement/SKILL.md`).
  - `.gitignore` (`.agent/`, `docs/tickets/.queue.lock`).
- Initializes git (if `.git/` is missing): `git init -b main`, then
  `git checkout -b agent/ticket-runner`.
- Installs the pre-push hook via `python -m
  runner.adapters.git.pre_push_hook install --git-dir <target>/.git` (per T005a),
  shelling out via `subprocess.run` so the CLI's exit code is observable.
- Authors the initial commit (`chore(sandbox): initialize ticket-runner onboarding
  sandbox`) using `gitpython` or `subprocess.run(["git", "-C", target_dir,
  "commit", ...])`. Configures `user.name`/`user.email` to a local default
  (`ticket-runner-scaffold <noreply@local>`) before committing if no global git
  identity is set.
- Logs a 5-line summary at the end (target dir, files created, hook installed,
  commit SHA, doctor command to verify).

**`scripts/sync_agents_md.py`**:

- One-way sync: reads `D:\Projects/AGENTS.md`, compares to
  `<target_dir>/AGENTS.md` (default `D:\Sandbox\ticket-runner-live-target\`).
- Diffs only the **curated subset** section (the part copied verbatim per T005c);
  ignores the preamble and the sync stamp.
- Exit codes: 0 if in sync, 1 if drift detected, 2 on missing-file I/O.
- Flags: `--target-dir <path>` (default sandbox path), `--write` (apply the
  upstream changes to the sandbox copy, stamping a fresh sync date; without `--write`
  the script is dry-run).
- No git ops, no commits, no installation of anything.

### Acceptance Criteria

- `python -m runner.tools.scaffold_sandbox --non-interactive --force` produces a
  fully-wired sandbox that passes
  `python ticket_runner.py --project-dir <target> doctor` on a fresh machine.
- `python -m runner.tools.scaffold_sandbox --non-interactive` (default mode) on an
  already-scaffolded sandbox makes zero changes (idempotent).
- A `ticket-runner-scaffold-sandbox` console-script entry point in
  `pyproject.toml` invokes the same code (T005's resolved Q1-a follow-up).
- `scripts/sync_agents_md.py --write` brings a manually-diverged sandbox
  `AGENTS.md` back in sync with the curated subset.
- Unit tests at `tests/unit/tools/test_scaffold_sandbox.py` cover: idempotent
  mode preserves existing files, `--force` wipes + regenerates, missing git
  identity is auto-configured, hook installer is invoked via subprocess.
- Unit tests at `tests/unit/scripts/test_sync_agents_md.py` cover: in-sync
  exit 0, drift exit 1, `--write` updates the sandbox file and resets the stamp.
- A gotcha entry is added to `docs/tickets/gotchas.md` summarizing the
  scaffold_sandbox --force semantics.

### Smoke Scenarios

**Scenario: Sandbox scaffolds successfully and doctor-passes**

- Setup: An empty `D:\Sandbox\` parent directory.
- Why: Verify end-to-end that scaffold_sandbox produces a doctor-clean sandbox.
- Steps:
  1. Run
     `python -m runner.tools.scaffold_sandbox --non-interactive --force`.
  2. Confirm `D:\Sandbox\ticket-runner-live-target\` exists with the T005-locked
     tree.
  3. Run
     `python ticket_runner.py --project-dir D:\Sandbox\ticket-runner-live-target
     doctor`.
- Expected: Step 3 reports PASS / no remediation messages.

**Scenario: Sync script flags drift**

- Setup: A scaffolded sandbox.
- Steps:
  1. Run `python scripts/sync_agents_md.py` (no `--write`).
- Expected: Exit 1, stdout lists the differing lines.

### Gotchas

- The scaffold commits via subprocess `git commit`, but `user.name`/`user.email`
  are NOT set by the scaffolder unless missing — the operator's existing git
  identity is preserved. Auto-config only kicks in when `git config user.name`
  returns empty.
- The curated AGENTS.md subset is defined by T005c, not by this ticket. T005b's
  source of the curated subset is whatever T005c locks in. If T005c resolves before
  T005b lands, T005b reads T005c's locked preamble + section list; if T005c
  lands after T005b, T005b reads from a placeholder and T099 (spec-closing
  alignment) reconciles.
- The `--force` flag does NOT wipe `.git/` (history is preserved) or `.agent/`
  (runtime state). Only source-tree files (`AGENTS.md`, `ticket-runner.yaml`,
  `.agents/`, `docs/`, `src/`, `tests/`, `.gitignore`) are wiped.
- The console-script entry point in `pyproject.toml` is
  `ticket-runner-scaffold-sandbox = runner.tools.scaffold_sandbox:main`.
