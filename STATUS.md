---
project: ticket-runner
last_updated: 2026-11-03T18:18:00
author: Gab
branch: agent/ticket-runner
active_ticket: T139
status: in_progress
stopped_at:
  file: "docs/tickets/19-dual-track-skill-segregation/completed/T138-prompt-builder-signal-protocol-and-handoff-wiring.md"
  symbol: "T138 Completed; Next: T139 Worker Telemetry Parity and Gatekeeper Auditing"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [Spec 19: Dual-Track Skill Segregation](file:///d:/Projects/docs/specs/19-dual-track-skill-segregation.md) — **IN PROGRESS**.
- **Last Touchpoint**: T138 Completed: PromptBuilder, authoritative ready Signal protocol, and Context Handoff prompt rewired to segregated `-ticket-runner` skills (`code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`).
- **Blockers**: None. Full test suite green (2,189 passed, 0 failures), linter and typechecker clean.
- **Next Step**: Proceed to `T139` (Worker Telemetry Parity and Gatekeeper / TicketProcessor `-ticket-runner` Auditing).

## 🎯 Active Tickets & Progress
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
- [x] `Spec 18 Queue` (`18-signal-contract-hardening`): Signal Contract Hardening and Schema Authority — **COMPLETED**
- [ ] `Spec 19 Queue` (`19-dual-track-skill-segregation`): Dual-Track Skill Segregation — **IN PROGRESS**
  - Context / Spec: [docs/specs/19-dual-track-skill-segregation.md](file:///d:/Projects/docs/specs/19-dual-track-skill-segregation.md)
  - Subtasks:
    - [x] `T137`: [Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T137-standalone-ticket-runner-skills-and-segregation-contract.md)
    - [x] `T138`: [Prompt Builder, Ready Signal Protocol, and Handoff Coordinator `-ticket-runner` Wiring](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T138-prompt-builder-signal-protocol-and-handoff-wiring.md)
    - [ ] `T139`: Worker Telemetry Parity and Gatekeeper Telemetry Auditing
    - [ ] `T140`: Doctor Pre-Flight, Sandbox Scaffolder, and Catalog Publisher Alignment
    - [ ] `T141`: ADR 0026, Living Documentation, and `ticket-runner-site` Synchronization

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: Staged for T138 completion.
- **Last Stopped At**: T138 completed; ready for commit and transition to T139.

## 📦 Recent Completed Work & Key Decisions
- **T138 Complete**:
  - Rewired `runner/domain/signal_schema.py` (`render_ready_signal_protocol`) to mandate reading `.agents/skills/code-review-ticket-runner/SKILL.md` before ready Signal emission.
  - Rewired `runner/application/prompt_builder.py` (`DEFAULT_INVARIANTS`, `_with_token_budget`, `security_review_line`, and `build_prompt`) to direct workers to read `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/security-review-ticket-runner/SKILL.md`, `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`, and `.agents/skills/handoff-ticket-runner/SKILL.md`.
  - Rewired `runner/application/handoff_coordinator.py` (`HANDOFF_PROMPT_TEMPLATE`) to instruct the worker to execute `.agents/skills/handoff-ticket-runner/SKILL.md` when the token threshold is reached.
  - Verified and locked contract assertions across `test_signal_schema.py`, `test_prompt_builder.py`, `test_handoff_coordinator.py`, and `test_spec_03_worker.py`.

## 🔬 Verification Evidence
- Targeted verification suite: 130 passed (`test_signal_schema.py`, `test_prompt_builder.py`, `test_handoff_coordinator.py`, `test_spec_03_worker.py`).
- Skills suite: 22 passed (`test_dual_track_skills.py`, `test_signal_skill_contract.py`).
- Full test suite: `py -3 -m pytest -q` passed (2,189 passed, 6 skipped).
- Ruff check and mypy clean with 0 issues.

## ⏭️ Next 1–3 Actionable Steps
1. Execute commit for `T138`.
2. Begin implementation of `T139` (Worker Telemetry Parity and Gatekeeper / TicketProcessor `-ticket-runner` Auditing).
3. Continue through Spec 19 queue.
