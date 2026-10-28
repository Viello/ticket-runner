# T013 — Lock Agent-Skills Cluster Layout
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-14T06:21:25Z
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

### Resolution

- **Driver — `D:\Repos\agent-runner-driver\`** (minimal invocation stub):
  - `git init -b main` → `git checkout -b agent/ticket-runner`
  - Pre-push hook installed via `PrePushHookInstaller.install()` with
    `DEFAULT_STANDALONE_HOOK` (no remote, matches T006/T008/T009/T014)
  - `.gitignore` covers `.agent/`, `docs/tickets/.queue.lock`
  - Initial scaffold commit authored by hand (T006/T008 exception pattern)
  - `scripts/start.ps1` hard-codes `--project-dir D:\Repos\agent-skills`
    (header comment documents the implicit path)
  - **No `ticket-runner.yaml`, no `.agent/`, no `docs/tickets/`** in the driver —
    discipline rule: the driver carries no file the runner parses, so an
    accidental `ticket-runner start` from the driver's CWD cannot drift provider
    or scan empty signal directories
  - No remote (`origin` unset)
- **Skills clone — `D:\Repos\agent-skills\`**:
  - `git clone https://github.com/Viello/agent-skills` to that path
  - HEAD SHA recorded by T014 at close time (`e4eb54cd006a66229020009898035a5289ac7e73`
    at chart date; T014 confirms the actual current upstream SHA)
  - `git checkout -b agent/ticket-runner` from `main`
  - Pre-push hook installed (same `DEFAULT_STANDALONE_HOOK` mechanism)
  - `.gitignore`: add `.agent/` and `docs/tickets/.queue.lock` **only if upstream
    does not already cover them**; do not add any other patterns
  - **Escalation**: if upstream `.gitignore` lacks `docs/tickets/.queue.lock`,
    open a small ADR instead of carving a one-off entry
- **Parent — `D:\Repos\`**:
  - 5-line `README.md` declaring the cluster's taxonomy ("External target projects
    operated on by `D:\Projects` ticket-runner"); parent of the driver, the
    skills clone, and the empty-starter (T009)
  - Out of scope of every child's `.gitignore`; no remote; pure prose the
    runner never reads
- **`ticket-runner.yaml` provider setting**: `worker.provider: antigravity`
  (matches `D:\Projects\config.yaml:11-13`; aligns the driver with the
  sandbox (T005) and the empty-starter (T009) on the same backend)
- **`project_dir` representation**: CLI flag `--project-dir` only; no YAML
  `project_dir:` key. `YamlConfigLoader` schema unchanged.
- **`scripts/publish_agent_skills.py` status**: **TBD — delegated to T016**.
  This placeholder will be overwritten at T016 close.
- **Bootstrap command**: `pwsh D:\Repos\agent-runner-driver\scripts\start.ps1`

T014, T015 may proceed.

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