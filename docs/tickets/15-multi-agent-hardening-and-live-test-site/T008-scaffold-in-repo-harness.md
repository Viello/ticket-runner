# T008 — Scaffold the In-Repo Harness at `D:\Projects\live-test-target/`
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T007
Reasoning: medium

### Question

Execute the layout decision locked in T007: create the in-repo harness, initialize
its own git repo, install the pre-push hook, append `live-test-target/` to
`D:\Projects\.gitignore`.

### Why this matters

The harness lets the user self-test ticket-runner against an internal target
without leaving `D:\Projects`. Quick iteration: change runner, point harness, run,
inspect.

### Requirements

- Create `D:\Projects\live-test-target/` with the layout T007 locked.
- Initialize git repo, branch `agent/ticket-runner`.
- Install pre-push hook (same mechanism as T006).
- Author initial scaffold commit (same exception pattern as T006).
- Append `live-test-target/` to `D:\Projects\.gitignore` (with a brief comment
  explaining the role — e.g. `# In-repo live-test harness (Spec 15 — isolated
  git repo)`).
- Confirm `git status` from `D:\Projects` shows the harness as ignored (not as
  untracked files).

### Acceptance Criteria

- `D:\Projects\live-test-target/` exists with the scaffold shape.
- `D:\Projects\.gitignore` contains the `live-test-target/` rule.
- `git status` from `D:\Projects` does NOT list `live-test-target/` as untracked.
- `ticket-runner --project-dir D:\Projects\live-test-target doctor` passes all
  checks.

### Smoke Scenarios

**Scenario: In-repo harness is wired and isolated**

- Setup: None (verifies the work done by T008).
- Why: Confirm the harness is fully scaffolded and isolated from the runner
  source repo.
- Steps:
  1. Run
     `python ticket_runner.py --project-dir D:\Projects\live-test-target doctor`.
  2. From `D:\Projects`, run `git status` and confirm `live-test-target/` does NOT
     appear in untracked files.
- Expected: Step 1 passes; Step 2 shows no untracked files related to the
  harness.

### Gotchas

- The `.gitignore` append must be idempotent — running T008 twice should not
  duplicate the rule.
- The pre-push hook for `D:\Projects\live-test-target/.git/hooks/pre-push` is
  independent of the one in `D:\Projects/.git/hooks/pre-push`. They are
  separate repos.