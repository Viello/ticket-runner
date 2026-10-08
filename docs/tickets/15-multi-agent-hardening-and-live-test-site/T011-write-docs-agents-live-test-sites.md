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
  1. **Overview** — what the four sites are, their roles, when to use each. Frame
     the external sandbox (site #1) as the **user-facing onboarding site** for a
     first-time Ticket Runner visitor, not as a developer's disposable playground.
     The other three sites serve diagnostic and integration-test purposes for
     developers working on Ticket Runner itself.
  2. **External sandbox** (`D:\Sandbox\ticket-runner-live-target\`) — onboarding
     site. Path, branch, scaffold command (`python -m
     runner.tools.scaffold_sandbox` or `ticket-runner-scaffold-sandbox`), reset
     command (`... --force`), smoke-test entry point
     (`ticket-runner --project-dir D:\Sandbox\ticket-runner-live-target doctor`),
     and the welcome ticket
     (`docs/tickets/00-welcome/T001-hello-world.md`) that ships with the scaffold.
  3. **In-repo harness** (`D:\Projects\live-test-target/`) — self-test. Path,
     branch, `.gitignore` rule, smoke-test entry point.
  4. **Agent-skills driver** (`D:\Repos\agent-runner-driver\` →
     `D:\Repos\agent-skills\`) — real upstream. Path, branch, clone source URL,
     smoke-test entry point.
  5. **Empty starter** — scaffolding demonstrations. Path, design choice from T009.
  6. **Choosing a site** — decision matrix: which site fits which scenario. The
     matrix should treat "I'm trying Ticket Runner for the first time" as the
     sandbox case, and any Ticket Runner developer scenario as one of the other
     three.
- Cross-link from `AGENTS.md` to `docs/agents/live-test-sites.md`.
- Cross-link from `README.md` to `docs/agents/live-test-sites.md`.
- Document the install hints for `agy` and `opencode` (env vars
  `AGENT_ANTIGRAVITY_BIN` / `AGENT_OPENCODE_BIN` per T001) inside the
  External sandbox section, since the sandbox's `ticket-runner.yaml` ships
  pinned to `antigravity` and a first-time user without `agy` installed will
  hit Doctor remediation.
- In the External sandbox and In-repo harness sections, state the expected Doctor
  worker-binary line for an antigravity-pinned site (`agy` verified). Pre-T022
  `Doctor` misreported the provider (see `docs/tickets/gotchas.md`); document the
  corrected expectation, not the buggy line.

### Acceptance Criteria

- `docs/agents/live-test-sites.md` exists and covers all four sites.
- The External sandbox section is framed for a first-time user, with install
  hints for the worker binary.
- The decision matrix section is concrete enough to answer "which site should I use
  for X?" for at least five common scenarios, including "I'm trying Ticket
  Runner for the first time" → External sandbox.
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
- The External sandbox section must NOT use the word "disposable" — that framing
  was rejected at T005 in favor of "realistic user-facing onboarding." Drift on
  this wording is a T099 alignment issue.
- The decision matrix should not bury the sandbox case under developer-only
  scenarios. A first-time user landing on the doc should be able to identify the
  sandbox as their starting point within 30 seconds.
- Antigravity-pinned sites misreported `OpenCode CLI available` before T022 (the
  Doctor provider-resolution bug recorded in `docs/tickets/gotchas.md`). Document
  the corrected `agy` expectation and, if T022 has not landed yet, gate this
  section on it.