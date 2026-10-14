---
project: ticket-runner
last_updated: 2026-10-14T14:54:30
author: Gab
branch: agent/ticket-runner
active_ticket: T022-fix-doctor-provider-resolution
status: in_progress
stopped_at:
  file: "docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md"
  symbol: "### Requirements"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Spec 15 (Multi-Agent Hardening & External Live-Test Site) — T015 closed; T022 (Doctor provider resolution) in flight next
- **Last Touchpoint**: T015 closed; `D:\Repos\agent-runner-driver` scaffolded with `agent/ticket-runner`, pre-push guardrail, `.gitignore`, and `scripts/start.ps1`
- **Blockers**: None (T015 closed; T022 unblocked; T018 still critical-path for full Antigravity backend)
- **Next Step**: Execute T022 (Doctor worker-provider resolution under single-tier config load)

## 🎯 Active Tickets & Progress
- [ ] `T022-fix-doctor-provider-resolution`: Fix Doctor worker-provider resolution under single-tier config load
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md)
  - Subtasks:
    - [ ] Resolve provider from merged two-tier config in `Doctor._check_worker_binary`
    - [ ] Avoid swallowing load errors into silent `opencode` default
    - [ ] Update `runner/tools/scaffold_sandbox.py` template with `discord.token_env` default
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
- **Uncommitted Files**: None (working tree clean, commit `791dd35`)
- **Last Stopped At**: T015 completed; ready to execute T022

## 📦 Recent Completed Work & Key Decisions
- **T015**: Scaffolded `D:\Repos\agent-runner-driver\` minimal stub (`git init -b main`, branch `agent/ticket-runner`, pre-push hook, defensive `.gitignore`, and `scripts/start.ps1` / `scripts/start.bat` pointing `--project-dir D:\Repos\agent-skills`). Root scaffold commit authored as `6214c1e`.
- **T014**: Cloned `Viello/agent-skills` into `D:\Repos\agent-skills\`, checked out `agent/ticket-runner`, installed pre-push guardrail, added `.gitignore` (`.agent/`, `docs/tickets/.queue.lock`), and verified push blocking. Upstream HEAD recorded as `727a94f70cad35438cd89ccb896174b44f2ff38a`.
- **aa3bd9c**: Lock agent-skills cluster layout and amend driver scaffold — T013 relocated to `completed/`, T015 amended to minimal-stub shape, gotcha + STATUS synced
- **T013 Resolution**: `D:\Repos\agent-runner-driver\` = minimal invocation stub (git + pre-push + `.gitignore` + `scripts/start.ps1`; no `ticket-runner.yaml`, no `.agent/`, no `docs/tickets/`); `D:\Repos\agent-skills\` = real clone of `Viello/agent-skills` on `agent/ticket-runner` with `.agent/` & `docs/tickets/.queue.lock` added to `.gitignore` only if upstream doesn't already cover; `D:\Repos\README.md` = 5-line cluster index. Provider: `antigravity`. Bootstrap: `pwsh D:\Repos\agent-runner-driver\scripts/start.ps1`. `scripts/publish_agent_skills.py`: TBD (delegated to T016, placeholder recorded).
- **cc14f8b**: Lock empty-starter design, add session orienting rule, and track STATUS.md
- **c080555**: Add status skill and integrate session status tracking into retro and handoff
- **cb0a0f0**: Scaffold runnable artifacts from init (`AGENTS.md`, welcome ticket, sample app, smoke test)
- **039b1d0**: Create empty starter fresh-slate target at `D:\Repos\empty-starter` (T010)

## ⚠️ Blockers & Gotchas
- Doctor worker-provider resolution bug (T022): live-test sites with `antigravity` provider fall back to `opencode` validation if config fails single-tier load.
- **Spec 15 spec file is missing**: every ticket in `docs/tickets/15-multi-agent-hardening-and-live-test-site/` references `docs/specs/15-multi-agent-hardening-and-live-test-site.md` which does not exist; the de facto spec lives at `T000-wayfinder-map.md`. ADR-0011 spec-context-excerpt injection would FileNotFoundError on every Spec-15 Worker prompt. T099 owns this fix.
- `scripts/start.ps1` (per T013 resolution) requires `pwsh` (PowerShell 7); boxes with only `powershell.exe` 5.1 will fail silently. Consider dual `scripts/start.bat` fallback or a pure-Python `scripts/start.py`.
- Never `git push` on `agent/ticket-runner` — pre-push hook is installed.
- All external path resolution inside `.agent/`, `docs/tickets/`, `ticket-runner.yaml` resolves relative to Target Project root.

## ⏭️ Next 1–3 Actionable Steps
1. `Execute T022`: Resolve Doctor worker provider from merged two-tier configuration and add regression test in `tests/unit/application/test_doctor.py`.
2. `Run Doctor against agent-skills`: Once T022 lands, verify `doctor` passes when invoked from driver or with `--project-dir D:\Repos\agent-skills`.
3. `Decide T016`: Grilling session on whether to ship a starter ticket queue in the agent-skills driver.
