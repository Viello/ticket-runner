---
project: ticket-runner
last_updated: 2026-11-02T19:20:00
author: Gab
branch: agent/ticket-runner
active_ticket: T136-adrs-operating-contract-invariant-and-status-note
status: active
stopped_at:
  file: "docs/tickets/18-signal-contract-hardening/T136-adrs-operating-contract-invariant-and-status-note.md"
  symbol: "ADR 0024 & ADR 0025 documentation pending"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [T136: ADRs, Operating Contract Invariant, and Status Note](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T136-adrs-operating-contract-invariant-and-status-note.md) under [Spec 18](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md).
- **Last Touchpoint**: `runner/domain/failure_analyser.py` and `runner/application/gatekeeper.py` on branch `agent/ticket-runner`.
- **Blockers**: None. T135 `SIGNAL_FORMAT` failure label and one-shot self-correctable retry exemption landed in commit `eb2eb8b`.
- **Next Step**: Document ADR 0024 and ADR 0025, update operating contract invariants, record catalog sync status note, and close Spec 18.

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
    - [x] `T135`: [Signal Format Label and Self-Correctable Retry](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T135-signal-format-label-and-self-correctable-retry.md) (`eb2eb8b`)
    - [ ] `T136`: [ADRs, Operating Contract Invariant, and Status Note](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/T136-adrs-operating-contract-invariant-and-status-note.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: None (working tree clean).
- **Last Stopped At**: T135 completed and committed to `agent/ticket-runner`; ready for T136.

## 📦 Recent Completed Work & Key Decisions
- **Spec 18 Tracer Bullets (`T130`–`T135`)**:
  - `T130`: Domain Signal Schema Authority and Gotcha Tolerance (`runner/domain/signal_contract.py`).
  - `T131`: Authoritative Signal Protocol rendered dynamically in prompt (`runner/application/prompt_builder.py`).
  - `T132`: Markdown Signal Example Contract Checker (`runner/domain/signal_contract.py`).
  - `T133`: Doctor Pre-Flight Signal Contract Check (`runner/application/doctor.py`) and Skills Catalog Publish Gate (`scripts/publish_agent_skills.py`).
  - `T134`: Malformed Signal Archive (`runner/domain/runtime_paths.py`) and Diagnostic Log Persistence on Escalation (`runner/application/gatekeeper.py`).
  - `T135`: Signal Format Label (`runner/domain/failure_analyser.py`), One-Shot Retry Exemption, and Status Event Publishing (`runner/application/gatekeeper.py`).

## ⚠️ Blockers & Gotchas
- Malformed ready and question signal payloads are archived atomically under `.agent/logs/` before consumption or cleaning.
- Diagnostic reports are persisted to `.agent/logs/<ticket_id>_diagnostic.md` on every escalation attempt before prompting the operator.
- The one-shot retry exemption applies only when the policy would otherwise escalate and budget remains; it is shared between ready and question signals and is not re-armed on operator circuit breaker retry.

## ⏭️ Next 1–3 Actionable Steps
1. Draft ADR 0024 (Signal Schema Ownership and Contract Checks) and ADR 0025 (Malformed Signal Retention and Retry).
2. Add Signal Schema Authority invariant to `AGENTS.md` operating contract.
3. Record pending Skills Catalog republish note and close Spec 18 alignment ticket T136.
