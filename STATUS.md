---
project: ticket-runner
last_updated: 2026-11-03T19:25:00
author: Gab
branch: agent/ticket-runner
active_ticket: T141
status: ready
stopped_at:
  file: "docs/tickets/19-dual-track-skill-segregation/completed/T141-adr-0026-living-docs-and-site-sync.md"
  symbol: "Spec 19 Completed; Pending operator skills publish step"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [Spec 19: Dual-Track Skill Segregation](file:///d:/Projects/docs/specs/19-dual-track-skill-segregation.md) — **COMPLETED**.
- **Last Touchpoint**: T141 Completed: ADR 0026 recorded, ADRs 0008/0013/0014/0020 amended, Dual-Track Skill Segregation Rule codified in `AGENTS.md` and `docs/ai/workflow.md`, `README.md` updated with `-ticket-runner` pipeline stages, and `ticket-runner-site` synchronized, verified, and committed.
- **Blockers**: None. Full test suite green (2,190 passed, 0 failures), static site verify clean.
- **Next Step**: Operator step: run `py -3 scripts/publish_agent_skills.py` to publish the canonical 54-skill catalog to GitHub (`Viello/agent-skills`).

## 🎯 Active Tickets & Progress
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
- [x] `Spec 18 Queue` (`18-signal-contract-hardening`): Signal Contract Hardening and Schema Authority — **COMPLETED**
- [x] `Spec 19 Queue` (`19-dual-track-skill-segregation`): Dual-Track Skill Segregation — **COMPLETED**
  - Context / Spec: [docs/specs/19-dual-track-skill-segregation.md](file:///d:/Projects/docs/specs/19-dual-track-skill-segregation.md)
  - Subtasks:
    - [x] `T137`: [Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T137-standalone-ticket-runner-skills-and-segregation-contract.md)
    - [x] `T138`: [Prompt Builder, Ready Signal Protocol, and Handoff Coordinator `-ticket-runner` Wiring](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T138-prompt-builder-signal-protocol-and-handoff-wiring.md)
    - [x] `T139`: [Worker Telemetry Parity and Gatekeeper Telemetry Auditing](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T139-worker-telemetry-parity-and-gatekeeper-auditing.md)
    - [x] `T140`: [Doctor Pre-Flight, Sandbox Scaffolder, and Catalog Publisher Alignment](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T140-doctor-preflight-scaffolder-and-catalog-publisher-alignment.md)
    - [x] `T141`: [ADR 0026, Operating Contract & README Alignment, and `ticket-runner-site` Synchronization](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T141-adr-0026-living-docs-and-site-sync.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: Staged for T141 completion.
- **Last Stopped At**: T141 completed and verified; Spec 19 complete.

## 📦 Recent Completed Work & Key Decisions
- **T141 Complete & Spec 19 Closed**:
  - Authored ADR 0026 (`docs/adr/0026-dual-track-skill-segregation-and-human-control-routing.md`) codifying the Dual-Track Skill Segregation Rule, the 6-pair skill matrix, and Question Signal (`WAITING_FOR_USER`) human control routing.
  - Amended ADRs 0008, 0013, 0014, and 0020 to link to ADR 0026 and standardise on the `-ticket-runner` skill family.
  - Codified the Dual-Track Skill Segregation Rule in `AGENTS.md` and `docs/ai/workflow.md`, preserving the `## Invariants`, `## Environment`, and `## Agent skills` headings and bullet prefixes required by runtime readers.
  - Aligned `D:\Projects\README.md` 8-stage pipeline diagram, Stage Details, and configuration examples to reference `/to-ticket-runner`, `.agents/skills/implement-ticket-runner/SKILL.md`, `code-review-ticket-runner`, and `security-review-ticket-runner`.
  - Synchronized `D:\Repos\ticket-runner-site` vendored skills, updated `scripts/sync-runner.mjs` (`pipelineDefinitions`), regenerated `content/snapshot.json` via `npm run sync`, verified cleanly via `npm run verify`, and committed changes.
  - Verified full test suite and contract tests pass with 0 failures.

## 🔬 Verification Evidence
- Targeted skills, scaffolder, and prompt builder tests: 85 passed.
- Documentation site verification (`npm --prefix D:\Repos\ticket-runner-site run verify`): typecheck, lint, next build, check:links (276 links verified), and check:design clean with 0 errors.
- Site test suite (`npm --prefix D:\Repos\ticket-runner-site test`): 88 passed, 0 failures.

## ⏭️ Next 1–3 Actionable Steps
1. Operator step: Run `py -3 scripts/publish_agent_skills.py` to publish the updated 54 canonical skills catalog to GitHub (`Viello/agent-skills`).
2. Optional: Run `npm --prefix D:\Repos\ticket-runner-site run dev` to preview the updated documentation site locally.
3. Consult operator for next milestone or spec roadmap.
