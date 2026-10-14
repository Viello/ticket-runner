---
project: ticket-runner
last_updated: 2026-10-14T13:41:00
author: Gab
branch: agent/ticket-runner
active_ticket: T022-fix-doctor-provider-resolution
status: in_progress
stopped_at:
  file: ""
  symbol: ""
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Spec 15 (Multi-Agent Hardening & External Live-Test Site) — T022 Doctor provider resolution / T013 Agent-Skills cluster layout
- **Last Touchpoint**: Fresh / ready for next task on branch `agent/ticket-runner` (3 uncommitted files)
- **Blockers**: None (T022 unblocked; T018 critical-path for Antigravity backend execution)
- **Next Step**: Stage and commit uncommitted T009 completion, wayfinder map updates, and AGENTS.md, then proceed with T022 or T013

## 🎯 Active Tickets & Progress
- [ ] `T022-fix-doctor-provider-resolution`: Fix Doctor worker-provider resolution under single-tier config load
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md)
  - Subtasks:
    - [ ] Resolve provider from merged two-tier config in `Doctor._check_worker_binary`
    - [ ] Avoid swallowing load errors into silent `opencode` default
    - [ ] Update `runner/tools/scaffold_sandbox.py` template with `discord.token_env` default
- [ ] `T013-lock-agent-skills-cluster-layout`: Lock Agent-Skills Cluster Layout
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/T013-lock-agent-skills-cluster-layout.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T013-lock-agent-skills-cluster-layout.md)
  - Subtasks:
    - [ ] Decide GitHub remotes and driver-to-skills layout
    - [ ] Decide branch and pre-push hook conventions for both repos

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**:
  - `AGENTS.md`: Added Session Orienting & Status rule for automatic STATUS.md reading on session startup
  - `docs/tickets/15-multi-agent-hardening-and-live-test-site/T000-wayfinder-map.md`: Map index updated to reflect T009 CLOSED and empty-starter path resolution
  - `docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T009-lock-empty-starter-design.md`: Resolution recorded and status marked completed
- **Last Stopped At**: None (reset for fresh work)

## 📦 Recent Completed Work & Key Decisions
- **c080555**: Add status skill and integrate session status tracking into retro and handoff
- **cb0a0f0**: Scaffold runnable artifacts from init (`AGENTS.md`, welcome ticket, sample app, smoke test)
- **039b1d0**: Create empty starter fresh-slate target at `D:\Repos\empty-starter` (T010)
- **T009 Resolution**: Pure Empty design at `D:\Repos\empty-starter\` tracked with `.gitkeep` on `agent/ticket-runner`

## ⚠️ Blockers & Gotchas
- Doctor worker-provider resolution bug (T022): live-test sites with `antigravity` provider fall back to `opencode` validation if config fails single-tier load.
- Never `git push` on `agent/ticket-runner` — pre-push hook is installed.
- All external path resolution inside `.agent/`, `docs/tickets/`, `ticket-runner.yaml` resolves relative to Target Project root.

## ⏭️ Next 1–3 Actionable Steps
1. `Commit T009 & map updates`: Author git commit for uncommitted T009 completion and wayfinder map updates following project commit format.
2. `Execute T022`: Resolve Doctor worker provider from merged two-tier configuration and add regression test in `tests/unit/application/test_doctor.py`.
3. `Execute T013`: Conduct grilling interview on agent-skills cluster layout (`D:\Repos\agent-skills\` vs `D:\Repos\agent-runner-driver\`).
