# T007 — Lock In-Repo Harness Layout and `.gitignore` Rules
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

What is the exact on-disk layout of the in-repo debugging harness at
`D:\Projects\live-test-target/`? This includes git branch convention, scaffold
shape, and how to keep it isolated from `D:\Projects\.git` (its own repo? a
worktree? a submodule?).

### Why this matters

The harness lives *inside* `D:\Projects` but must NOT be part of the runner source
git history — committing a git branch on top of `D:\Projects\.git` would either:

- Pollute the runner source repo with test artifacts.
- Or require a separate git repo nested inside (which `git` doesn't support
  cleanly without submodules or worktrees).

Decide the isolation mechanism.

### Requirements

- Decide the layout:
  - Path: `D:\Projects\live-test-target/` (sibling of `runner/`, `tests/`, `docs/`).
  - Own `.git/` (separate repo, NOT a submodule).
  - Branch: `agent/ticket-runner` (per AGENTS.md invariant).
- Decide isolation mechanism:
  - Add `live-test-target/` to `D:\Projects\.gitignore` so the runner's source
    repo ignores it entirely.
  - Optionally add a sentinel marker (e.g. `live-test-target/.isolated`) to make
    the isolation intent explicit.
- Decide scaffold shape:
  - Same as the external sandbox (T006): `.agent/`, `docs/tickets/`,
    `.agents/skills/`, `AGENTS.md`, `ticket-runner.yaml`.
  - Same pre-push hook installation.
  - Same `agent/ticket-runner` branch convention.
- Decide role distinction:
  - The in-repo harness exists for SELF-TESTING ticket-runner against a known
    internal target.
  - The external sandbox (T006) exists for disposable experiments.
  - The agent-skills driver (T015) exists for real-world workflow tickets.
- Decide whether the harness ships with a starter ticket queue or stays empty.

### Acceptance Criteria

- The `.gitignore` rule is finalized (T008 will append it).
- The layout, branch, and scaffold shape are recorded in the ticket's resolution
  comment.
- T008 may proceed.

### Gotchas

- The harness MUST be its own git repo, not a submodule — worktrees complicate the
  pre-push hook installer.
- The harness's `.gitignore` must include `.agent/` and
  `docs/tickets/.queue.lock` (same rules as the external sandbox).