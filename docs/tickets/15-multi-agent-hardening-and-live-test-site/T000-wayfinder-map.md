# Spec 15 — Multi-Agent Hardening & External Live-Test Site

## Destination

Close the Antigravity integration gaps AND land a four-part external live-test
site cluster:

1. **`D:\Sandbox\ticket-runner-live-target\`** — disposable external sandbox for one-off
   experiments.
2. **`D:\Projects\live-test-target/`** — in-repo debugging harness for self-test
   (git-ignored from `D:\Projects`).
3. **`D:\Repos\agent-runner-driver\`** → driving **`D:\Repos\agent-skills\`** (a clone of
   `https://github.com/Viello/agent-skills`) — a real upstream Target Project where the
   agentic-coding workflow operates against a live skills catalog, with the option of
   replacing `scripts/publish_agent_skills.py` with a ticket-driven publication flow.
4. **(TBD)** — a completely-empty starter directory used to exercise the runner's
   scaffolding and startup against a fresh slate.

### Antigravity scope (revised after T002 research)

The originally proposed "three hardening gaps" turned out to be one critical fix
plus two hardening items:

- **T018 (critical fix)** — the existing
  `runner/adapters/antigravity/antigravity_worker.py:55` hardcodes
  `cmd = ["agy", "run", "--auto", prompt]` but `agy` has no `run` subcommand and
  no `--auto` flag. Every existing call fails immediately with exit code 2.
  T018 rewrites the adapter to the empirical surface captured by T002
  (`agy -p "<prompt>" --output-format stream-json --effort <level> --model <slug>
  --conversation <uuid> --print-timeout <dur>`).
- **T003 (hardening)** — add `test_live_antigravity_smoke.py` gated on
  `TICKET_RUNNER_LIVE=1` (post-T018).
- **T001 + T004 (hardening)** — env-var path override `AGENT_ANTIGRAVITY_BIN`
  (and symmetric `AGENT_OPENCODE_BIN`) through Doctor pre-flight.

When this map's last ticket (the spec-closing alignment ticket, T099) closes, a
developer should be able to:

- Run `pytest tests/unit/adapters/test_live_antigravity_smoke.py` (gated on
  `TICKET_RUNNER_LIVE=1`) against a real `agy` binary and get a green signal.
- Set `AGENT_ANTIGRAVITY_BIN=/custom/path/to/agy` and have the Doctor pre-flight use it.
- Set `AGENT_OPENCODE_BIN=/custom/path/to/opencode` symmetrically.
- Point the runner at any of the four live-test sites and watch the full scaffolding →
  doctor → ticket-loop → gatekeeper → commit pipeline execute end-to-end.

## Notes

- **Domain**: Ticket Runner's multi-agent adapter layer (`runner/adapters/antigravity/`,
  `runner/adapters/opencode/`), the `Doctor` pre-flight (`runner/application/doctor.py`),
  the external `--project-dir` mechanism (Spec 11), and the live-test scaffolding
  discipline (Spec 12).
- **Skills every session should consult**: `grilling`, `domain-modeling`, `implement`,
  `create-verification-skill` (if T012 resolves "yes"), `maintain-verification-skill`
  (post-creation).
- **Standing preferences** (per `AGENTS.md` invariants):
  - No commit-numbered titles; `<type>(<scope>): <Title>` only.
  - Single commit per ticket authored by the Gatekeeper.
  - `.agent/` is untracked runtime state — git-ignore it when implementing.
  - Source-of-truth hierarchy: working code + tests + CLI interfaces > markdown
    documentation.
  - Spec-closing alignment ticket (T099) audits and updates root living documents
    (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`) only if architectural details shifted.
  - Never `git push`; `.git/hooks/pre-push` blocks pushes on `agent/ticket-runner`.
  - Worker never commits directly; Gatekeeper alone commits.
- **External project root resolution**: all `.agent/`, `docs/tickets/`,
  `.agents/skills/`, and `ticket-runner.yaml` paths resolve relative to the Target
  Project root, not to the Runner source repo.

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [T001 — Confirm `AGENT_ANTIGRAVITY_BIN` and write ADR-0023](completed/T001-confirm-agent-antigravity-bin-env-var-and-adr-0023.md):
  locked single-underscore family convention `AGENT_ANTIGRAVITY_BIN` (and symmetric
  `AGENT_OPENCODE_BIN`); rejected double-underscore (`__`) per Rails/pydantic-settings
  nested-key precedent being inapplicable to flat category:provider:field triples;
  resolution priority is env-var → `shutil.which`; case-sensitive (POSIX); fail loud
  if env-var points at invalid path. Research: branch `research/agent-backend-env-var-convention`
  (commit `652b209`).
- [T002 — Empirical `agy` CLI flag surface](completed/T002-empirical-agy-cli-flag-surface.md):
  `agy` 1.2.16 has no `run` subcommand and no `--auto` flag; canonical invocation is
  `agy -p "<prompt>" --output-format stream-json [--effort low|medium|high|xhigh|max]
  [--model <slug>] [--continue|--conversation <uuid>] [--print-timeout <dur>]`;
  NDJSON envelope is `event: {init, step_update, result}`; usage at
  `step_update.usage` / `result.usage` with keys `input_tokens` / `output_tokens` /
  `thinking_tokens` / `cache_read_tokens` / `total_tokens`; session id is
  `conversation_id` (UUID, not `ses_*`); exit codes 0/1/2/3. **Comprehensive drift
  between adapter and reality → new ticket T018.** Research: branch
  `research/agy-flag-surface` (commit `0c30f9a`).
- [T005 — Lock the layout of `D:\Sandbox\ticket-runner-live-target\`](completed/T005-lock-layout-of-external-sandbox.md):
  realistic user-facing onboarding sandbox (not a disposable playground); own git
  repo (`main` base, `agent/ticket-runner` branch); pre-push hook via
  `PrePushHookInstaller.install()` self-contained default; smoke test
  `ticket-runner --project-dir D:\Sandbox\ticket-runner-live-target\ doctor`;
  `worker.provider: "antigravity"`; persistent primary, rebuild via
  `python -m runner.tools.scaffold_sandbox --force` (or
  `ticket-runner-scaffold-sandbox` console-script); 4 skills
  (`implement`, `code-review`, `diagnosing-bugs`, `handoff`); ships with sample
  `src/sample_app/` + `tests/test_smoke.py` + one trivial ticket
  `docs/tickets/00-welcome/T001-hello-world.md` so doctor and the worker flow have a
  real, runnable demo; AGENTS.md is a 5-line preamble + curated subset of
  upstream invariants (Discord/Supabase/Vercel/Tailwind sections omitted),
  stamped with sync date; `scripts/sync_agents_md.py` does one-way drift
  detection; initial commit `chore(sandbox): initialize ticket-runner onboarding
  sandbox`.
- [T005c — Lock the curated `AGENTS.md` subset and preamble](completed/T005c-lock-curated-agents-md-subset.md):
  locked preamble (5 lines, opens "Welcome to your Ticket Runner sandbox…", no
  top-level heading) and sync stamp `<!-- mirrored from D:\Projects/AGENTS.md on
  YYYY-MM-DD -->`; section rubric (`## Invariants` + `## Environment` + `## Agent
  skills` included verbatim-or-trimmed; `## Implementation status`,
  `## Read before designing`, `## Development workflow`, and the opening
  paragraph excluded); bullet-trim tables for `## Environment` (1 of 4 kept) and
  `## Agent skills` (2 of 4 kept in default mode, all 4 in `sandbox.skills: all`
  mode); scaffold_sandbox.py aligned: `INCLUDED_HEADINGS = ("## Invariants",
  "## Environment", "## Agent skills")`, new bullet-trim constants, `skills_mode:
  Literal["default", "all"]` parameter on `extract_curated_subset` and `scaffold`,
  `--skills {default,all}` CLI flag, fallback curated-subset updated to match;
  `scripts/sync_agents_md.py` mirrors the `--skills` flag.
- [T005d — Add `sandbox.skills` config flag for skill catalog mode](completed/T005d-add-sandbox-skills-config-flag.md):
  locked nested `sandbox.skills: default|all` key (Q1=a) with mode-resolution
  priority CLI > `ticket-runner.yaml` > `"default"` mirrored in both
  `scaffold_sandbox` and `sync_agents_md` (Q2=a); scaffold self-documents the
  mode it used (Q3=a); contract-only — `all`-mode catalog enumeration deferred to
  a follow-up, flagged by `[scaffold] all mode: … deferred to T005d-impl` (Q4=c);
  the `sandbox.skills` line carries a flip-and-re-sync footnote (Q5=b); new
  `sync_agents_md --apply` opt-in auto-rewrites on YAML-mode drift (Q6=b);
  `worker.execution_skill` is unaffected — the flag governs bullet trim only.
- [T009 — Lock the empty-starter design](completed/T009-lock-empty-starter-design.md):
  **Pure Empty** candidate (directory ships only `.gitkeep`; user runs
  `ticket-runner init` and watches every artifact scaffold); standalone path
  `D:\Repos\empty-starter\` (sibling to the future agent-skills driver, not under
  `D:\Sandbox\`, not nested in the driver); **disposable** lifecycle (reset via
  `rm -rf` except `.gitkeep`, or delete-and-recreate); own git repo on
  `agent/ticket-runner` with `DEFAULT_STANDALONE_HOOK` pre-push, no remote, and
  `.gitkeep` as the only tracked file (scaffold output never committed). Resolves
  the map's open question on where the empty starter lives.

## Not yet specified

<!-- in-scope fog that can't yet be ticket-sized; graduates as the frontier advances -->

- ~~Whether `AGENT_OPENCODE_BIN` ships symmetrically in T004 alongside
  `AGENT_ANTIGRAVITY_BIN`~~ — resolved by T001: yes, both.
- Whether the agent-skills driver becomes the canonical live-test site documented in
  `live-test-sites.md`, or whether all four sites are presented equally.
- Whether `scripts/publish_agent_skills.py` (current manual one-off publication to
  Viello/agent-skills) is replaced by a ticket-driven publication flow in the agent-skills
  driver, or whether the two coexist.
- ~~Whether the empty starter lives alongside `D:\Repos\agent-runner-driver\` or in a
  separate scratch location~~ — resolved by T009: standalone `D:\Repos\empty-starter\`,
  a sibling of the driver.
- Whether the agent-skills driver needs its own `.gitignore` in
  `D:\Repos\agent-runner-driver\.gitignore` or relies on the runner's defaults.
- Whether the agent-skills driver's `--project-dir` setup is replicated via a
  `ticket-runner.yaml` `project_dir:` key (per Spec 11) instead of a CLI flag.
- Whether the empty starter needs its own `verify-<app>` skill or rides on tier-0 smoke.
- **Session-id allowlist decision (T018 internal)**: agy emits UUIDs as
  `conversation_id`, not the `ses_<alphanumeric>` shape. Two options surfaced —
  relax `SESSION_ID_PATTERN` to accept both, or translate inside the adapter.
  Needs a grilling ticket if T018 cannot resolve it inline.
- **T018 timing relative to live-test work**: T018 must land before any Antigravity
  smoke test (T003) or live-test execution. Live-test site work (T005-T017) can
  proceed in parallel with T018 since their scaffolds do not depend on a working
  Antigravity backend.

## Out of scope

<!-- scope, not sharpness — ruled beyond the destination -->

- A third agent backend (Claude Code, Aider, Cursor, etc.) — separate effort.
- Refactoring the `AgentWorker` port or the `WorkerSupervisor` interactor.
- Replacing Ticket Runner's `docs/tickets/` queue with the wayfinder skill's
  `.scratch/` local-markdown tracker.
- Publishing the live-test sites or making them reproducible across machines.
- Adding CI to publish jobs; running the agent-skills driver in continuous integration.
- Migrating `scripts/publish_agent_skills.py`'s caller code paths wholesale — T016 may
  flag it as a target but the migration itself is out of scope.

<!-- ticket index: every ticket carries a Type label per ADR-0023; maps are untyped -->

<!-- T001 — Confirm `AGENT_ANTIGRAVITY_BIN` and write ADR-0023 — CLOSED — wayfinder:grilling (HITL)
- T002 — Empirical `agy` CLI flag surface — CLOSED — wayfinder:research (AFK)
- T003 — Add `test_live_antigravity_smoke.py` — wayfinder:task (AFK) — blocked by T018
- T004 — Plumb `AGENT_ANTIGRAVITY_BIN` and `AGENT_OPENCODE_BIN` through Doctor — wayfinder:task (HITL) — blocked by T001 (unblocked)
- T005 — Lock the layout of `D:\Sandbox\ticket-runner-live-target\` — CLOSED — wayfinder:grilling (HITL)
- T005a — Add CLI to `runner/adapters/git/pre_push_hook.py` — CLOSED — wayfinder:task (AFK)
- T005b — Create `runner.tools.scaffold_sandbox` and `scripts/sync_agents_md.py` — CLOSED — wayfinder:task (AFK) — blocked by T005, T005a, T005c
- T005c — Lock the curated `AGENTS.md` subset and preamble — CLOSED — wayfinder:grilling (HITL)
- T005d — Add `sandbox.skills` config flag for skill catalog mode — CLOSED — wayfinder:grilling (HITL)
- T006 — Scaffold the external sandbox — wayfinder:task (AFK) — blocked by T005, T005a, T005b, T005c, T005d
- T007 — Lock the in-repo harness layout and `.gitignore` rules — wayfinder:grilling (HITL)
- T008 — Scaffold the in-repo harness at `D:\Projects\live-test-target/` — wayfinder:task (AFK) — blocked by T007
- T009 — Lock the empty-starter design — CLOSED — wayfinder:grilling (HITL)
- T010 — Create the empty starter — wayfinder:task (AFK) — blocked by T009
- T011 — Write `docs/agents/live-test-sites.md` describing all four sites — wayfinder:task (HITL) — blocked by T006, T008, T010, T015
- T012 — Does each live-test site need a `verify-<app>` skill? — wayfinder:grilling (HITL) — blocked by T006, T008, T015
- T013 — Lock the agent-skills cluster layout — wayfinder:grilling (HITL)
- T014 — Clone `https://github.com/Viello/agent-skills` to `D:\Repos\agent-skills\`, install pre-push hook — wayfinder:task (AFK) — blocked by T013
- T015 — Scaffold `D:\Repos\agent-runner-driver\` — wayfinder:task (AFK) — blocked by T013
- T016 — Decide: ship a starter ticket queue in the agent-skills driver — wayfinder:grilling (HITL)
- T017 — (Conditional) Seed the demo ticket queue — wayfinder:task (AFK) — blocked by T016 = yes
- T018 — Rewrite Antigravity adapter to match empirical CLI surface — wayfinder:task (HITL) — blocked by T002 (unblocked); critical-path
- T019 — Push the wayfinder skill fix to Viello/agent-skills main — wayfinder:grilling (HITL) — blocked by T014, T018
- T020 — Scaffold output sanitization engine — wayfinder:task (HITL) — blocked by T005b, T005c, T005d
- T021 — All-mode skill catalog enumeration from the public catalog — wayfinder:task (HITL) — blocked by T005d
- T022 — Fix Doctor worker-provider resolution under single-tier config load — wayfinder:task (HITL) — blocked by none; T099 blocked by T022
- T099 — Spec-closing alignment ticket — wayfinder:task (HITL) — blocked by all (incl. T019, T020, T021)
-->