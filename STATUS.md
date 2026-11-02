---
project: ticket-runner
last_updated: 2026-11-02T19:40:00
author: Gab
branch: agent/ticket-runner
active_ticket: null
status: active
stopped_at:
  file: "docs/specs/18-signal-contract-hardening.md"
  symbol: "Spec 18 Completed; Pending Skills Catalog Republish"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: [Spec 18: Signal Contract Hardening and Schema Authority](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md) — **COMPLETED**.
- **Last Touchpoint**: Documentation & Operating Invariants (`docs/adr/0024-signal-schema-ownership-and-contract-checks.md`, `docs/adr/0025-malformed-signal-retention-and-retry.md`, `docs/adr/0017-invalid-signal-consumes-verification-attempt.md`, `AGENTS.md`, `docs/tickets/gotchas.md`).
- **Blockers**: None. Full test suite green, linter and typechecker clean.
- **Next Step**: Explicit operator action: republish Skills Catalog (`scripts/publish_agent_skills.py` to `Viello/agent-skills`). Proceed to `/live-qa` or next spec.

## 🎯 Active Tickets & Progress
- [x] `Spec 17 Queue` (`17-human-first-ticket-document-format`): Human-First Ticket Document Format with Checkbox Acceptance Criteria — **COMPLETED**
- [x] `Spec 18 Queue` (`18-signal-contract-hardening`): Signal Contract Hardening and Schema Authority — **COMPLETED**
  - Context / Spec: [docs/specs/18-signal-contract-hardening.md](file:///d:/Projects/docs/specs/18-signal-contract-hardening.md)
  - Subtasks:
    - [x] `T130`: [Domain Signal Schema Authority and Gotcha Tolerance](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T130-domain-signal-schema-authority-and-gotcha-tolerance.md) (`f052bb3`)
    - [x] `T131`: [Prompt Renders Domain Protocol and Skill Defers](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T131-prompt-renders-domain-protocol-and-skill-defers.md) (`456a7ec`)
    - [x] `T132`: [Markdown Signal Example Contract Checker](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T132-markdown-signal-example-contract-checker.md) (`0b600d7`)
    - [x] `T133`: [Doctor Pre-Flight and Skills Publish Gate](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T133-doctor-preflight-and-skills-publish-gate.md) (`60434e2`)
    - [x] `T134`: [Malformed Signal Archive and Diagnostic](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T134-malformed-signal-archive-and-diagnostic.md) (`4bf0241`)
    - [x] `T135`: [Signal Format Label and Self-Correctable Retry](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T135-signal-format-label-and-self-correctable-retry.md) (`eb2eb8b`)
    - [x] `T136`: [ADRs, Operating Contract Invariant, and Status Note](file:///d:/Projects/docs/tickets/18-signal-contract-hardening/completed/T136-adrs-operating-contract-invariant-and-status-note.md)

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner`
- **Uncommitted Files**: None (working tree clean).
- **Last Stopped At**: Spec 18 closed with T136; all binding decisions recorded.

## 📦 Recent Completed Work & Key Decisions
- **Spec 18 Complete**:
  - `T130`: Domain Signal Schema Authority and Gotcha Tolerance (`runner/domain/signal_contract.py`).
  - `T131`: Authoritative Signal Protocol rendered dynamically in prompt (`runner/application/prompt_builder.py`).
  - `T132`: Markdown Signal Example Contract Checker (`runner/domain/signal_contract.py`).
  - `T133`: Doctor Pre-Flight Signal Contract Check (`runner/application/doctor.py`) and Skills Catalog Publish Gate (`scripts/publish_agent_skills.py`).
  - `T134`: Malformed Signal Archive (`runner/domain/runtime_paths.py`) and Diagnostic Log Persistence on Escalation (`runner/application/gatekeeper.py`).
  - `T135`: Signal Format Label (`runner/domain/failure_analyser.py`), One-Shot Retry Exemption, and Status Event Publishing (`runner/application/gatekeeper.py`).
  - `T136`: ADR 0024 (Signal Schema Ownership and Contract Checks), ADR 0025 (Malformed Signal Retention and Retry), ADR 0017 amendment, `AGENTS.md` invariant, and gotchas update.

## ⚠️ Pending Operator Step: Skills Catalog Republish
- Publishing the updated Skills Catalog is an explicit manual operator step (`py -3 scripts/publish_agent_skills.py` against `Viello/agent-skills`).
- Until published and synced, provisioned Target Projects rely on in-place skill repair, and any future catalog sync would overwrite hand repairs until the upstream catalog is updated.

## 🔬 Verification Evidence
- Targeted domain, application, and spec suites pass 100%.
- Full test suite: `py -3 -m pytest -q` passing with 0 failures.
- Ruff and mypy clean across all modified files.

## ⏭️ Next 1–3 Actionable Steps
1. Operator action: Run `py -3 scripts/publish_agent_skills.py` to publish the updated skills catalog to `Viello/agent-skills`.
2. Optional post-green verification via `/live-qa`.
3. Proceed to the next specification queue.
