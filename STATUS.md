---
project: ticket-runner
last_updated: 2026-10-15T21:32:00
author: Gab
branch: agent/ticket-runner
active_ticket: None
status: ready
stopped_at:
  file: "docs/tickets/15-multi-agent-hardening-and-live-test-site/T000-wayfinder-map.md"
  symbol: "# T000 — Multi-Agent Hardening & External Live-Test Site"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Spec 15 (Multi-Agent Hardening & External Live-Test Site) — Ticket headers formatted; Doctor pre-flight passes clean
- **Last Touchpoint**: [T000-wayfinder-map.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T000-wayfinder-map.md) on branch `agent/ticket-runner` (clean working tree)
- **Blockers**: None (Doctor pre-flight verification passing 100%)
- **Next Step**: Run live verification via `/live-qa` or begin next ticket execution (T018 / T011)

## 🎯 Active Tickets & Progress
- [x] `T017-seed-demo-ticket-queue`: Seed the demo ticket queue (conditional) — CLOSED via `ec2c590`
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T017-seed-demo-ticket-queue.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T017-seed-demo-ticket-queue.md)
  - Subtasks:
    - [x] Author 1-paragraph spec at `D:\Repos\agent-runner-driver\docs\specs\01-runner-live-test-bootstrap.md`
    - [x] Author 2 demo tickets under `D:\Repos\agent-runner-driver\docs\tickets\01-runner-live-test-bootstrap\`
    - [x] Demo tickets carry standard sections + no T<NNN> in H1 titles + standard tags
    - [x] Seed tickets describe real catalog hygiene gaps observed at chart-time (not Round-1 stale candidates)
    - [x] Initialize driver-local gotchas log capturing cluster-layout reconciliation + Unicode-tree discipline
    - [x] Demo tickets `pending`; execution is the user's decision in a subsequent session
- [x] `T016-decide-starter-ticket-queue-and-publish-migration`: Decide starter ticket queue and publish-script migration — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T016-decide-starter-ticket-queue-and-publish-migration.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T016-decide-starter-ticket-queue-and-publish-migration.md)
  - Subtasks:
    - [x] Decide starter-queue option: **Yes** — pre-seed 2 demo tickets in driver under `01-runner-live-test-bootstrap`
    - [x] Decide publication script: **Coexist** — keep `scripts/publish_agent_skills.py`; no relocation follow-up
    - [x] Decide queue location: **Driver** — `D:\Repos\agent-runner-driver\docs/tickets/01-runner-live-test-bootstrap/`
    - [x] Decide spec file: **Yes** — 1-paragraph spec alongside the queue scaffold
    - [x] Reconcile prior cluster-layout discipline: bootstrap `--project-dir` indirection preserves the spirit; prior ticket stays as historical record
    - [x] Defer specific ticket content to next ticket in chain (Round-1 candidates partly stale)
- [x] `T022-fix-doctor-provider-resolution`: Fix Doctor worker-provider resolution under single-tier config load — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T022-fix-doctor-provider-resolution.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T022-fix-doctor-provider-resolution.md)
  - Subtasks:
    - [x] Resolve provider from merged two-tier config in `Doctor._check_worker_binary`
    - [x] Avoid swallowing load errors into silent `opencode` default
    - [x] Update `runner/tools/scaffold_sandbox.py` template with `discord.token_env` default
    - [x] Add regression tests in `tests/unit/application/test_doctor.py`
- [x] `T015-scaffold-agent-runner-driver`: Scaffold the Agent-Skills Driver Minimal Stub — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T015-scaffold-agent-runner-driver.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T015-scaffold-agent-runner-driver.md)
  - Subtasks:
    - [x] Create `D:\Repos\agent-runner-driver\` directory
    - [x] Initialize git repo on branch `agent/ticket-runner`
    - [x] Install pre-push guardrail hook
    - [x] Add defensive `.gitignore`
    - [x] Author `scripts/start.ps1` targeting `--project-dir D:\Repos\agent-skills`
    - [x] Commit initial scaffold `6214c1e`
- [x] `T014-clone-viello-agent-skills-and-install-pre-push`: Clone Viello/agent-skills and install pre-push hook — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T014-clone-viello-agent-skills-and-install-pre-push.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T014-clone-viello-agent-skills-and-install-pre-push.md)
  - Subtasks:
    - [x] Clone `https://github.com/Viello/agent-skills` into `D:\Repos\agent-skills` (HEAD `727a94f`)
    - [x] Create and checkout branch `agent/ticket-runner`
    - [x] Install standalone pre-push guardrail hook into `.git/hooks/pre-push`
    - [x] Add `.gitignore` covering `.agent/` and `docs/tickets/.queue.lock`
    - [x] Verify smoke scenario: push attempt blocked by pre-push hook
- [x] `T013-lock-agent-skills-cluster-layout`: Lock Agent-Skills Cluster Layout — CLOSED via `aa3bd9c`
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T013-lock-agent-skills-cluster-layout.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T013-lock-agent-skills-cluster-layout.md)
  - Subtasks:
    - [x] Decide GitHub remotes and driver-to-skills layout (driver = no remote, skills clone = real clone)
    - [x] Decide branch and pre-push hook conventions (`agent/ticket-runner` + `DEFAULT_STANDALONE_HOOK` on both)
    - [x] Decide worker.provider for driver overlay (`antigravity`; locked; CLI-only `--project-dir`)
    - [x] Decide parent `D:\Repos\` hygiene (5-line README; cluster index)
    - [x] Decide discipline rule (driver carries no file the runner parses)
    - [x] Decide D:\Repos\agent-runner-driver\ scripts/start.ps1 as canonical bootstrap

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: None (working tree clean)
- **Last Stopped At**: [T000-wayfinder-map.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T000-wayfinder-map.md) line 1; Doctor pre-flight passes 100% clean

## 📦 Recent Completed Work & Key Decisions
- **b38c2c5**: Formatted [T000-wayfinder-map.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T000-wayfinder-map.md) with `# T000 — Multi-Agent Hardening & External Live-Test Site` and `Status: completed` metadata; formatted driver demo tickets [T101](file:///D:/Repos/agent-runner-driver/docs/tickets/01-runner-live-test-bootstrap/T101-add-codex-interface-metadata-to-skills-lacking-it.md) and [T102](file:///D:/Repos/agent-runner-driver/docs/tickets/01-runner-live-test-bootstrap/T102-document-agents-openai-yaml-in-skill-anatomy.md) with standard `# T<NNN> — <Title>` headers. Unblocked queue verification across Doctor and Ticket Store parsers.
- **T017**: Seeded the live-test bootstrap spec (`D:\Repos\agent-runner-driver\docs\specs\01-runner-live-test-bootstrap.md`) and 2 demo tickets under `D:\Repos\agent-runner-driver\docs\tickets\01-runner-live-test-bootstrap\` (`T101` adds `agents/openai.yaml` to 8 catalog skills lacking it; `T102` documents the interface file in the catalog anatomy README block). Both H1s are T<NNN>-free per the demo-ticket title constraint; both carry standard wayfinder sections; both target real chart-time catalog hygiene (8 of 45 skills missing Codex interface metadata; README silent on `agents/`). Initialized driver-local `docs/tickets/gotchas.md` with the cluster-layout reconciliation narrative and the Unicode-tree-character discipline. Demo tickets are seeded (not executed) — execution is the next step. Driver commit landed at `9af978e`; runner-source relocation at `ec2c590`.
- **T016**: Decided starter-queue (yes, 2 demo tickets in driver under `01-runner-live-test-bootstrap`) and publication-script (coexist, no follow-up). Reconciled prior cluster-layout discipline via bootstrap `--project-dir` indirection (driver's `docs/tickets/` permitted as a queue home; runner never reads it). Authored 1-paragraph spec alongside queue scaffold (per agent-guidelines pattern). Defer specific ticket content to next ticket in chain.
- **T022**: Resolved Doctor worker-provider resolution by unifying configuration loading in `Doctor._load_configuration` with two-tier resolution (`load_two_tier`). Suppressed silent `"opencode"` fallback on unloadable configs so errors surface via `check_config` without masquerading as valid providers. Added `discord.token_env: "DISCORD_BOT_TOKEN"` default to sandbox template and added regression tests in `tests/unit/application/test_doctor.py`. Verified on `D:\Sandbox\ticket-runner-live-target` and `D:\Projects\live-test-target`.
- **T015**: Scaffolded `D:\Repos\agent-runner-driver\` minimal stub (`git init -b main`, branch `agent/ticket-runner`, pre-push hook, defensive `.gitignore`, and `scripts/start.ps1` / `scripts/start.bat` pointing `--project-dir D:\Repos\agent-skills`). Root scaffold commit authored as `6214c1e`.
- **T014**: Cloned `Viello/agent-skills` into `D:\Repos\agent-skills\`, checked out `agent/ticket-runner`, installed pre-push guardrail, added `.gitignore` (`.agent/`, `docs/tickets/.queue.lock`), and verified push blocking. Upstream HEAD recorded as `727a94f70cad35438cd89ccb896174b44f2ff38a`.
- **aa3bd9c**: Lock agent-skills cluster layout and amend driver scaffold — T013 relocated to `completed/`, T015 amended to minimal-stub shape, gotcha + STATUS synced
- **T013 Resolution**: `D:\Repos\agent-runner-driver\` = minimal invocation stub (git + pre-push + `.gitignore` + `scripts/start.ps1`; no `ticket-runner.yaml`, no `.agent/`; `docs/tickets/` permitted per the live-test queue decision); `D:\Repos\agent-skills\` = real clone of `Viello/agent-skills` on `agent/ticket-runner` with `.agent/` & `docs/tickets/.queue.lock` added to `.gitignore` only if upstream doesn't already cover; `D:\Repos\README.md` = 5-line cluster index. Provider: `antigravity`. Bootstrap: `pwsh D:\Repos\agent-runner-driver\scripts/start.ps1` (or `scripts/start.bat`). `scripts/publish_agent_skills.py`: **Coexist** (decided via the live-test queue ticket; script remains manual bulk-reset path).
- **cc14f8b**: Lock empty-starter design, add session orienting rule, and track STATUS.md
- **c080555**: Add status skill and integrate session status tracking into retro and handoff
- **cb0a0f0**: Scaffold runnable artifacts from init (`AGENTS.md`, welcome ticket, sample app, smoke test)
- **039b1d0**: Create empty starter fresh-slate target at `D:\Repos\empty-starter` (T010)

## ⚠️ Blockers & Gotchas
- **Spec 15 spec file is missing**: every ticket in `docs/tickets/15-multi-agent-hardening-and-live-test-site/` references `docs/specs/15-multi-agent-hardening-and-live-test-site.md` which does not exist; the de facto spec lives at `T000-wayfinder-map.md`. ADR-0011 spec-context-excerpt injection would FileNotFoundError on every Spec-15 Worker prompt. T099 owns this fix.
- `scripts/start.ps1` (per T013 resolution) requires `pwsh` (PowerShell 7); boxes with only `powershell.exe` 5.1 will fail silently. Consider dual `scripts/start.bat` fallback or a pure-Python `scripts/start.py`.
- Never `git push` on `agent/ticket-runner` — pre-push hook is installed.
- All external path resolution inside `.agent/`, `docs/tickets/`, `ticket-runner.yaml` resolves relative to Target Project root.

## ⏭️ Next 1–3 Actionable Steps
1. `Execute seeded demo tickets`: Run the Ticket Runner from the driver (`pwsh D:\Repos\agent-runner-driver\scripts/start.ps1 start`) so the Worker picks up T101 (Codex interface metadata), the Gatekeeper verifies, and T102 (README anatomy) follows.
2. `Run Doctor against agent-skills`: Verify `doctor` passes when invoked from driver or with `--project-dir D:\Repos\agent-skills`, now that the queue is seeded.
3. `T018 / T019`: Rewrite Antigravity adapter (empirical flag surface) and push the wayfinder skill fix upstream.
