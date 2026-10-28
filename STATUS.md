---
project: ticket-runner
last_updated: 2026-10-28T16:15:00
author: Gab
branch: agent/ticket-runner
active_ticket: null
status: ready
stopped_at:
  file: "docs/specs/17-human-first-ticket-document-format.md"
  symbol: "All tickets T124-T129 completed and verified"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Spec 17 (`17-human-first-ticket-document-format.md`) fully completed; ready for next spec / operator direction.
- **Last Touchpoint**: Implemented `T129` (`feat(queue): Spec 17 Queue Migrations, Verification Suite, and Living Docs Alignment`), verified full test suite (2,032 passed, 0 failures), active queues migrated, Target Projects synchronized, and root living documents aligned.
- **Blockers**: None.
- **Next Step**: Await operator direction or select next backlog item / live run.

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
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
  - Context / Spec: [docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md)
  - Subtasks:
    - [x] Author and settle Spec 17 ([docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md))
    - [x] Decompose Spec 17 into tracer-bullet tickets (`T124`–`T129`) under `docs/tickets/17-human-first-ticket-document-format/`
    - [x] `T124`: [Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T124-canonical-ticket-model-parser-and-serializer.md)
    - [x] `T125`: [Gatekeeper Dispatch-Baseline Tick Boundary and Evidence Card Unticked Criteria](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T125-gatekeeper-dispatch-baseline-tick-boundary-and-evidence-card.md)
    - [x] `T126`: [Pre-Dispatch `HITL` Gate in Gatekeeper, Intervention Port, and Terminal/Discord Prompts](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T126-pre-dispatch-hitl-gate-and-intervention-prompts.md)
    - [x] `T127`: [Default `implement-ticket-runner` Execution Skill Plumbing and Canonical Prompt Builder](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T127-default-implement-ticket-runner-skill-and-prompt-builder.md)
    - [x] `T128`: [Dual-Track Skills Catalog (`Viello/agent-skills`) and Local `.agents/skills/` Vendoring](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T128-dual-track-skills-catalog-and-vendoring.md)
    - [x] `T129`: [Queue Migrations, End-to-End Spec 17 Verification Suite, and Spec-Closing Living Docs Alignment](file:///D:/Projects/docs/tickets/17-human-first-ticket-document-format/completed/T129-queue-migrations-spec-17-suite-and-living-docs-alignment.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: Staged & unstaged changes for T129 (Spec 17 closing ticket).
- **Last Stopped At**: Spec 17 fully implemented and verified; preparing final atomic commit for T129.

## 📦 Recent Completed Work & Key Decisions
- **Spec 17 Tracer Bullets Completed (`T124`–`T129`)**:
  - `T124`: Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer.
  - `T125`: Gatekeeper Dispatch-Baseline Tick Boundary and Evidence Card Unticked Criteria.
  - `T126`: Pre-Dispatch `HITL` Gate in Gatekeeper, Intervention Port, and Terminal/Discord Prompts.
  - `T127`: Default `implement-ticket-runner` Execution Skill Plumbing and Canonical Prompt Builder.
  - `T128`: Dual-Track Skills Catalog (`Viello/agent-skills`) and Local `.agents/skills/` Vendoring.
  - `T129`: Queue Migrations, End-to-End Spec 17 Verification Suite (10/10 tests in `test_spec_17_human_first_ticket_format.py`), and Root Living Docs Alignment (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `gotchas.md`, ADRs 0008, 0012, 0023).
  - Verified full test suite: 2,032 passed, 4 skipped, 0 failures.

## ⚠️ Blockers & Gotchas
- **Dispatch Baseline Enforcement (Spec 17)**: The dispatch baseline taken by the Gatekeeper before Worker execution is the security boundary preventing prompt injection or unauthorized ticket rewriting. Refusal consumes an attempt (ADR 0017).
- **Dual-Track Skill Conventions**: `to-tickets` and `implement` are reserved for Human + AI development on `D:\Projects`. `to-ticket-runner` and `implement-ticket-runner` are canonical for autonomous Ticket Runner Target Projects.

## ⏭️ Next 1–3 Actionable Steps
1. `Commit T129`: Create atomic git commit for T129 closing Spec 17.
2. `Next Milestone`: Review backlog or consult operator for next spec/milestone.
