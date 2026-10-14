---
project: ticket-runner
last_updated: 2026-10-14T19:13:38
author: Gab
branch: agent/ticket-runner
active_ticket: T013-lock-agent-skills-cluster-layout
status: in_progress
stopped_at:
  file: "docs/tickets/15-multi-agent-hardening-and-live-test-site/T013-lock-agent-skills-cluster-layout.md"
  symbol: "## Resolution"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Spec 15 (Multi-Agent Hardening & External Live-Test Site) — T013 Agent-Skills cluster layout (RESOLVED this session, awaiting gatekeeper commit) / T022 Doctor provider resolution (queued next)
- **Last Touchpoint**: T013 + T015 textual edits landed (resolution block added; driver shape amended to minimal stub); working tree clean
- **Blockers**: None (T022 unblocked; T018 critical-path for Antigravity backend execution; T013→T014→T015 chain now unblocked)
- **Next Step**: Execute T022 (Fix Doctor worker-provider resolution) — once landed, run T014 (clone Viello/agent-skills + pre-push) and T015 (scaffold agent-runner-driver minimal stub)

## 🎯 Active Tickets & Progress
- [ ] `T022-fix-doctor-provider-resolution`: Fix Doctor worker-provider resolution under single-tier config load
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T022-fix-doctor-provider-resolution.md)
  - Subtasks:
    - [ ] Resolve provider from merged two-tier config in `Doctor._check_worker_binary`
    - [ ] Avoid swallowing load errors into silent `opencode` default
    - [ ] Update `runner/tools/scaffold_sandbox.py` template with `discord.token_env` default
- [x] `T013-lock-agent-skills-cluster-layout`: Lock Agent-Skills Cluster Layout — RESOLUTION LOCKED; awaiting gatekeeper commit & `Status: completed` flip
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/T013-lock-agent-skills-cluster-layout.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T013-lock-agent-skills-cluster-layout.md)
  - Subtasks:
    - [x] Decide GitHub remotes and driver-to-skills layout (driver = no remote, skills clone = real clone)
    - [x] Decide branch and pre-push hook conventions (`agent/ticket-runner` + `DEFAULT_STANDALONE_HOOK` on both)
    - [x] Decide worker.provider for driver overlay (`antigravity`; locked; CLI-only `--project-dir`)
    - [x] Decide parent `D:\Repos\` hygiene (5-line README; cluster index)
    - [x] Decide discipline rule (driver carries no file the runner parses)
    - [x] Decide D:\Repos\agent-runner-driver\ scripts/start.ps1 as canonical bootstrap
- [ ] `T015-scaffold-agent-runner-driver`: amended this session to drop dead-artifact bullets and adopt minimal-stub shape
  - [ ] `T014-clone-viello-agent-skills-and-install-pre-push`: unblocked once T013 lands

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: None (T013 + T015 ticket-text edits only; no code)
- **Last Stopped At**: T013 `### Resolution` block, line 67 ("T014, T015 may proceed.")

## 📦 Recent Completed Work & Key Decisions
- **T013 Resolution (this session, no commit yet)**: locked agent-skills cluster layout — `D:\Repos\agent-runner-driver\` = minimal invocation stub (git + pre-push + `.gitignore` + `scripts/start.ps1`; no `ticket-runner.yaml`, no `.agent/`, no `docs/tickets/`); `D:\Repos\agent-skills\` = real clone of `Viello/agent-skills` on `agent/ticket-runner` with `.agent/` & `docs/tickets/.queue.lock` added to `.gitignore` only if upstream doesn't already cover; `D:\Repos\README.md` = 5-line cluster index. Provider: `antigravity`. Bootstrap: `pwsh D:\Repos\agent-runner-driver\scripts/start.ps1`. `scripts/publish_agent_skills.py`: TBD (delegated to T016, placeholder recorded).
- **T015 amendment (this session, no commit yet)**: dropped dead `ticket-runner.yaml` / `.agent/` / `docs/tickets/` creation lines; added `scripts/start.ps1` creation requirement; acceptance criteria and gotchas aligned with minimal-stub discipline.
- **cc14f8b**: Lock empty-starter design, add session orienting rule, and track STATUS.md
- **c080555**: Add status skill and integrate session status tracking into retro and handoff
- **cb0a0f0**: Scaffold runnable artifacts from init (`AGENTS.md`, welcome ticket, sample app, smoke test)
- **039b1d0**: Create empty starter fresh-slate target at `D:\Repos\empty-starter` (T010)
- **T009 Resolution**: Pure Empty design at `D:\Repos\empty-starter\` tracked with `.gitkeep` on `agent/ticket-runner`

## ⚠️ Blockers & Gotchas
- Doctor worker-provider resolution bug (T022): live-test sites with `antigravity` provider fall back to `opencode` validation if config fails single-tier load.
- **Spec 15 spec file is missing**: every ticket in `docs/tickets/15-multi-agent-hardening-and-live-test-site/` references `docs/specs/15-multi-agent-hardening-and-live-test-site.md` which does not exist; the de facto spec lives at `T000-wayfinder-map.md`. ADR-0011 spec-context-excerpt injection would FileNotFoundError on every Spec-15 Worker prompt. T099 owns this fix.
- `scripts/start.ps1` (per T013 resolution) requires `pwsh` (PowerShell 7); boxes with only `powershell.exe` 5.1 will fail silently. Consider dual `scripts/start.bat` fallback or a pure-Python `scripts/start.py`.
- Never `git push` on `agent/ticket-runner` — pre-push hook is installed.
- All external path resolution inside `.agent/`, `docs/tickets/`, `ticket-runner.yaml` resolves relative to Target Project root.

## ⏭️ Next 1–3 Actionable Steps
1. `Commit T013`: gatekeeper stages the amended T013 + T015 markdown and the (no-op) `### Resolution` content into a single `docs(scaffolding): <Title>` commit (per single-commit-per-ticket invariant); flips `Status: completed` and relocates to `completed/`.
2. `Execute T022`: Resolve Doctor worker provider from merged two-tier configuration and add regression test in `tests/unit/application/test_doctor.py`.
3. `Execute T014 + T015` (unblocked after T022 lands, since T015's doctor check requires the post-T022 provider resolution): clone Viello/agent-skills (T014) and scaffold the agent-runner-driver minimal stub + `scripts/start.ps1` (T015).
