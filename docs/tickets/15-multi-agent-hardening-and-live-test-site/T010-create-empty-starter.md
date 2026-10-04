# T010 — Create the Empty Starter
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T009
Reasoning: low

### Question

Execute the design decision locked in T009: create the empty starter directory at
the agreed path.

### Why this matters

T009 specifies what shape the starter should have; T010 actually creates it.

### Requirements

- Create the directory at the path T009 locked.
- Apply the design T009 locked:
  - If "pure empty": write only `.gitkeep` (so the directory exists on disk and is
    visible to `git` / `ls`).
  - If "scaffold-tickets-only": run `ticket-runner init` then prune everything
    except `docs/tickets/<spec-slug>/`.
  - If "minimal-bare": write only `AGENTS.md` and `ticket-runner.yaml` with
    minimum-viable content.
- If the starter is its own git repo: `git init -b main`, branch
  `agent/ticket-runner`, install pre-push hook (matching T006/T008).
- If the starter is NOT a git repo: do not initialize one. The user will initialize
  git inside the starter if they choose.

### Acceptance Criteria

- The directory exists at the agreed path.
- The directory contains only the artifacts T009 specified.
- If git-init was part of the design: `git log` shows the scaffold commit (or
  nothing if T009 said no initial commit).

### Smoke Scenarios

**Scenario: Empty starter scaffolded per T009 design**

- Setup: None.
- Why: Verify the starter matches the T009 spec.
- Steps:
  1. List the contents of the starter directory.
  2. If git-init was part of the design: `git log --oneline`.
  3. If `ticket-runner init` is runnable against it: run it and observe the
     scaffold output.
- Expected: Step 1 matches the agreed design; Step 2 shows the expected commit;
  Step 3 shows the runner scaffolding the empty starter (this is the user's stated
  goal — watching the runner scaffold and startup).

### Gotchas

- "Completely empty" means minimal artifacts. Do not over-engineer this
  directory.