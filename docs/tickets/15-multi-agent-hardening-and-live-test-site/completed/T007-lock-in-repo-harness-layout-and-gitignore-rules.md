# T007 — Lock In-Repo Harness Layout and `.gitignore` Rules
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-08T00:00:00Z
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

### Resolution

**Role** — Self-test seat for the runner developer. Internal target, persistent
primary; not an onboarding sandbox (T005), not a real-upstream driver (T015).
The developer points the runner at it to iterate on runner code against a known,
internal Target Project without leaving `D:\Projects\`.

**Path** — `D:\Projects\live-test-target/` (sibling of `runner/`, `tests/`,
`docs/`).

**Git layout** — own repo (`git init -b main`), checkout `agent/ticket-runner`,
self-contained pre-push hook via `PrePushHookInstaller.install()` using
`DEFAULT_STANDALONE_HOOK` (matches T005; no dependency on
`D:\Projects\scripts\pre-push.sh` being on disk). Pushing from
`agent/ticket-runner` is blocked per `docs/adr/0005-local-pre-push-git-hook.md`
— same invariant as every other live-test site.

**Isolation mechanism** — two layers, both in place:
- `D:\Projects\.gitignore:13` already contains the `live-test-target/` rule
  (Spec 15, line 12 comment). Confirmed live; T008's gotcha about idempotent
  append still applies on re-run.
- Sentinel marker `D:\Projects\live-test-target/.isolated` (one line) makes
  the isolation intent explicit on `ls` and prevents a future contributor from
  "fixing" the missing-from-`git-status` tree by `git add`-ing it back into
  the runner source repo.

**Scaffold shape** —
```
D:\Projects\live-test-target\
├── .agent/{signals,questions,logs,checkpoints,evidence,archive}/
├── .agents/skills/{implement,code-review,diagnosing-bugs,handoff}/SKILL.md
├── .git/                               (own repo; main base; agent/ticket-runner branch)
├── .gitignore                          (full T005 set; see below)
├── .isolated                           (sentinel; one-line explanation)
├── AGENTS.md                           (one-line terse preamble; no curation, no sync stamp)
├── docs/tickets/                       (empty — developer authors self-test tickets on demand)
└── ticket-runner.yaml                  (worker.provider: "antigravity")
```

**`ticket-runner.yaml`** — `worker.provider: "antigravity"` (matches
`D:\Sandbox\ticket-runner-live-target\ticket-runner.yaml:7` and
`D:\Projects\config.yaml:13`). Consistency across the three non-empty live-test
sites makes doctor output comparable; a single T018 regression surfaces in all
three. Other keys may mirror T005's example verbatim.

**`AGENTS.md` content** — single line, no preamble, no upstream-curated subset,
no sync stamp:
```
Self-test harness for ticket-runner — see D:\Projects/AGENTS.md for invariants.
This directory is its own git repo (gitignored from D:\Projects\).
```
The developer opening this directory is two folders away from the canonical
`D:\Projects/AGENTS.md`; mirroring it back is busywork and risks drift if a
curator forgets to re-sync. The terse one-liner makes the isolation explicit
and points to the source of truth.

**`D:\Projects\live-test-target\.gitignore`** — full T005 set (cheap insurance
against future self-test tickets that author Python here):
```
.agent/
docs/tickets/.queue.lock
__pycache__/
*.pyc
.pytest_cache/
```

**Starter ticket queue** — empty. A pre-seeded self-test ticket would pre-empt
the developer's own iteration loop and force a delete step on every scaffold.
The whole point of "in-repo" is fast iteration; make the developer author
what they want to test.

**Persistence policy** — persistent primary, same as T005. Accumulated
self-test tickets are the developer's record of what they've already verified;
a throwaway would lose that audit trail. Runtime state (`.agent/`,
`docs/tickets/.queue.lock`) is gitignored, so persistence costs nothing. No
`--force` rebuild script is provided (unlike T005's `scaffold_sandbox.py`):
the harness's runtime is gitignored, so factory-reset is a manual `rm -rf
.agent/ docs/tickets/.queue.lock`.

**Initial commit message** —
`chore(harness): initialize ticket-runner in-repo self-test harness`
(no ticket number in title or body, per `AGENTS.md` commit-format invariant).
Hand-authored under the T006/T008/T015 exception pattern (no Gatekeeper has
run yet for this repo).

### Acceptance Criteria

- The `.gitignore` rule is finalized (T008 will append it). ✓ (already live
  at `D:\Projects\.gitignore:13`)
- The layout, branch, and scaffold shape are recorded in the ticket's resolution
  comment. ✓
- T008 may proceed. ✓ (unblocked)

### Gotchas

- The harness MUST be its own git repo, not a submodule — worktrees complicate the
  pre-push hook installer.
- The harness's `.gitignore` must include `.agent/` and
  `docs/tickets/.queue.lock` (same rules as the external sandbox).
- The `.gitignore` append must be idempotent — T008 should check for an existing
  `live-test-target/` line before appending. (Currently the rule is present;
  T008's gotcha still applies on re-run.)
- The in-repo harness and the external sandbox differ in **role** (self-test vs.
  onboarding) but share **configuration** (`worker.provider: "antigravity"`,
  `agent/ticket-runner` branch, self-contained pre-push hook). T008 must not
  drift the two sites' configs without an explicit decision in a follow-up
  ticket.