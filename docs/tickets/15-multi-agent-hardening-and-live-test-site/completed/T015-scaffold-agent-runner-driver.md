# T015 — Scaffold `D:\Repos\agent-runner-driver\`
**Type:** wayfinder:task (AFK)
Status: completed
Completed: 2026-10-14T06:52:00Z
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
- Per T013's minimal-stub discipline rule, **do not** create `ticket-runner.yaml`,
  `.agent/`, or `docs/tickets/` inside the driver. The driver is an invocation
  stub; the skills clone (Target Project) owns those artifacts.
- Create `.gitignore` covering `.agent/`, `docs/tickets/.queue.lock` (defensive,
  even though the directories are not created now — prevents accidental
  commits if they are added later).
- Create `scripts/start.ps1` per the bootstrap command documented in T013's
  Resolution. Body is essentially:
  `python D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start @args`
  with a header comment declaring the implicit `--project-dir` path.

### Acceptance Criteria

- `D:\Repos\agent-runner-driver\` exists with the minimal-stub shape: `git/`,
  pre-push hook, `.gitignore`, the initial scaffold commit, and
  `scripts/start.ps1` — and **no** `ticket-runner.yaml`, `.agent/`, or
  `docs/tickets/`.
- `scripts/start.ps1` exists and its body hard-codes
  `--project-dir D:\Repos\agent-skills` with the documented header comment.
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
- The minimal-stub shape (no `ticket-runner.yaml`, no `.agent/`, no
  `docs/tickets/`) is a deliberate T013 decision. The `.gitignore` still
  references those paths so an accidentally-created directory stays untracked
  rather than being mistaken for an active Target Project.
- Its "doctor passes all checks" AC can pass for the wrong reason on an
  antigravity-configured site: pre-T022 `Doctor` misresolved the provider and
  printed `OpenCode CLI available`. Confirm T022 has landed and that doctor
  reports the `agy` check (see `docs/tickets/gotchas.md`).

### Resolution

- Created `D:\Repos\agent-runner-driver\` directory.
- Initialized empty git repo with branch `agent/ticket-runner`.
- Installed pre-push guardrail hook into `D:\Repos\agent-runner-driver\.git\hooks\pre-push` using `runner.adapters.git.pre_push_hook`. Verified direct push is blocked.
- Created defensive `.gitignore` covering `.agent/` and `docs/tickets/.queue.lock`.
- Created `scripts/start.ps1` with the documented header comment, hardcoded `--project-dir D:\Repos\agent-skills`, and python launcher (`py -3`/`python`) autodetection. Also authored `scripts/start.bat` for cmd.exe execution.
- Maintained minimal-stub discipline: driver contains strictly `.git`, pre-push hook, `.gitignore`, and `scripts/` (no `ticket-runner.yaml`, no `.agent/`, no `docs/tickets/`).
- Authored initial root scaffold commit on `agent/ticket-runner`: `6214c1e` (`chore(driver): scaffold agent-skills driver invocation stub`).
- Verified smoke scenarios: running Doctor from `D:\Repos\agent-runner-driver` with `--project-dir D:\Repos\agent-skills` cleanly inspects the Target Project on branch `agent/ticket-runner` (pre-flight queue validation notes `docs/tickets/` awaiting seeding via T016/T017).