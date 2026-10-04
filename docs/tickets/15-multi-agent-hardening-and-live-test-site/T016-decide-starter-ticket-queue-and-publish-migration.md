# T016 — Decide: Ship a Starter Ticket Queue in the Driver?
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T013
Reasoning: medium

### Question

Should the agent-skills driver ship with a starter ticket queue (e.g. "add a new
skill", "update existing skill", "refactor skill structure") to prove the workflow
end-to-end against the real upstream? Or should the queue stay empty for the user
to fill in?

A secondary question: should `scripts/publish_agent_skills.py` (the current manual
publication workflow at `D:\Projects\scripts\publish_agent_skills.py:1-2`) be
replaced by ticket-driven publication?

### Why this matters

The user said the agent-skills repo "will be my agentic coding workflow where in
[i use] in every project file even if ticket runner isn't set up there". A starter
ticket queue proves the driver works against a real repo; an empty queue leaves
the demonstration for the user.

`scripts/publish_agent_skills.py` is the current one-off publication workflow.
T016's resolution determines whether this Spec replaces it, complements it, or
leaves it alone.

### Requirements

- Decide on a starter ticket queue:
  - **Yes — demo tickets** — pre-seed `docs/tickets/<spec-slug>/` in the driver
    with 2-3 starter tickets. Examples:
    - "Add `grill-me` skill (mirroring `.agents/skills/grill-me/SKILL.md` from
      `D:\Projects`)".
    - "Refactor `code-review` skill to v2 schema".
    - "Document the agent-skills catalog in a top-level README".
    These tickets accumulate real work in the skills clone (via the driver) and
    prove the workflow end-to-end.
  - **No — empty queue** — leave `docs/tickets/` empty. The user adds their own
    tickets as they come up.
- Decide on `scripts/publish_agent_skills.py`:
  - **Replace** — deprecate the script; ticket-driven flow becomes the canonical
    publication path. Requires T016a "migrate publication workflow to ticket
    queue" as a follow-up ticket.
  - **Coexist** — keep the script for one-off / bulk operations; tickets handle
    day-to-day additions.
  - **Leave alone** — out of scope for this Spec; revisit later.

### Acceptance Criteria

- The starter-queue decision is recorded in the ticket's resolution comment.
- The `publish_agent_skills.py` decision is recorded in the same comment.
- If "Yes — demo tickets" is chosen: T017 is unblocked and lists the specific
  tickets to seed.
- If "Replace `publish_agent_skills.py`" is chosen: a follow-up ticket (e.g.
  T016a) is created with the migration scope documented.

### Gotchas

- Demo tickets must NOT include ticket numbers in their titles (per `AGENTS.md`
  commit-format invariant — even if demo, the discipline holds).
- The starter queue should be small (2-3 tickets) — the goal is to prove the
  workflow, not to ship a comprehensive demo.
- The "Replace" option for `publish_agent_skills.py` is a substantial effort; if
  chosen, plan for T016a to be its own ticket with its own acceptance criteria.