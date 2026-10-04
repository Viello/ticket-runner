# T006 — Scaffold the External Sandbox at `D:\Sandbox\ticket-runner-live-target\`
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T005
Reasoning: medium

### Question

Execute the layout decision locked in T005: create the on-disk structure, initialize
the git repo, install the pre-push hook, and seed the minimal `ticket-runner.yaml`.

### Why this matters

Without a live external sandbox, the user cannot:

- Exercise the runner end-to-end against a fresh target without polluting
  `D:\Projects`.
- Diagnose issues by comparing runner behavior between `D:\Projects` and a clean
  external tree.
- Validate that `--project-dir` works on a sandbox tree that mirrors a real Target
  Project shape.

### Requirements

- Create `D:\Sandbox\` if it does not exist.
- Create `D:\Sandbox\ticket-runner-live-target\` with the layout T005 locked:
  - `.agent/` (with the standard subdirs: `signals/`, `questions/`, `logs/`,
    `checkpoints/`, `evidence/`, `archive/`).
  - `docs/tickets/` (empty for now — T016-T017-style demo tickets are NOT part of
    this sandbox; it stays disposable).
  - `.agents/skills/implement/SKILL.md` (minimal copy of
    `D:\Projects\.agents\skills\implement\SKILL.md`).
  - `.agents/skills/code-review/SKILL.md` (minimal copy).
  - `AGENTS.md` (minimal, pointing to AGENTS.md invariants — link back to
    `D:\Projects\AGENTS.md` for the canonical invariants, with a local note that
    this is a sandbox).
  - `ticket-runner.yaml` with the provider + execution_skill settings T005 locked.
  - `.gitignore` covering `.agent/` and `docs/tickets/.queue.lock`.
- Initialize git repo: `git init -b main`, `git checkout -b agent/ticket-runner`.
- Install pre-push hook:
  - Run `python -m runner.adapters.git.pre_push_hook install
    --target-dir D:\Sandbox\ticket-runner-live-target` (or whatever CLI the
    scaffolder exposes).
  - Verify `.git/hooks/pre-push` exists with the guardrail block.
- Author one initial commit on `agent/ticket-runner` with a `<type>(<scope>):
  <Title>` message per `AGENTS.md` commit format invariant — never include a ticket
  number. Suggested: `chore(sandbox): initialize disposable ticket-runner sandbox`.
- DO NOT push (per `AGENTS.md` "Never `git push`" invariant).

### Acceptance Criteria

- `D:\Sandbox\ticket-runner-live-target\.agent\` exists with the standard
  subdirectories.
- `D:\Sandbox\ticket-runner-live-target\docs\tickets\` exists.
- `D:\Sandbox\ticket-runner-live-target\.git\hooks\pre-push` exists with the
  guardrail block.
- `git log` on `agent/ticket-runner` shows the initial scaffold commit.
- `ticket-runner --project-dir D:\Sandbox\ticket-runner-live-target doctor`
  passes all checks.

### Smoke Scenarios

**Scenario: External sandbox is fully scaffolded and doctor-clean**

- Setup: None (this scenario verifies the work done by T006).
- Why: Confirm the sandbox is wired end-to-end.
- Steps:
  1. Run
     `python ticket_runner.py --project-dir D:\Sandbox\ticket-runner-live-target doctor`.
  2. Confirm doctor prints "PASS" / no remediation messages.
- Expected: Step 2 prints success for all doctor checks.

### Gotchas

- The sandbox's AGENTS.md should reference the canonical
  `D:\Projects\AGENTS.md` invariants so the runner's gatekeeper and worker behave
  consistently between sandbox and source repo.
- The `agent/ticket-runner` branch must be created BEFORE the pre-push hook is
  installed; otherwise the hook may not fire on the initial scaffold commit.
- The initial commit is hand-authored, not gatekeeper-authored. This is a one-time
  exception to the "Gatekeeper alone commits" invariant (per
  `docs/adr/0002-independent-gatekeeper-verification.md`) because no gatekeeper has
  yet run against an empty ticket queue.