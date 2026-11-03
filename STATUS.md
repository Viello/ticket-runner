---
project: ticket-runner
last_updated: 2026-11-03T17:47:00
author: Gab
branch: agent/ticket-runner
active_ticket: T138
status: in_progress
stopped_at:
  file: "docs/tickets/19-dual-track-skill-segregation/completed/T137-standalone-ticket-runner-skills-and-segregation-contract.md"
  symbol: "T137 Completed; Next: T138 Prompt Builder & Signal Protocol Wiring"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [Spec 19: Dual-Track Skill Segregation](file:///d:/Projects/docs/specs/19-dual-track-skill-segregation.md) — **IN PROGRESS**.
- **Last Touchpoint**: T137 Completed: Standalone `-ticket-runner` skills authored (`code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`), interactive skills cleaned of `.agent/` references, and dual-track 6-pair segregation contract locked.
- **Blockers**: None. Full test suite green (2,188 passed, 0 failures), linter and typechecker clean.
- **Next Step**: Proceed to `T138` (Prompt Builder, Ready Signal Protocol, and Handoff Coordinator `-ticket-runner` Wiring).

## 🎯 Active Tickets & Progress
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
- [x] `Spec 18 Queue` (`18-signal-contract-hardening`): Signal Contract Hardening and Schema Authority — **COMPLETED**
- [ ] `Spec 19 Queue` (`19-dual-track-skill-segregation`): Dual-Track Skill Segregation — **IN PROGRESS**
  - Context / Spec: [docs/specs/19-dual-track-skill-segregation.md](file:///d:/Projects/docs/specs/19-dual-track-skill-segregation.md)
  - Subtasks:
    - [x] `T137`: [Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract](file:///d:/Projects/docs/tickets/19-dual-track-skill-segregation/completed/T137-standalone-ticket-runner-skills-and-segregation-contract.md)
    - [ ] `T138`: Prompt Builder, Ready Signal Protocol, and Handoff Coordinator `-ticket-runner` Wiring
    - [ ] `T139`: Worker Telemetry Parity and Gatekeeper Telemetry Auditing
    - [ ] `T140`: Doctor Pre-Flight, Sandbox Scaffolder, and Catalog Publisher Alignment
    - [ ] `T141`: ADR 0026, Living Documentation, and `ticket-runner-site` Synchronization

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: Staged for T137 completion.
- **Last Stopped At**: T137 completed; ready for commit and transition to T138.

## 📦 Recent Completed Work & Key Decisions
- **T137 Complete**:
  - Authored standalone `-ticket-runner` skills (`code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`) with `agents/openai.yaml` and `disable-model-invocation: true`.
  - Cleaned all six interactive Human + AI skills (`to-tickets`, `implement`, `code-review`, `security-review`, `diagnosing-bugs`, `handoff`) to contain zero references to `.agent/signals/`, `.agent/questions/`, or `.agent/checkpoints/`.
  - Added routing pointers and updated `ask-matt` router and `D:\Repos\agent-skills\README.md` index (54 canonical skills).
  - Enforced 6-pair dual-track segregation contract in `tests/unit/skills/test_dual_track_skills.py` and signal contract compliance in `test_signal_skill_contract.py`.

## 🔬 Verification Evidence
- Targeted skills suite: 22 passed.
- Prompt builder suite: 39 passed.
- Full test suite: `py -3 -m pytest -q` passed (2,188 passed, 4 skipped).
- Ruff check and mypy clean with 0 issues.

## ⏭️ Next 1–3 Actionable Steps
1. Execute commit for `T137`.
2. Begin implementation of `T138` (Prompt Builder, Ready Signal Protocol, and Handoff Wiring).
3. Continue through Spec 19 queue.
