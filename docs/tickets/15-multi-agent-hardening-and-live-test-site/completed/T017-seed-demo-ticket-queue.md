# T017 — Seed the Demo Ticket Queue (Conditional)
**Type:** wayfinder:task (AFK)
Status: completed
Completed: 2026-10-14T17:30:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T016 (only if "Yes — demo tickets" chosen)
Reasoning: medium

### Question

If T016 resolves "Yes — demo tickets", seed 2-3 starter tickets under
`D:\Repos\agent-runner-driver\docs\tickets\<spec-slug>\` that exercise the workflow
against the real upstream.

### Why this matters

Demo tickets are the proof that the driver works end-to-end against
`https://github.com/Viello/agent-skills`. Without them, the driver is just a
scaffold — it has never executed a real ticket against a real upstream.

### Requirements

- Create `D:\Repos\agent-runner-driver\docs\tickets\<spec-slug>\` with 2-3
  starter tickets. The exact tickets are T016's decision; suggested candidates
  if T016 deferred:
  1. **Add a new skill** — e.g. "Add `grill-me` skill mirror from
     `D:\Projects\.agents\skills\grill-me\SKILL.md`". Demonstrates adding new
     content to the upstream.
  2. **Refactor an existing skill** — e.g. "Consolidate `code-review` and
     `security-review` frontmatter". Demonstrates in-place modification of
     existing upstream content.
  3. **Document the catalog** — e.g. "Add top-level README to Viello/agent-skills
     that points to the skill catalog". Demonstrates documentation work.
- Each ticket must:
  - Follow the standard ticket format (frontmatter, requirements, acceptance
    criteria, smoke scenarios).
  - NOT include a ticket number in its title (per `AGENTS.md`).
  - Be tagged with the spec slug.
- The starter tickets accumulate work in the skills clone (via the driver) when
  executed; they are NOT executed by this ticket. Execution is the user's
  decision in subsequent sessions.

### Acceptance Criteria

- 2-3 demo tickets exist at
  `D:\Repos\agent-runner-driver\docs\tickets\<spec-slug>\`.
- Each ticket has the standard format and discipline (no ticket numbers in
  titles, conventional commit format applies when committed).

### Gotchas

- Do NOT execute the demo tickets in this Spec — T017 only seeds them.
  Execution is a separate activity.
- The demo tickets should target the public upstream's stable shape, not
  experimental or unstable areas of `Viello/agent-skills`.

### Smoke Scenarios

**Scenario: Demo queue is seeded and matches the spec convention**

- Setup: Driver is at `D:\Repos\agent-runner-driver`, with `.gitignore`,
  `scripts/start.ps1`, and `scripts/start.bat` already committed
  (`6214c1e`). T016 has resolved "Yes — demo tickets" with the queue
  location locked.
- Why: Verify the seed produces the structure the next ticket in the chain
  needs to execute against.
- Steps:
  1. Confirm `D:\Repos\agent-runner-driver\docs\specs\01-runner-live-test-bootstrap.md`
     exists and is a single-paragraph spec.
  2. Confirm `D:\Repos\agent-runner-driver\docs/tickets/01-runner-live-test-bootstrap/`
     holds exactly 2 starter tickets, each in standard format
     (frontmatter, requirements, acceptance criteria, smoke scenarios).
  3. Confirm neither H1 in the starter tickets includes a `T<nnn>` prefix
     (titles describe work; ticket numbers live in filenames only).
- Expected: All three steps succeed; the queue mirrors the spec slug in path
  and the convention in format.

### Resolution

- Authored 1-paragraph spec at
  `D:\Repos\agent-runner-driver/docs/specs/01-runner-live-test-bootstrap.md`
  describing the queue scope and reconciling the prior cluster-layout
  exclusion via the bootstrap's `--project-dir` indirection.
- Authored 2 demo tickets under
  `D:\Repos\agent-runner-driver/docs/tickets/01-runner-live-test-bootstrap/`:
  - `T101-add-codex-interface-metadata-to-skills-lacking-it.md` —
    adds the missing `agents/openai.yaml` to 8 catalog skills
    (clean-architecture, create-verification-skill, live-qa,
    maintain-verification-skill, security-review, smoke-fail,
    software-architecture, status). Exercises file-add code path.
  - `T102-document-agents-openai-yaml-in-skill-anatomy.md` — modifies the
    `README.md` "Skill Directory Anatomy" section to document the
    `agents/` interface files. Exercises in-place-modify code path.
  Both H1s are T<NNN>-free (titles describe work; ticket numbers live in
  filenames only), as required by the no-ticket-number-in-title constraint
  inherited from `AGENTS.md` commit-format invariant.
- Round-1 candidate suggestions (`grill-me` mirror, `code-review` frontmatter
  consolidation, top-level README) were not used: `grill-me` already exists
  in the catalog, the README already exists, and `code-review` frontmatter
  consolidation is too subjective to ground in real chart-time drift.
  Catalog gaps observed at chart-time (8 of 45 missing
  `agents/openai.yaml`; README anatomy silent on `agents/`) are
  objectively fixable and so became the seed content.
- Authored `D:\Repos\agent-runner-driver/docs/tickets/gotchas.md` capturing
  the cluster-layout reconciliation, the demo-tickets rationale, and the
  Unicode tree-character discipline in the README anatomy block.
- Demo tickets are seeded; execution is the user's decision in a subsequent
  session (likely a Ticket Runner run pointed at the driver).
- This ticket (`T017`) is marked `Status: completed` and relocated to
  `completed/T017-seed-demo-ticket-queue.md` per the implement-skill ticket
  transition.