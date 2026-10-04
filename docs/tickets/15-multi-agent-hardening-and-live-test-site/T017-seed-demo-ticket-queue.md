# T017 — Seed the Demo Ticket Queue (Conditional)
**Type:** wayfinder:task (AFK)
Status: pending
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