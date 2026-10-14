# T009 — Lock the Empty-Starter Design
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-08T14:35:33Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

What is the on-disk shape of the "completely empty starter" directory that the user
will use to exercise the runner's scaffolding and startup against a fresh slate?

Three design candidates exist:

- **Pure empty** — only a `.gitkeep`. The user runs `ticket-runner init` against it
  and watches the runner scaffold every artifact.
- **Scaffold-tickets-only** — `ticket-runner init` has already been run; only
  `docs/tickets/<spec-slug>/` exists with starter tickets. The user watches the
  runner execute one starter ticket end-to-end.
- **Minimal-bare** — just `AGENTS.md` and `ticket-runner.yaml` so the runner
  has the minimum required files; the user runs `--local-only smoke` and watches
  the gatekeeper verify nothing.

### Why this matters

The user explicitly requested a "completely empty" state for watching scaffolding
and startup. The design choice determines what files the starter ships with and
what the user can demonstrate.

### Resolution

**Design candidate — Pure Empty.** The directory contains only a `.gitkeep` at
rest. The user runs `ticket-runner init` against it and watches the runner scaffold
every artifact. Chosen over *Scaffold-Tickets-Only* (already covered by the three
other live-test sites) and *Minimal-Bare* (pre-seeds `AGENTS.md` +
`ticket-runner.yaml`, undermining "completely empty"), and consistent with the
ticket Gotcha ("favor candidates that maximize what `ticket-runner init` will
scaffold rather than candidates that pre-seed artifacts").

**Path — `D:\Repos\empty-starter\`** (standalone, sibling to the future
`D:\Repos\agent-runner-driver\`). Not under `D:\Sandbox\` (already scoped to the
onboarding sandbox per T005) and not nested inside the agent-skills driver
(`D:\Repos\agent-runner-driver\empty/`) because the driver already owns its own
`docs/tickets/` resolution root; nesting two live-test sites invites confusion.

**Lifecycle — disposable, rebuilt on demand.** The *act* of scaffolding is the
demonstration; this site is not a reference target. Reset procedure: `rm -rf`
everything except `.gitkeep`, or delete-and-recreate the directory. Mirrors T005's
`--force` factory-reset pattern in spirit (manual here, since no scaffold tool
exists yet for this site).

**VCS hygiene — git repo, `.gitkeep` only tracked.** Own repo (`git init -b main`),
checkout `agent/ticket-runner`, pre-push hook installed via
`PrePushHookInstaller.install()` using `DEFAULT_STANDALONE_HOOK`
(`runner/adapters/git/pre_push_hook.py:24-28`) — same mechanism as T006/T008/T014/T015.
No remote (local test site, matching T015's pattern). Scaffold output is never
committed: throwaway generated files are torn down to reset, and `.agent/` runtime
state is git-ignored.

**Directory tree** (`D:\Repos\empty-starter\`):

```
.gitkeep          (sole tracked file; the empty slate)
.git/             (own repo; main base; agent/ticket-runner branch)
```

### Requirements

- Decide between the three candidates above (or a fourth hybrid).
- Decide the path:
  - Standalone `D:\Repos\empty-starter\`?
  - Under `D:\Sandbox\` alongside the external sandbox?
  - Inside the agent-skills driver (`D:\Repos\agent-runner-driver\empty/`)?
  - Other?
- Decide whether the starter is disposable (rebuilt on demand) or persistent
  (kept around as a reference target).
- Decide whether the starter ships with a `.gitkeep` or a `.gitignore` or
  nothing — the user mentioned "completely empty" which implies minimal
  artifacts.

### Acceptance Criteria

- Chosen design candidate (Pure Empty) is recorded in this ticket's Resolution. ✓
- Chosen path (`D:\Repos\empty-starter\`) is finalized. ✓
- T010 may proceed. ✓

### Gotchas

- "Completely empty" is the user's stated goal — favor candidates that maximize
  what `ticket-runner init` will scaffold rather than candidates that pre-seed
  artifacts.
- T012 (`verify-<app>` skill per site?) — Pure Empty has no app to verify, so this
  site rides on tier-0 smoke. Flag when T012 grills.
- T011 (`live-test-sites.md`) — describe this site as the "fresh-slate scaffolding
  target", distinct from the three content-bearing live-test sites.
- T015 does not block T010: the empty starter and `D:\Repos\agent-runner-driver\`
  are independent siblings.
- This resolves the wayfinder map's open question "Whether the empty starter lives
  alongside `D:\Repos\agent-runner-driver\` or in a separate scratch location" —
  sibling, separate scratch location.