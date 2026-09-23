# T091 — Update AGENTS.md with External Invariants & Verification Guardrails
Status: pending
Spec: docs/specs/10b-living-documentation-and-roadmap.md
Blocked by: T090
Reasoning: medium

### Requirements
- Update `AGENTS.md` to document new system invariants and operational guardrails:
  1. **External Path Resolution Invariant**: Runner execution treats the Target Project as `CWD`. All paths inside `.agent/` and `docs/` resolve relative to the Target Project root, never assuming the runner's source repository is the working tree.
  2. **Token-Preserving Verification Guardrails**: Behavioral verification harnesses run out-of-band. Raw logs, screenshots, and DOM snapshots are saved to `.agent/evidence/<ticket_id>/` and never dumped into the LLM context. On failure, only a bounded 30-line / 1,000-character excerpt is provided.
  3. **Human-in-the-Loop Gate Invariant**: In Human-in-the-Loop mode, Gatekeeper verification halts after green checks to present an Evidence Card via the active presence channel (Terminal prompt or Discord Status Card); commits strictly require human approval.
  4. **Spec-Closing Alignment Ticket Rule**: Every spec queue under `docs/tickets/<spec-slug>/` must include a final closing ticket tasked with auditing implementation against the spec and updating root living documents if any architectural details shifted.
  5. **Interactive Mode Parity**: Update the execution workflow to note that human approval occurs prior to commit in both interactive and autonomous modes.

### Acceptance Criteria
- `AGENTS.md` Invariants section includes the External Path Resolution Invariant, Token-Preserving Verification Guardrail, Human-in-the-Loop Gate Invariant, and Spec-Closing Alignment Ticket Rule.
- The document conforms to the `writing-for-agents` discipline (clear completion bounds, leading words, positive prompts).
### Suggested Skills
- `writing-for-agents`: Positive prompts over prohibitions, eliminating no-ops, preserving agent context budget.

### Smoke Scenarios
**Scenario: Verify AGENTS.md Invariants and Rules**
- Setup: None (runs from repo root).
- Why: Ensure coding agents following `AGENTS.md` abide by the new external pathing, token budgeting, and approval rules.
- Steps:
  1. Read `AGENTS.md` under `## Invariants`.
  2. Verify that the 30-line verification failure bound is documented.
  3. Verify that the closing alignment ticket requirement is stated clearly.
- Expected: All four new invariants are documented clearly with positive guidance.

### Gotchas
- Keep `AGENTS.md` lean: avoid verbose prose that bloats agent context windows; use tight leading words.
