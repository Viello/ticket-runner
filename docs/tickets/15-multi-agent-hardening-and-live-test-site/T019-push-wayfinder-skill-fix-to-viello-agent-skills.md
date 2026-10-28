# T019 — Push the Wayfinder Skill Fix to Viello/agent-skills Main
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T014, T018
Reasoning: medium

### Question

Mirror the patched wayfinder skill (`D:\Projects\.agents\skills\wayfinder\SKILL.md`
+ the worked-example ticket at `.agents/skills/wayfinder/examples/example-ticket-types.md`)
into the agent-skills clone at `D:\Repos\agent-skills\.agents\skills\wayfinder\`,
prepare a commit on the `agent/ticket-runner` branch in that clone, and push
directly to `main` on `https://github.com/Viello/agent-skills` so the public
catalog inherits the Type-label convention locked by ADR-0023.

### Why this matters

ADR-0023 binds the propagation of the patched skill to the public catalog as
part of the convention itself — not as an optional mirror. Future tickets
across the agent-skills repo (and any downstream project that vendors its
skills) carry the `**Type:**` line by default only if the patched skill reaches
the public repo. Without this ticket, the convention lives only in
`D:\Projects\.agents\skills\wayfinder\`, a private vendor.

### Requirements

- Verify T014 has produced the agent-skills clone at `D:\Repos\agent-skills\`
  (this ticket blocks on T014).
- Verify T018 has produced the final local wayfinder skill fix
  (this ticket blocks on T018 — the local fix must be final, not provisional).
- Stage the mirrored files in the clone:
  - `D:\Repos\agent-skills\.agents\skills\wayfinder\SKILL.md` ← updated
    `D:\Projects\.agents\skills\wayfinder\SKILL.md`.
  - `D:\Repos\agent-skills\.agents\skills\wayfinder\examples\example-ticket-types.md`
    ← new worked example from `D:\Projects\.agents\skills\wayfinder\examples\`.
- Run the diff first; surface it to the user for one final read.
- Author a commit on the `agent/ticket-runner` branch in the clone. Commit
  message MUST follow `D:\Projects\AGENTS.md` commit-format invariant
  (`<type>(<scope>): <Title>` with no ticket numbers): e.g.
  `chore(skills): carry wayfinder ticket type-label convention from local vendor`.
- Push the commit directly to `main` on `https://github.com/Viello/agent-skills`
  per the user's locked decision (chart session, plan-mode Q2 answer).
- Emit a durable signal at `D:\Repos\agent-skills\.agent\signals\T019_ready.json`
  per AGENTS.md signal invariant summarizing:
  - Commit SHA pushed.
  - Files mirrored.
  - Commit message used.
  - Timestamp.
  - Operator hint: `login` if the agent-skills driver has its own
    GitHub-credentials story; `noop` if pushed via the user's local Git
    credentials.
- Update the agent-skills clone's CHANGELOG or release notes (if such a file
  exists in the upstream repo) with a one-line note about the convention change.

### Acceptance Criteria

- `D:\Repos\agent-skills\.agents\skills\wayfinder\SKILL.md` exists and matches the
  patched local vendor.
- `D:\Repos\agent-skills\.agents\skills\wayfinder\examples\example-ticket-types.md`
  exists.
- Commit pushed to `main` on `https://github.com/Viello/agent-skills`.
- Durable signal emitted at `D:\Repos\agent-skills\.agent\signals\T019_ready.json`.
- The patch is visible on GitHub at
  `https://github.com/Viello/agent-skills/blob/main/.agents/skills/wayfinder/SKILL.md`
  (or equivalent path; verify against the actual repo structure on clone).

### Smoke Scenarios

**Scenario: Wayfinder skill fix lands on the public catalog**

- Setup: T014 + T018 both closed; user available to confirm the final diff
  before push.
- Why: Verify the propagation succeeds and the change is live on GitHub.
- Steps:
  1. From `D:\Repos\agent-skills`, run `git diff main` (or whatever the local
     branch compares against).
  2. Surface the diff to the user for final review.
  3. After user approval, push to `main` on GitHub.
  4. Confirm the GitHub URL renders the updated `SKILL.md` and the new
     `examples/example-ticket-types.md`.
- Expected: Step 1 shows only the intended changes; Step 3 succeeds; Step 4
  confirms the public catalog reflects the patched skill.

### Gotchas

- The agent-skills repo's `main` branch is being pushed to directly — no feature
  branch / PR review. The user explicitly chose this in chart session
  (option 1, push strategy). The pre-push hook on `D:\Projects` does NOT apply
  to `D:\Repos\agent-skills` (separate repo).
- The user owns `Viello/agent-skills`; pushing directly to `main` is the user's
  call. T019 surfaces the diff for one final read before push, but does NOT
  require explicit approval — the user already approved the strategy in chart.
- If `D:\Repos\agent-skills/.agents/skills/wayfinder/` does not yet exist in
  the upstream (i.e., the wayfinder skill is local-only), T019 creates it via
  the standard git add + commit flow. Verify the upstream structure on clone.
- T099 must include T019 in its blocking list (audit must cover the public
  catalog change too).