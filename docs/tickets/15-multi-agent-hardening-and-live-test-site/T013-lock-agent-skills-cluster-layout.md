# T013 — Lock Agent-Skills Cluster Layout
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

What is the exact on-disk and configuration layout of the agent-skills cluster?
This spans two directories (`D:\Repos\agent-skills\` and
`D:\Repos\agent-runner-driver\`), the GitHub remote relationship between them, and
how the driver invokes ticket-runner against the skills repo.

### Why this matters

The agent-skills cluster is the only live-test site pointed at a real, public
upstream (`https://github.com/Viello/agent-skills`). Unlike the disposable sandbox
or the self-test harness, every ticket executed here accumulates real work that
must eventually reconcile with the public repo. The layout decision determines:

- Whether the driver pushes to `Viello/agent-skills` (it must NOT, per
  `AGENTS.md` "Never `git push`").
- Whether `scripts/publish_agent_skills.py` coexists or is replaced.
- How the user reviews accumulated commits before pushing manually.

### Requirements

- Decide the GitHub relationship:
  - Driver (`D:\Repos\agent-runner-driver\`) is a separate git repo with NO
    remote.
  - Skills clone (`D:\Repos\agent-skills\`) is a clone of
    `https://github.com/Viello/agent-skills` (the HEAD commit
    `e4eb54cd006a66229020009898035a5289ac7e73` was confirmed reachable on chart
    date).
  - Driver points `--project-dir` at the skills clone.
- Decide branch conventions:
  - Skills clone: `agent/ticket-runner` branch created locally; pre-push hook installed.
  - Driver: own git repo with `agent/ticket-runner` branch; pre-push hook installed.
- Decide `D:\Repos\` parent — does it need creating? (Confirmed empty; T014 creates
  it.)
- Decide `.gitignore` rules:
  - Driver: `.agent/`, `docs/tickets/.queue.lock`, the canonical Ticket Runner
    gitignore subset.
  - Skills clone: same, plus any Viello/agent-skills-specific ignores (existing
    patterns in the upstream's `.gitignore` if any).
- Decide whether the driver ships with a starter `ticket-runner.yaml` configured
  for `worker.provider: "antigravity"` (the locked default per
  `D:\Projects\config.yaml:11-13`) or `"opencode"`.
- Decide whether `scripts/publish_agent_skills.py` coexists with the driver
  or is replaced (escalate to T016 for the full replacement question).
- Decide the relationship between the driver's `.agent/` and the skills clone's
  `.agent/`:
  - Per `runtime_paths`, `.agent/` belongs to the Target Project (skills clone),
    not the driver. Driver's `.agent/` is irrelevant; runner uses the Target
    Project's.

### Acceptance Criteria

- The layout is recorded in the ticket's resolution comment:
  - Directory tree.
  - Git branch conventions for both repos.
  - `ticket-runner.yaml` provider setting.
  - `scripts/publish_agent_skills.py` coexistence / replacement status (delegated to T016).
- T014, T015 may proceed.

### Gotchas

- The pre-push hook in the skills clone blocks pushes from
  `agent/ticket-runner` per `docs/adr/0005-local-pre-push-git-hook.md`. This is
  intentional: the user accumulates commits locally, then manually reviews and
  merges to `main` before pushing to GitHub.
- The driver and the skills clone are siblings on disk but entirely separate
  git repos. Do not nest one inside the other.