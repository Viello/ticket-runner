# T012 — Decide: Does Each Site Need a `verify-<app>` Skill?
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T006, T008, T015
Reasoning: medium

### Question

Should each of the four live-test sites have a `verify-<app>` skill (per the
`create-verification-skill` discipline), or is `--local-only smoke` (or the new
in-band smoke verification) sufficient?

### Why this matters

The `create-verification-skill` skill scaffolds per-app verification harnesses with
the 5-step lifecycle contract, harness stubs, and feature maps. Creating one per
site is heavy (each is its own skill with feature-map maintenance) but gives:

- Structured verification criteria.
- Per-feature maps that future candidates update.

Alternatively, `--local-only smoke` runs the gatekeeper's verification commands
without verification harnesses. Lighter, but less structured.

### Requirements

- Evaluate per-site:
  1. **External sandbox** — disposable. `verify-ticket-runner-live-target`?
     Probably no — it's disposable.
  2. **In-repo harness** — self-test. `verify-ticket-runner-self-test`? Maybe —
     it has a stable shape.
  3. **Agent-skills driver** — real upstream driving a real catalog.
     `verify-viello-agent-skills`? Strongest candidate — the agent-skills repo has
     verifiable structure (skill catalog indexing, README generation, etc.).
  4. **Empty starter** — scaffolding demo. No verify (the point is the empty
     state).
- For each `yes` candidate, decide the verification contract:
  - 5-step lifecycle (Setup, Execute, Verify, Cleanup, Report).
  - Harness stubs (Python module, CLI entry, feature map).
  - Initial feature map scope (which features to verify).
- Decide whether the verification skills live at the global skills catalog
  (`C:\Users\Acer\.agents\skills\` or equivalent) or at the per-site location.

### Acceptance Criteria

- A per-site decision recorded in the ticket's resolution comment:
  - Site name, yes/no decision, justification, contract if yes.
- For each `yes` site:
  - The `verify-<app>` skill is created per the `create-verification-skill`
    discipline.
  - The skill is reachable from the live-test-sites.md doc.
- For each `no` site:
  - A one-line justification in the doc.

### Gotchas

- Creating a `verify-<app>` skill is non-trivial work. If three of four sites get
  one, T012 becomes a multi-ticket effort on its own. Consider whether to break
  T012 into per-site sub-tickets (T012a, T012b, T012c).
- The agent-skills driver's verify skill is the most defensible; the external
  sandbox's is the least. Don't force symmetry.