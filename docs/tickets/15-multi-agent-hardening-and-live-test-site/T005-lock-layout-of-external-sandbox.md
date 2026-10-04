# T005 — Lock Layout of `D:\Sandbox\ticket-runner-live-target\`
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

What is the exact on-disk layout of the external sandbox at
`D:\Sandbox\ticket-runner-live-target\`? This includes the git branch convention,
scaffold commands, smoke-test entry point, and what minimal Target Project shape the
sandbox holds.

### Why this matters

`D:\Sandbox\ticket-runner-live-target\` is the disposable sandbox the user can point
`ticket-runner --project-dir` at. Without a documented layout, every scaffold
session invents its own conventions, drifting over time. The pattern is partially
established by `tests/specs/test_spec_11_decoupled_runner.py:76-100`
(`_seed_external_target_repo`), but no live, persistent site exists yet.

### Requirements

- Decide the on-disk layout:
  - `D:\Sandbox\` (parent — created by this ticket or by T006).
  - `D:\Sandbox\ticket-runner-live-target\` (the sandbox root).
  - `.agent/`, `docs/tickets/`, `AGENTS.md`, `ticket-runner.yaml`, `.agents/skills/`
    inside the sandbox root.
- Decide the git layout:
  - Own git repo (`git init`).
  - Branch: `agent/ticket-runner` (per `AGENTS.md` branch invariant).
  - Base branch: `main` (or `master`, whichever `git init` defaults to on the
    host).
  - Pre-push hook installed via the same mechanism as `D:\Projects`:
    `runner/adapters/git/pre_push_hook.py` reads `scripts/pre-push.sh` and installs
    the guardrail into `.git/hooks/pre-push` (see `AGENTS.md` invariant).
- Decide the smoke-test entry point:
  - Is there a single command the user runs to verify the sandbox is wired correctly?
    E.g. `ticket-runner --project-dir D:\Sandbox\ticket-runner-live-target\ doctor`.
  - Does the sandbox ship with a minimal `ticket-runner.yaml` that uses
    `worker.provider: "antigravity"` (to exercise the new env-var override path) or
    `"opencode"` (the default)?
- Decide whether the sandbox is rebuilt-on-demand or persistent:
  - Persistent means `D:\Sandbox\` survives across sessions.
  - Rebuild-on-demand means a script regenerates the sandbox from a template
    each time.
- Decide git-ignore rules:
  - `.agent/` is untracked (per `AGENTS.md`).
  - `docs/tickets/.queue.lock` is untracked.
  - These should appear in the sandbox's `.gitignore` from the start.

### Acceptance Criteria

- This ticket's resolution comment captures the layout decision in concrete terms:
  - Directory tree.
  - Git branch convention.
  - Smoke-test entry point command.
  - Provider setting in `ticket-runner.yaml`.
  - Persistence vs rebuild policy.
- T006 may proceed.

### Gotchas

- The sandbox's `.gitignore` is independent of `D:\Projects\.gitignore` — they are
  separate git repos.
- The pre-push hook guardrail blocks pushes from `agent/ticket-runner` per
  `docs/adr/0005-local-pre-push-git-hook.md`. The sandbox must have this installed
  before any ticket execution.