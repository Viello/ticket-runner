# Example — Wayfinder Ticket Type Labels

This is a worked example showing the four wayfinder ticket types with their
HITL/AFK classification. The wayfinder skill at
`D:\Projects\.agents\skills\wayfinder\SKILL.md` requires every ticket to carry a
`**Type:** wayfinder:<research|prototype|grilling|task> (<HITL|AFK>)` line as
the second line of the ticket markdown.

---

## Example 1 — Research ticket (AFK)

**Type:** wayfinder:research (AFK)
Status: pending
Spec: docs/specs/example-spec.md
Blocked by: none
Reasoning: low

### Question

What is the canonical flag surface of the `<external-cli>` binary on the host?
Surface the empirical flags, JSONL envelope shape, and exit codes so a follow-up
implementation ticket can build the adapter against verified input rather than
guessed-at documentation.

### Resolution

Resolved by research subagent on branch `research/<cli-name>-flag-surface`
(commit `<sha>`), file `.agents/skills/research/out/<cli-name>-flag-surface.md`.

---

## Example 2 — Prototype ticket (HITL)

**Type:** wayfinder:prototype (HITL)
Status: pending
Spec: docs/specs/example-spec.md
Blocked by: none
Reasoning: medium

### Question

How should the new dashboard surface the circuit-breaker trip state? Build a
rough HTML/CSS prototype showing three trip states (green, amber, red) and a
recovery action so the user can react to a concrete artifact rather than a
text description.

### Resolution

Resolved by `/prototype` skill call, asset linked at
`.agent/prototypes/<ticket-id>-dashboard-trip.html`.

---

## Example 3 — Grilling ticket (HITL)

**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/example-spec.md
Blocked by: none
Reasoning: medium

### Question

Lock the env-var name for the Antigravity binary path override. Candidates:
`AGENT_ANTIGRAVITY_BIN`, `AGENT_ANTIGRAVITY__BIN`, `ANTIGRAVITY_BIN`, `AGY_BIN`.
Each has trade-offs across precedent, portability, and symmetry with future
backends.

### Resolution

Resolved by grilling + domain-modeling skills; decision recorded in
`docs/adr/<NNNN>-<slug>.md`; map updated with context pointer.

---

## Example 4 — Task ticket (HITL or AFK)

**Type:** wayfinder:task (HITL)
Status: pending
Spec: docs/specs/example-spec.md
Blocked by: <other-ticket>
Reasoning: medium

### Question

Plumb the env-var override from Example 3 through `Doctor._check_worker_binary`
with full unit-test coverage (env-var set + valid, env-var set + invalid,
env-var unset + binary on PATH, env-var unset + binary missing) and a gotcha
entry recording the new resolution priority.

### Resolution

Resolved by `/implement` skill call; tests added at
`tests/unit/application/test_doctor.py`; gotcha entry at
`docs/tickets/gotchas.md:<line>`.

---

## Classification cheat sheet

| Type | Suffix | When |
|---|---|---|
| `wayfinder:research` | `(AFK)` | Reading external docs / APIs / sources to surface a fact a decision waits on. Resolved by a subagent; the human agent does NOT pay context on the read. |
| `wayfinder:prototype` | `(HITL)` | Raising fidelity of a discussion by producing a concrete artifact to react to. The human MUST see the artifact and react. |
| `wayfinder:grilling` | `(HITL)` | Conversation. The default type. The agent never stands in for the human's side of it. |
| `wayfinder:task` | `(HITL or AFK)` | Manual work that must happen before a decision can be made. AFK when the agent drives alone; HITL when the human must execute a checklist. |

## Common pitfalls

- **Silent retyping**: an agent that flips `HITL` to `AFK` (or vice versa)
  without an explicit decision has broken the ticket. Reclassification is a
  ticket of its own.
- **Empty Type line**: a ticket with `Status: pending` but no `**Type:**` line
  is **closed** by the convention. The map's chart session MUST set the label
  before any work begins; the work-through session MUST NOT start work on an
  untyped ticket.
- **Map vs ticket**: the map itself (T000 in Spec 15) is not typed. Maps hold
  tickets; tickets carry types.