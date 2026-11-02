---
project: ticket-runner
last_updated: 2026-11-02T18:15:00
author: Gab
branch: agent/ticket-runner
active_ticket: T134-malformed-signal-archive-and-diagnostic
status: paused
stopped_at:
  file: "docs/tickets/18-signal-contract-hardening/T134-malformed-signal-archive-and-diagnostic.md"
  symbol: "T134 implementation pending"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [T134: Malformed Signal Archive and Diagnostic](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T134-malformed-signal-archive-and-diagnostic.md) under [Spec 18](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md).
- **Last Touchpoint**: `runner/application/doctor.py` and `scripts/publish_agent_skills.py` on branch `agent/ticket-runner`.
- **Blockers**: None. T133 Doctor pre-flight check and skills publish gate completed and verified.
- **Next Step**: Implement malformed signal archive paths in `RuntimePaths` and diagnostic persistence in `Gatekeeper` (T134).

## 🎯 Active Tickets & Progress
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
- [ ] `Spec 18 Queue` (`18-signal-contract-hardening`): Signal Contract Hardening and Schema Authority — **IN PROGRESS**
  - Context / Spec: [docs/specs/18-signal-contract-hardening.md](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md)
  - Subtasks:
    - [x] `T130`: [Domain Signal Schema Authority and Gotcha Tolerance](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T130-domain-signal-schema-authority-and-gotcha-tolerance.md) (`f052bb3`)
    - [x] `T131`: [Prompt Renders Domain Protocol and Skill Defers](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T131-prompt-renders-domain-protocol-and-skill-defers.md) (`456a7ec`)
    - [x] `T132`: [Markdown Signal Example Contract Checker](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T132-markdown-signal-example-contract-checker.md) (`0b600d7`)
    - [x] `T133`: [Doctor Pre-Flight and Skills Publish Gate](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T133-doctor-preflight-and-skills-publish-gate.md)
    - [ ] `T134`: [Malformed Signal Archive and Diagnostic](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T134-malformed-signal-archive-and-diagnostic.md)
    - [ ] `T135`: [Signal Format Label and Self-Correctable Retry](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T135-signal-format-label-and-self-correctable-retry.md)
    - [ ] `T136`: [ADRs, Operating Contract Invariant, and Status Note](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T136-adrs-operating-contract-invariant-and-status-note.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: Staged changes for T133.
- **Last Stopped At**: T133 completed and verified green; ready for T134.

## 📦 Recent Completed Work & Key Decisions
- **Spec 18 Tracer Bullets (`T130`–`T133`)**:
  - `T130`: Domain Signal Schema Authority and Gotcha Tolerance (`runner/domain/signal_contract.py`).
  - `T131`: Authoritative Signal Protocol rendered dynamically in prompt (`runner/application/prompt_builder.py`).
  - `T132`: Markdown Signal Example Contract Checker (`runner/domain/signal_contract.py`).
  - `T133`: Doctor Pre-Flight Signal Contract Check (`runner/application/doctor.py`) and Skills Catalog Publish Gate (`scripts/publish_agent_skills.py`).

## ⚠️ Blockers & Gotchas
- Doctor pre-flight checks reject any execution skill violating the domain Signal schema before dispatch.
- Remediation strings specify the file and rule first, referencing `ticket-runner skills sync` only as post-republish.
- Skills catalog publication verifies all `SKILL.md` documents before staging and aborts if any signal example fails.

## ⏭️ Next 1–3 Actionable Steps
1. Write failing tests for malformed signal archive paths in `tests/unit/domain/test_runtime_paths.py`.
2. Add `malformed_ready_signal_path` and `malformed_question_signal_path` to `RuntimePaths`.
3. Implement atomic archiving and diagnostic writing before escalation prompt in `Gatekeeper` (T134).
