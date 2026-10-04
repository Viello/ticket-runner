# T005 — Lock Layout of `D:\Sandbox\ticket-runner-live-target\`
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-04T18:30:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

What is the exact on-disk layout of the external sandbox at
`D:\Sandbox\ticket-runner-live-target\`? This includes the git branch convention,
scaffold commands, smoke-test entry point, and what minimal Target Project shape the
sandbox holds.

### Why this matters

`D:\Sandbox\ticket-runner-live-target\` is the on-disk landing pad a first-time
Ticket Runner user can point `ticket-runner --project-dir` at. Without a documented
layout, every scaffold session invents its own conventions, drifting over time.
The pattern is partially established by
`tests/specs/test_spec_11_decoupled_runner.py:76-100` (`_seed_external_target_repo`),
but no live, persistent site exists yet.

### Resolution

**Role** — realistic user-facing onboarding sandbox (not a disposable playground).
A first-time Ticket Runner user should land in a polished tree that demonstrates the
worker/gatekeeper flow against a real, runnable Python sample, with a trivial ticket
queued for them to watch execute end-to-end.

**Directory tree** (`D:\Sandbox\ticket-runner-live-target\`):

```
.agent/{signals,questions,logs,checkpoints,evidence,archive}/
.agents/skills/{implement,code-review,diagnosing-bugs,handoff}/SKILL.md
docs/tickets/00-welcome/T001-hello-world.md
src/sample_app/__init__.py
tests/test_smoke.py
AGENTS.md                       (5-line preamble + curated subset of D:\Projects/AGENTS.md)
ticket-runner.yaml              (provider: antigravity)
.gitignore                      (.agent/, docs/tickets/.queue.lock)
.git/                           (own repo; main base; agent/ticket-runner branch)
```

**Git layout** — own repo (`git init -b main`), checkout `agent/ticket-runner`,
pre-push hook installed via `PrePushHookInstaller.install()` using
`DEFAULT_STANDALONE_HOOK` (`runner/adapters/git/pre_push_hook.py:24-28`) — self-
contained, no dependency on `D:\Projects\scripts/pre-push.sh` being on disk at
install time.

**Smoke-test entry point** —
`ticket-runner --project-dir D:\Sandbox\ticket-runner-live-target\ doctor`.

**`ticket-runner.yaml`** —
`worker.provider: "antigravity"` (matches `D:\Projects/config.yaml:13`; exercises
the post-T018 hardened `AGENT_ANTIGRAVITY_BIN` path on every doctor run).

**Persistence policy** — persistent primary; rebuild via
`python -m runner.tools.scaffold_sandbox --force` (or `ticket-runner-scaffold-sandbox`
console-script alias from `pyproject.toml`). Default mode is idempotent (fills gaps,
leaves existing files alone); `--force` is destructive (wipes + regenerates).

**AGENTS.md shape** — 5-line "Welcome to your Ticket Runner sandbox" preamble
followed by a curated subset of `D:\Projects/AGENTS.md` containing only the
invariant-bearing sections (branch, commit format, pre-push, single-commit-per-
ticket, token budget, source-of-truth, runner-developer-only sections like Discord,
Supabase, Vercel, Tailwind). Stamped at the top with `<!-- mirrored from
D:\Projects/AGENTS.md on YYYY-MM-DD -->` so drift is detectable. Exact subset to
be enumerated by T005c.

**Initial commit message** — `chore(sandbox): initialize ticket-runner onboarding
sandbox` (drops "disposable" from T006's originally-suggested text to match the
user-facing framing). No ticket number in title or body.

**Sync script** — `scripts/sync_agents_md.py` runs upstream to sandbox, reports
drift. Bidirectional sync rejected (sandbox must never edit upstream invariants).

### Acceptance Criteria

- This ticket's resolution comment captures the layout decision in concrete terms:
  - Directory tree. ✓
  - Git branch convention. ✓
  - Smoke-test entry point command. ✓
  - Provider setting in `ticket-runner.yaml`. ✓
  - Persistence vs rebuild policy. ✓
- T005a, T005b, T005c, T006 may proceed.

### Gotchas

- The sandbox's `.gitignore` is independent of `D:\Projects\.gitignore` — they are
  separate git repos.
- The pre-push hook guardrail blocks pushes from `agent/ticket-runner` per
  `docs/adr/0005-local-pre-push-git-hook.md`. The sandbox must have this installed
  before any ticket execution.
- The sandbox is **persistent primary**, not throwaway. `--force` exists for
  factory-reset scenarios (a user wants to start over), not routine use.
- The curated AGENTS.md subset omits sections that target a Ticket Runner
  *developer* (Discord bot setup, Supabase MCP guidance, Vercel deploy commands).
  A first-time user trying the product does not need them; including them invites
  confusion ("why am I setting up Discord in a throwaway tree?").