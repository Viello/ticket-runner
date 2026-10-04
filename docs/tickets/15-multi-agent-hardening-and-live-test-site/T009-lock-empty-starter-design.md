# T009 — Lock the Empty-Starter Design
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

What is the on-disk shape of the "completely empty starter" directory that the user
will use to exercise the runner's scaffolding and startup against a fresh slate?

Three design candidates exist:

- **Pure empty** — only a `.gitkeep`. The user runs `ticket-runner init` against it
  and watches the runner scaffold every artifact.
- **Scaffold-tickets-only** — `ticket-runner init` has already been run; only
  `docs/tickets/<spec-slug>/` exists with starter tickets. The user watches the
  runner execute one starter ticket end-to-end.
- **Minimal-bare** — just `AGENTS.md` and `ticket-runner.yaml` so the runner
  has the minimum required files; the user runs `--local-only smoke` and watches
  the gatekeeper verify nothing.

### Why this matters

The user explicitly requested a "completely empty" state for watching scaffolding
and startup. The design choice determines what files the starter ships with and
what the user can demonstrate.

### Requirements

- Decide between the three candidates above (or a fourth hybrid).
- Decide the path:
  - Standalone `D:\Repos\empty-starter\`?
  - Under `D:\Sandbox\` alongside the external sandbox?
  - Inside the agent-skills driver (`D:\Repos\agent-runner-driver\empty/`)?
  - Other?
- Decide whether the starter is disposable (rebuilt on demand) or persistent
  (kept around as a reference target).
- Decide whether the starter ships with a `.gitkeep` or a `.gitignore` or
  nothing — the user mentioned "completely empty" which implies minimal
  artifacts.

### Acceptance Criteria

- The chosen design candidate is recorded in the ticket's resolution comment.
- The chosen path is finalized.
- T010 may proceed.

### Gotchas

- "Completely empty" is the user's stated goal — favor candidates that maximize
  what `ticket-runner init` will scaffold rather than candidates that pre-seed
  artifacts.