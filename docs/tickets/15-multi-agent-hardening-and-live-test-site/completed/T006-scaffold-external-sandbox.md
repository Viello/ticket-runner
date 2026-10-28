# T006 — Scaffold the External Sandbox at `D:\Sandbox\ticket-runner-live-target\`
**Type:** wayfinder:task (AFK)
Status: completed
Completed: 2026-10-04T15:35:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T005, T005a, T005b, T005c
Reasoning: medium

### Question

Execute the layout decision locked in T005 by invoking
`runner.tools.scaffold_sandbox` (per T005b) against
`D:\Sandbox\ticket-runner-live-target\`. T006 itself does not write the tree —
that is T005b's job. T006 is the "kick the tires" ticket that proves
scaffold_sandbox's output satisfies the user-facing demo promise.

### Why this matters

Without a live external sandbox, the user cannot:

- Experience the worker/gatekeeper flow against a real, runnable Python sample
  (per T005's resolution: `src/sample_app/` + `tests/test_smoke.py`).
- Watch the queue drive a trivial ticket (`T001-hello-world.md`) end-to-end.
- Diagnose issues by comparing runner behavior between `D:\Projects` and a clean
  external tree.
- Validate that `--project-dir` works on a sandbox tree that mirrors a real
  Target Project shape.

### Requirements

- Invoke
  `python -m runner.tools.scaffold_sandbox --non-interactive --force` from the
  Runner repo (`D:\Projects`) with the implicit default of
  `D:\Sandbox\ticket-runner-live-target\`.
- Verify the scaffold produces the T005-locked tree:
  - `.agent/{signals,questions,logs,checkpoints,evidence,archive}/`
  - `.agents/skills/{implement,code-review,diagnosing-bugs,handoff}/SKILL.md`
  - `docs/tickets/00-welcome/T001-hello-world.md`
  - `src/sample_app/__init__.py` + `tests/test_smoke.py`
  - `AGENTS.md` (preamble + curated subset, per T005c)
  - `ticket-runner.yaml` (provider: antigravity)
  - `.gitignore` (`.agent/`, `docs/tickets/.queue.lock`)
  - `.git/` with `agent/ticket-runner` branch and the pre-push guardrail hook
    installed.
- Verify the initial commit `chore(sandbox): initialize ticket-runner onboarding
  sandbox` exists on `agent/ticket-runner`.
- Verify `git log` shows the scaffold commit authored by
  `runner.tools.scaffold_sandbox` (per T005's Q13 = A: scaffold authors the
  commit, not the gatekeeper).
- DO NOT push (per `AGENTS.md` "Never `git push`" invariant).
- Run the smoke scenario (below) end-to-end.

### Acceptance Criteria

- `D:\Sandbox\ticket-runner-live-target\` exists with the T005-locked tree.
- `D:\Sandbox\ticket-runner-live-target\.git\hooks\pre-push` exists with the
  guardrail block.
- `git log` on `agent/ticket-runner` shows the initial scaffold commit
  (`chore(sandbox): initialize ticket-runner onboarding sandbox`).
- `python ticket_runner.py --project-dir
  D:\Sandbox\ticket-runner-live-target doctor` passes all checks.
- A second, idempotent invocation of
  `python -m runner.tools.scaffold_sandbox --non-interactive` (no `--force`)
  makes zero changes (verifies T005b's idempotency).
- The trivial ticket `T001-hello-world.md` is discoverable by the queue loader
  (i.e. has the right frontmatter shape, lives under a `<spec-slug>/` directory).

### Smoke Scenarios

**Scenario: External sandbox is fully scaffolded and doctor-clean**

- Setup: None (this scenario verifies the work done by T006).
- Why: Confirm the sandbox is wired end-to-end as a user-facing demo.
- Steps:
  1. Run
     `python ticket_runner.py --project-dir D:\Sandbox\ticket-runner-live-target
     doctor`.
  2. Confirm doctor prints "PASS" / no remediation messages.
  3. Inspect `D:\Sandbox\ticket-runner-live-target\AGENTS.md` and confirm the
     5-line preamble is present above the curated subset.
  4. Confirm `D:\Sandbox\ticket-runner-live-target\docs\tickets\00-welcome\
     T001-hello-world.md` is present and loadable.
- Expected: All four steps succeed; doctor reports a clean pre-flight; the
  welcome ticket is visible to a `ticket-runner queue list` invocation.

### Gotchas

- The sandbox's AGENTS.md is a curated subset (per T005c) — do NOT inline-edit
  it to match `D:\Projects/AGENTS.md`. Drift detection is
  `scripts/sync_agents_md.py`'s job (T005b).
- The pre-push hook installation is delegated to
  `runner.adapters.git.pre_push_hook install --git-dir <target>/.git` (T005a).
  T006 does not invoke `PrePushHookInstaller` directly.
- The `agent/ticket-runner` branch is created by scaffold_sandbox as part of its
  git-init step. T006 does not run `git checkout` separately.
- The initial commit is authored by scaffold_sandbox (one-shot exception to the
  "Gatekeeper alone commits" invariant per
  `docs/adr/0002-independent-gatekeeper-verification.md`); the gatekeeper does
  not run until a real ticket (T001-hello-world) executes.
- Re-running scaffold_sandbox in default mode is a no-op verification — useful
  for confirming the sandbox hasn't rotted, but does not regenerate anything.
  Use `--force` only when intentionally resetting.