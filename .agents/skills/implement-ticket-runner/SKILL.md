---
name: implement-ticket-runner
description: "Autonomous worker execution skill for Ticket Runner queues: test-driven implementation at jump-start seams, Standards and Spec review with a conditional Security axis, checkbox criteria acknowledgement, and explicit signal durability."
disable-model-invocation: true
---

# Implement Ticket Runner

Autonomous Worker execution discipline for Ticket Runner queues. Orchestrated by `ticket_runner.py` via an AI coding agent backend (OpenCode, Antigravity CLI).

You are an autonomous Worker subprocess executing a single Ticket from `docs/tickets/<spec-slug>/`. Your boundary is strict: you write code and tests, acknowledge satisfied criteria by flipping checkboxes, and emit durable signals. The Gatekeeper independently verifies your work, authors the git commit, relocates completed tickets, and updates `docs/tickets/gotchas.md`.

## Execution Discipline

### 1. Seams & TDD
- Read `AGENTS.md` using your file-reading tool (`read` / `read_file`) to ground your work in repository invariants, even if `AGENTS.md` is preloaded in system rules (Gatekeeper audits tool-call telemetry for this read).
- Locate the active ticket and review `## What to build` and `## Jump-start`.
- Orientation begins at the named `## Jump-start` seams: files/areas to touch, seams to work at, and existing anchors. If exploration reveals additional files, follow where the code leads.
- Drive implementation test-first via red-green-refactor cycles. Write the failing test, verify it fails, write minimal code to pass, and re-verify.

### 2. Verification & Speed
- Run targeted tests for the modified files during development iterations.
- Run the broader test suite once targeted tests pass.
- Target platform is Windows/PowerShell: never pipe to Unix-only commands (`tail`, `grep`, `head`).
- **Stuck-Test-Suite Protocol**: If tests hang or cascade, read `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md` using your file-reading tool (`read` / `read_file`) and follow the Stuck-Test-Suite Protocol. Run the fastest single test file first, check for dangling subprocesses or locks, and isolate the failing seam before retrying.

### 3. Review (Security When Required)
Read `.agents/skills/code-review-ticket-runner/SKILL.md` using your file-reading tool (`read` / `read_file`) before signalling readiness, then evaluate the uncommitted working-tree diff (`git diff HEAD` plus untracked files) across the active axes:
1. **Standards**: Code follows repository coding standards, architectural layers, and Fowler smell baselines.
2. **Spec**: Code matches the ticket requirements in `## What to build` and `## Acceptance criteria` without scope creep.
3. **Security (conditional)**: Run this axis only when the ticket's `Security:` field is `required`, `true`, or `yes`. Audit security by reading `.agents/skills/security-review-ticket-runner/SKILL.md` with your file-reading tool. Do not add it merely because the change touches trust boundaries; those are review checkpoints once the axis is active (ADR 0013).

### 4. Severity-Gated Question Escalation
Handle review findings by severity:
- **Low / Medium findings**: Remediate in code or document in `self_review_notes`. Never block or interrupt the human operator.
- **Critical / High findings**: Remediate immediately in the session and verify tests pass.
- **Blocked Escalation**: If remediation is genuinely blocked by a required human architectural decision, missing external secret/credential, or policy ambiguity (the condition that would be `ready-for-human` in an interactive session), emit a durable question signal to `.agent/questions/<ticket_id>.json` following the schema in the task prompt's `Question Signal Protocol` section. The Gatekeeper will halt at the intervention gate (`WAITING_FOR_USER`) and await the human operator's response on Discord or Terminal before resuming.

### 5. Checkbox Criteria Acknowledgement & Permission Boundary
- In the active ticket file, flip satisfied criteria from `- [ ]` to `- [x]` under `## Acceptance criteria`.
- **STRICT BOUNDARY**: You may ONLY change `- [ ]` to `- [x]` inside `## Acceptance criteria`.
- You must **NEVER** edit the ticket header, `## What to build`, `## Jump-start`, criterion text, `## Smoke scenarios`, or `## Gotchas`.
- The Gatekeeper captures a pre-dispatch baseline of the ticket file before execution. Any unauthorized change to the ticket will cause the Gatekeeper to reject your ready signal, restore the ticket file, and consume a verification attempt.

### 6. Signal Readiness (Never Commit or Relocate)
- When all targeted tests pass, broad tests pass, criteria are ticked, and reviews are clean:
  - Confirm you have read `AGENTS.md`, `.agents/skills/code-review-ticket-runner/SKILL.md`, and (when `Security:` is required) `.agents/skills/security-review-ticket-runner/SKILL.md` using your file-reading tool (`read` / `read_file`) during this session.
  - You must **NEVER** run `git commit`.
  - You must **NEVER** relocate ticket files to `completed/`.
  - You must **NEVER** edit `docs/tickets/gotchas.md`.
  - Gatekeeper owns commits, ticket relocation, and gotchas logging exclusively.
- Emit your completion signal by writing `.agent/signals/<ticket_id>_ready.json` following the schema in the task prompt's `Ready Signal Protocol` section.
