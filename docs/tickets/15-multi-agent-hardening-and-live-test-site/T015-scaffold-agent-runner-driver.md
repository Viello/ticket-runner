# T015 — Scaffold `D:\Repos\agent-runner-driver\`
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T013
Reasoning: medium

### Question

Create the agent-runner-driver at `D:\Repos\agent-runner-driver\`. This is the
sibling folder that invokes ticket-runner against the skills clone at
`D:\Repos\agent-skills\` (created in T014).

### Why this matters

The driver is the live-test harness for the agent-skills cluster. It is the seat
where `ticket-runner start --project-dir D:\Repos\agent-skills` runs, where
gatekeeper commits accumulate, and where the user reviews accumulated work before
pushing manually.

### Requirements

- Create `D:\Repos\agent-runner-driver\` if it does not exist.
- Initialize git repo with branch `agent/ticket-runner`.
- Install pre-push hook (same mechanism as T006/T008/T014).
- Author an initial scaffold commit (per the T006/T008 exception pattern — no
  gatekeeper has run yet).
- Write `ticket-runner.yaml` with:
  - `worker.provider` set per T013's decision (default candidate: `"antigravity"`).
  - `project_dir: D:\Repos\agent-skills\` (per Spec 11 `project_dir:` key support,
    OR document that `--project-dir` is required on the CLI).
  - Standard verification commands (placeholder until T016 resolves demo tickets).
- Create `.agent/` with the standard subdirs (`signals/`, `questions/`, `logs/`,
  `checkpoints/`, `evidence/`, `archive/`).
- Create `docs/tickets/` (empty for now; T017 may seed demo tickets).
- Create `.gitignore` covering `.agent/`, `docs/tickets/.queue.lock`.

### Acceptance Criteria

- `D:\Repos\agent-runner-driver\` exists with the scaffold shape.
- `ticket-runner.yaml` exists and contains the `project_dir` (or notes that
  `--project-dir` is required).
- `agent/ticket-runner` branch exists with the initial scaffold commit.
- `git log` from `D:\Repos\agent-runner-driver` shows the commit.
- `ticket-runner --project-dir D:\Repos\agent-skills doctor` (run from
  `D:\Repos\agent-runner-driver`) passes all checks.

### Smoke Scenarios

**Scenario: Driver is fully scaffolded and wired against the skills clone**

- Setup: T014 must be completed first (skills clone must exist).
- Why: Confirm the driver's doctor recognizes the skills clone as a healthy
  Target Project.
- Steps:
  1. From `D:\Repos\agent-runner-driver`, run
     `python ticket_runner.py --project-dir D:\Repos\agent-skills doctor`.
  2. Confirm doctor prints "PASS" / no remediation messages.
  3. Confirm the doctor reports the `agent/ticket-runner` branch as expected.
- Expected: Steps 1-3 pass.

### Gotchas

- The driver and the skills clone are siblings on disk. Do not nest.
- The driver does NOT have a remote; the upstream is the skills clone's
  `origin`, not the driver's.
- The initial scaffold commit is hand-authored (T006/T008 exception pattern).
- Its "doctor passes all checks" AC can pass for the wrong reason on an
  antigravity-configured site: pre-T022 `Doctor` misresolved the provider and
  printed `OpenCode CLI available`. Confirm T022 has landed and that doctor
  reports the `agy` check (see `docs/tickets/gotchas.md`).