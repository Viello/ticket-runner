---
project: ticket-runner
last_updated: 2026-10-28T10:55:00
author: Gab
branch: agent/ticket-runner
active_ticket: docs/specs/17-human-first-ticket-document-format.md
status: ready
stopped_at:
  file: "docs/specs/17-human-first-ticket-document-format.md"
  symbol: "Spec 17 drafted and settled; live run against agent-skills passed"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Live run of `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only` succeeded as planned (`T101` and `T102` Gatekeeper-verified and committed); Spec 17 (`17-human-first-ticket-document-format`) settled and ready for decomposition.
- **Last Touchpoint**: [docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md) on branch `agent/ticket-runner` (working tree clean except untracked Spec 17 and observations).
- **Blockers**: None. Live run completed with 0 errors and all tickets finalized.
- **Next Step**: Commit [17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md) and decompose into tracer-bullet tickets under `docs/tickets/17-human-first-ticket-document-format/`.

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
    - [ ] Decompose Spec 17 into tracer-bullet tickets under `docs/tickets/17-human-first-ticket-document-format/`
    - [ ] Implement canonical Ticket parser and bold-label metadata header ([`TicketMarkdownParser`](file:///D:/Projects/runner/adapters/queue/ticket_parser.py))
    - [ ] Implement section extraction (`What to build`, `Jump-start`, checkbox `Acceptance criteria`, inert `Smoke scenarios`, `Gotchas`) and domain model updates
    - [ ] Implement Gatekeeper dispatch-baseline comparison and strict Tick-permission boundary ([`GatekeeperCommandExecutor`](file:///D:/Projects/runner/domain/gatekeeper.py))
    - [ ] Update Worker execution discipline and prompt generation ([`PromptBuilder`](file:///D:/Projects/runner/adapters/worker/prompt_builder.py), [`.agents/skills/implement/SKILL.md`](file:///D:/Projects/.agents/skills/implement/SKILL.md))
    - [ ] Synchronize canonical template to `to-tickets` and catalogue, migrate live target tickets and update living documents

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**:
  - `docs/specs/17-human-first-ticket-document-format.md`: Settled Spec 17 document ready for commit and ticket decomposition
  - `observations/`: Historical run traces and debug reports
- **Last Stopped At**: [docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md) at line 1; live test in `D:\Repos\agent-skills` fully passed.

## 📦 Recent Completed Work & Key Decisions
- **Live Run on Target Project Completed Successfully (2026-10-27/28)**:
  - Command: `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only`
  - `T101`: Gatekeeper verified, approved, committed as `d3ca102` (`feat(queue): Add Codex Interface Metadata to Catalog Skills Currently Missing It`)
  - `T102`: Gatekeeper verified, approved, committed as `59eb828` (`feat(queue): Document agents/openai.yaml in the Catalog's Skill Directory Anatomy`)
  - Target project `.agent/status.json` cleanly reports `run_state: "done"`, `last_step_summary: "Verification passed"`.
- **Spec 16 Completed & Committed (`f94609f`)**:
  - Gatekeeper shell quoting escaped for `cmd.exe /d /s /c`
  - Antigravity per-step token occupancy and ready-signal precedence over budget terminations verified
  - Autonomous `docs/tickets/` boundary enforcement and idempotent finalization in place
- **Spec 17 Drafted and Settled (`17-human-first-ticket-document-format`)**:
  - Canonical bold-label header (`**Type:**`, `**Status:**`, etc.)
  - 5 explicit top-level sections (`## What to build`, `## Jump-start`, `## Acceptance criteria`, `## Smoke scenarios`, `## Gotchas`)
  - Worker tick permission for `- [ ]` to `- [x]` with Gatekeeper dispatch baseline comparison (unauthorized modifications consume verification attempts)

## ⚠️ Blockers & Gotchas
- **Live Run Quirks Resolved**: Spec 16 fixes completely cleared previous Windows shell quoting issues and telemetry miscounts. Live run completed with 1 attempt per ticket.
- **Dispatch Baseline Enforcement (Spec 17)**: When implementing Spec 17, the dispatch baseline taken by the Gatekeeper before Worker execution is the security boundary preventing prompt injection or unauthorized ticket rewriting. Refusal consumes an attempt (ADR 0017).

## ⏭️ Next 1–3 Actionable Steps
1. `Commit Spec 17`: Commit [docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md) to `agent/ticket-runner`.
2. `Decompose Spec 17 into Tickets`: Run `/to-tickets` against [docs/specs/17-human-first-ticket-document-format.md](file:///D:/Projects/docs/specs/17-human-first-ticket-document-format.md) into `docs/tickets/17-human-first-ticket-document-format/`.
3. `Implement Spec 17 Queue`: Execute the tracer-bullet tickets test-first via `/implement`.
