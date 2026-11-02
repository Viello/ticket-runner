---
project: ticket-runner
last_updated: 2026-11-02T18:45:00
author: Gab
branch: agent/ticket-runner
active_ticket: T135-signal-format-label-and-self-correctable-retry
status: paused
stopped_at:
  file: "runner/domain/failure_analyser.py"
  symbol: "LABEL_SIGNAL_FORMAT (T135 implementation pending)"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [T135: Signal Format Label and Self-Correctable Retry](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T135-signal-format-label-and-self-correctable-retry.md) under [Spec 18](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md).
- **Last Touchpoint**: `runner/domain/runtime_paths.py` and `runner/application/gatekeeper.py` on branch `agent/ticket-runner`.
- **Blockers**: None. T134 malformed signal archive paths and diagnostic log persistence landed in commit `4bf0241` (merged via `ba14a2b`).
- **Next Step**: Add `SIGNAL_FORMAT` failure label and one-shot self-correctable retry logic in `Gatekeeper` via TDD.

## 🎯 Active Tickets & Progress
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
- [ ] `Spec 18 Queue` (`18-signal-contract-hardening`): Signal Contract Hardening and Schema Authority — **IN PROGRESS**
  - Context / Spec: [docs/specs/18-signal-contract-hardening.md](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md)
  - Subtasks:
    - [x] `T130`: [Domain Signal Schema Authority and Gotcha Tolerance](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T130-domain-signal-schema-authority-and-gotcha-tolerance.md) (`f052bb3`)
    - [x] `T131`: [Prompt Renders Domain Protocol and Skill Defers](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T131-prompt-renders-domain-protocol-and-skill-defers.md) (`456a7ec`)
    - [x] `T132`: [Markdown Signal Example Contract Checker](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T132-markdown-signal-example-contract-checker.md) (`0b600d7`)
    - [x] `T133`: [Doctor Pre-Flight and Skills Publish Gate](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T133-doctor-preflight-and-skills-publish-gate.md) (`60434e2`)
    - [x] `T134`: [Malformed Signal Archive and Diagnostic](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T134-malformed-signal-archive-and-diagnostic.md) (`4bf0241`)
    - [ ] `T135`: [Signal Format Label and Self-Correctable Retry](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T135-signal-format-label-and-self-correctable-retry.md)
    - [ ] `T136`: [ADRs, Operating Contract Invariant, and Status Note](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T136-adrs-operating-contract-invariant-and-status-note.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: None (working tree clean).
- **Last Stopped At**: T134 completed and merged to `agent/ticket-runner`; ready for T135.

## 📦 Recent Completed Work & Key Decisions
- **Spec 18 Tracer Bullets (`T130`–`T134`)**:
  - `T130`: Domain Signal Schema Authority and Gotcha Tolerance (`runner/domain/signal_contract.py`).
  - `T131`: Authoritative Signal Protocol rendered dynamically in prompt (`runner/application/prompt_builder.py`).
  - `T132`: Markdown Signal Example Contract Checker (`runner/domain/signal_contract.py`).
  - `T133`: Doctor Pre-Flight Signal Contract Check (`runner/application/doctor.py`) and Skills Catalog Publish Gate (`scripts/publish_agent_skills.py`).
  - `T134`: Malformed Signal Archive (`runner/domain/runtime_paths.py`) and Diagnostic Log Persistence on Escalation (`runner/application/gatekeeper.py`).

## ⚠️ Blockers & Gotchas
- Malformed ready and question signal payloads are archived atomically under `.agent/logs/` before consumption or cleaning.
- Diagnostic reports are persisted to `.agent/logs/<ticket_id>_diagnostic.md` on every escalation attempt before prompting the operator.

## ⏭️ Next 1–3 Actionable Steps
1. Add `SIGNAL_FORMAT` to `runner/domain/failure_analyser.py` (`FAILURE_LABELS`, `SUGGESTED_ACTIONS`).
2. Implement `self_correctable` one-shot retry exemption and status event publishing in `runner/application/gatekeeper.py`.
3. Verify T135 via targeted tests across `tests/unit/domain/test_diagnostic_report.py` and `tests/unit/application/test_verification_loop_escalation.py`.
