# T011 — Write `docs/agents/live-test-sites.md`
**Type:** wayfinder:task (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T006, T008, T010, T015
Reasoning: medium

### Question

Document the four live-test sites (external sandbox, in-repo harness, agent-skills
driver, empty starter) in a single reference file. The doc becomes the entry point
for users (and future agents) deciding which site to use.

### Why this matters

Without a reference, the user has to remember (or rediscover) the four sites, their
roles, and their `--project-dir` invocations. Future spec-closing alignment tickets
will reference this doc as the canonical list.

### Requirements

- Create `docs/agents/live-test-sites.md` (per the matt-pocock-skills
  `docs/agents/` convention; the existing structure under `D:\Projects\docs\` is
  already `adr/`, `tickets/`, etc. — `agents/` is the next sibling).
- Sections:
  1. **Overview** — what the four sites are, their roles, when to use each.
  2. **External sandbox** (`D:\Sandbox\ticket-runner-live-target\`) — disposable
     experiments. Path, branch, scaffold, smoke-test entry point.
  3. **In-repo harness** (`D:\Projects\live-test-target/`) — self-test. Path, branch,
     `.gitignore` rule, smoke-test entry point.
  4. **Agent-skills driver** (`D:\Repos\agent-runner-driver\` →
     `D:\Repos\agent-skills\`) — real upstream. Path, branch, clone source URL,
     smoke-test entry point.
  5. **Empty starter** — scaffolding demonstrations. Path, design choice from T009.
  6. **Choosing a site** — decision matrix: which site fits which scenario.
- Cross-link from `AGENTS.md` to `docs/agents/live-test-sites.md`.
- Cross-link from `README.md` to `docs/agents/live-test-sites.md`.

### Acceptance Criteria

- `docs/agents/live-test-sites.md` exists and covers all four sites.
- The decision matrix section is concrete enough to answer "which site should I use
  for X?" for at least five common scenarios.
- Cross-links from `AGENTS.md` and `README.md` resolve correctly.

### Smoke Scenarios

**Scenario: Live-test sites doc is complete and discoverable**

- Setup: None (verifies T011's work).
- Why: Confirm the doc is well-organized and reachable from the project's entry
  points.
- Steps:
  1. Open `docs/agents/live-test-sites.md` and confirm all six sections exist.
  2. From `AGENTS.md`, follow the cross-link to the doc.
  3. From `README.md`, follow the cross-link to the doc.
- Expected: All three steps succeed.

### Gotchas

- The doc is a living document. T099 (spec-closing alignment) and future tickets
  may amend it. Keep it short, concrete, and code-block-heavy (so future edits
  are localized).