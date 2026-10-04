# T014 — Clone Viello/agent-skills and Install Pre-Push Hook
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T013
Reasoning: medium

### Question

Execute the clone and hook installation locked in T013.

### Why this matters

The skills clone is the real upstream Target Project the agent-skills driver
operates against. Without a clean clone with the pre-push hook installed, ticket
execution against the skills repo is unsafe.

### Requirements

- Create `D:\Repos\` if it does not exist.
- Run `git clone https://github.com/Viello/agent-skills D:\Repos\agent-skills`.
  Confirm HEAD matches the chart-time SHA `e4eb54cd006a66229020009898035a5289ac7e73`
  (or current upstream HEAD if it has advanced; document the actual SHA in the
  ticket's resolution comment).
- Inside the clone:
  - `git checkout -b agent/ticket-runner` (or equivalent to create the
    ticket-runner branch from current `main`).
  - Install the pre-push hook via the same `runner/adapters/git/pre_push_hook.py`
    mechanism used by T006/T008.
  - Verify `.git/hooks/pre-push` contains the guardrail block.
- Add `.agent/` to the clone's `.gitignore` if not already present (existing
  patterns from the upstream may already cover this; verify).
- Add `docs/tickets/.queue.lock` to the clone's `.gitignore` if not present.
- Do NOT modify any source files in the clone yet — the agent-skills driver
  scaffolds will go through T015 and T016-T017.

### Acceptance Criteria

- `D:\Repos\agent-skills\` exists as a git repo with origin pointing at
  `https://github.com/Viello/agent-skills`.
- HEAD commit SHA recorded in the ticket's resolution comment.
- `agent/ticket-runner` branch exists locally.
- `.git/hooks/pre-push` contains the guardrail block.

### Smoke Scenarios

**Scenario: Skills clone is wired with pre-push guardrail**

- Setup: None (verifies T014's work).
- Why: Confirm the clone is safe for ticket execution.
- Steps:
  1. From `D:\Repos\agent-skills`, run `git remote -v` and confirm origin matches.
  2. From `D:\Repos\agent-skills`, run `git branch` and confirm
     `agent/ticket-runner` exists.
  3. From `D:\Repos\agent-skills`, attempt `git push origin agent/ticket-runner`
     (will fail; that's the test) and confirm the pre-push hook blocks with the
     guardrail message.
- Expected: Step 1 shows the upstream URL; Step 2 lists the branch; Step 3 fails
  with the guardrail message.

### Gotchas

- Do NOT push to `origin` — the pre-push hook should block any attempt, and the
  "Never `git push`" invariant applies regardless of the hook.
- The clone's `.gitignore` may already include `.agent/` and similar patterns
  from upstream. Verify before adding duplicates.