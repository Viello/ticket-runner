---
project: ticket-runner
last_updated: 2026-10-28T15:48:00
author: Gab
branch: agent/ticket-runner
active_ticket: docs/tickets/17-human-first-ticket-document-format/T128-dual-track-skills-catalog-and-vendoring.md
status: ready
stopped_at:
  file: "docs/tickets/17-human-first-ticket-document-format/T128-dual-track-skills-catalog-and-vendoring.md"
  symbol: "T127 completed and verified; ready to implement T128"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Executing [17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md) tracer-bullet tickets (`T124`–`T129`).
- **Last Touchpoint**: Implemented `T127` (`feat(application): Plumb Default implement-ticket-runner Skill and Canonical Prompt Builder`), verified across targeted and full suites (142 and 1,766 passed), code-reviewed.
- **Blockers**: None.
- **Next Step**: Implement [T128-dual-track-skills-catalog-and-vendoring.md](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/T128-dual-track-skills-catalog-and-vendoring.md) test-first via `/implement`.

## 🎯 Active Tickets & Progress
- [x] `orchestrate-runner-first-run`: Execute the canonical first-run sequence (Phases 1–9) against `D:\Repos\agent-skills` — **COMPLETED**
  - Context / Spec: `D:\Repos\agent-skills\docs\specs\orchestrate-runner.md`
  - Investigation: [gotchas_prompt_swallowed_under_live_display.md](file:///D:/Projects/docs/tickets/gotchas_prompt_swallowed_under_live_display.md)
  - Subtasks:
    - [x] Phases 1–4 environment verification, Doctor 11/11 green, pre-flight predictions (`observations/T101.md` + `T102.md`)
    - [x] Fix startup & live-run blockers A–F + `agy` `--model`/`--effort` normalizer + Rich Live display pause guards (`b1bf1d2`)
    - [x] Live run 2 executed with Overseer monitoring → Worker authored all 8 missing `*/agents/openai.yaml` files (37 → 45), surfacing the 3 Spec 16 defects
    - [x] Land Spec 16 fixes (`T120`–`T123`) in commit `f94609f`
    - [x] Re-run `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only`: both `T101` (`d3ca102`) and `T102` (`59eb828`) Gatekeeper-verified, approved, and committed; status reaches `done`
- [ ] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria
  - Context / Spec: [docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md)
  - Subtasks:
    - [x] Author and settle Spec 17 ([docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md))
    - [x] Decompose Spec 17 into tracer-bullet tickets (`T124`–`T129`) under `docs/tickets/17-human-first-ticket-document-format/`
    - [x] `T124`: [Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T124-canonical-ticket-model-parser-and-serializer.md)
    - [x] `T125`: [Gatekeeper Dispatch-Baseline Tick Boundary and Evidence Card Unticked Criteria](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T125-gatekeeper-dispatch-baseline-tick-boundary-and-evidence-card.md)
    - [x] `T126`: [Pre-Dispatch `HITL` Gate in Gatekeeper, Intervention Port, and Terminal/Discord Prompts](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T126-pre-dispatch-hitl-gate-and-intervention-prompts.md)
    - [x] `T127`: [Default `implement-ticket-runner` Execution Skill Plumbing and Canonical Prompt Builder](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T127-default-implement-ticket-runner-skill-and-prompt-builder.md)
    - [ ] `T128`: [Dual-Track Skills Catalog (`Viello/agent-skills`) and Local `.agents/skills/` Vendoring](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/T128-dual-track-skills-catalog-and-vendoring.md)
    - [ ] `T129`: [Queue Migrations, End-to-End Spec 17 Verification Suite, and Spec-Closing Living Docs Alignment](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/T129-queue-migrations-spec-17-suite-and-living-docs-alignment.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**:
  - `docs/specs/17-human-first-ticket-document-format.md`: Settled Spec 17 document
  - `docs/tickets/17-human-first-ticket-document-format/`: `T124`–`T129` ticket files + `completed/.gitkeep`
  - `observations/`: Historical run traces and debug reports
- **Last Stopped At**: [T124-canonical-ticket-model-parser-and-serializer.md](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/T124-canonical-ticket-model-parser-and-serializer.md) at line 1; ready for `/implement`.

## 📦 Recent Completed Work & Key Decisions
- **AGENTS.md Aligned & Scaffolder Decoupled (`b045307`)**:
  - Rewrote [AGENTS.md](file:///D:/Projects/AGENTS.md) to explicitly separate the **Human + AI interactive workflow on `D:\Projects`** from the **autonomous product architecture** built for Target Projects.
  - Mandated universal compatibility and testing across both **OpenCode** (`OpenCodeWorker`) and **Antigravity CLI** (`AntigravityWorker`) on every feature, with adapter bridging and explicit graceful gating.
  - Decoupled [`scaffold_sandbox.py`](file:///D:/Projects/runner/tools/scaffold_sandbox.py) and [`sync_agents_md.py`](file:///D:/Projects/scripts/sync_agents_md.py) to embed a built-in canonical Target Project starter template (`DEFAULT_UPSTREAM_AGENTS_MD`) instead of scraping `D:\Projects\AGENTS.md`.
  - Verified test suite: 60 passed, 0 failures.
- **Spec 17 Ticket Queue Published (`T124`–`T129`)**:
  - Authored 6 tracer-bullet tickets under `docs/tickets/17-human-first-ticket-document-format/` in the `to-tickets` (Human+AI) format for `D:\Projects`.
- **New Canonical Skills Vendored (`230744a`)**:
  - Merged upstream `origin/main` into local clone [D:\Repos\agent-skills](file:///D:/Repos/agent-skills) (`500be3a`), cleanly harmonizing the 3 new skills and catalog anatomy documentation.
  - Vendored [`brainstorming`](file:///D:/Projects/.agents/skills/brainstorming), [`diagnosing-superpowers`](file:///D:/Projects/.agents/skills/diagnosing-superpowers), and [`finishing-a-development-branch`](file:///D:/Projects/.agents/skills/finishing-a-development-branch) into [D:\Projects\.agents\skills/](file:///D:/Projects/.agents/skills).
  - Preserved protected custom skills (`handoff`, `claude-handoff`, `to-tickets`) untouched.
  - Verified test suite: 1,948 passed, 0 failures.
- **Live Run on Target Project Completed Successfully (2026-10-27/28)**:
  - Command: `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only`
  - `T101`: Gatekeeper verified, approved, committed as `d3ca102` (`feat(queue): Add Codex Interface Metadata to Catalog Skills Currently Missing It`)
  - `T102`: Gatekeeper verified, approved, committed as `59eb828` (`feat(queue): Document agents/openai.yaml in the Catalog's Skill Directory Anatomy`)
  - Target project `.agent/status.json` cleanly reports `run_state: "done"`, `last_step_summary: "Verification passed"`.

## ⚠️ Blockers & Gotchas
- **Live Run Quirks Resolved**: Spec 16 fixes completely cleared previous Windows shell quoting issues and telemetry miscounts. Live run completed with 1 attempt per ticket.
- **Dispatch Baseline Enforcement (Spec 17)**: When implementing Spec 17 (`T125`), the dispatch baseline taken by the Gatekeeper before Worker execution is the security boundary preventing prompt injection or unauthorized ticket rewriting. Refusal consumes an attempt (ADR 0017).

## ⏭️ Next 1–3 Actionable Steps
1. `Implement T124`: Execute [T124-canonical-ticket-model-parser-and-serializer.md](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/T124-canonical-ticket-model-parser-and-serializer.md) test-first via `/implement`.
2. `Implement T125 & T126`: Implement the Gatekeeper dispatch-baseline tick boundary and Pre-Dispatch `HITL` gate.
3. `Implement T127–T129`: Plumb `implement-ticket-runner`, update `Viello/agent-skills`, and complete the Spec 17 verification suite and queue migrations.
