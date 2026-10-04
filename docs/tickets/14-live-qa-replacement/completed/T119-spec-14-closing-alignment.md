# T119 — Spec 14 closing alignment audit
Status: completed
Completed: 2026-10-04T07:34:00Z
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: T114, T115, T116, T117, T118

### Requirements
- Audit the shipped system against every Spec 14 user story (1–14) and every Implementation Decision; where reality shifted from the spec, update the spec or the living documents so they describe what is actually true. Working code, unit tests, and CLI interfaces are authoritative.
- Retire the "migration overlap" Further Note once no dual mechanism remains observable.
- CONTEXT.md glossary pass: ensure the domain language reflects the live-qa ritual (the term `Live QA Session` and its listed synonyms), and that no glossary entry still defines a smoke-scenario term as active; historical entries may be marked superseded, never deleted.
- Verify the whole chain as shipped: Worker prompt (no scenario text) → ready signal (no manual_verification) → Gatekeeper (no smoke log) → Evidence Card (no checklist) → `notify` streaming works for a real human-driven `/live-qa` session against the Runner itself (e.g. drive the queue loop once and stream two verdicts).
- Jump-start:
  - Files to touch: `docs/specs/14-live-qa-replacement.md`, `CONTEXT.md`, `ARCHITECTURE.md` (only if the directory tree drifted from reality); root-doc edits require and already carry user approval from the spec-14 conversation — surgical only.
  - Verification: full suite `python -m pytest`; repo-wide scenario-mechanism grep as defined in T117.

### Audit Evidence
1. **User Story 1 (Human-driven verification)**: Shipped in `.agents/skills/live-qa/` where the operator acts as sensor driving real scenarios interactively.
2. **User Story 2 (Durable timestamped log)**: Shipped via append-only `.agent/live-qa_log_<slug>.md` recording ISO-8601 timestamps and exact human observation words.
3. **User Story 3 (Refusal in absence)**: Shipped in `live-qa` guardrails explicitly refusing or skipping verification when the human is not present at the machine.
4. **User Story 4 (Per-scenario Discord stream)**: Shipped via `.agent/live-qa.json` `notify_cmd` invoking `ticket-runner notify <message>`.
5. **User Story 5 (Evidence Card without checklist)**: Shipped in T116; `EvidenceCard` and approval adapters (terminal and Discord) omit scenario fields and render strictly machine-verified results.
6. **User Story 6 (No mandatory smoke scenarios in ticket authoring)**: Shipped in T118; `to-tickets` dropped mandatory smoke scenarios sections and quiz checks.
7. **User Story 7 (Ready signal schema freed of manual verification)**: Shipped in T115; `ReadySignal` dataclass and validator dropped `manual_verification`, with unknown-key tolerance for historical signals.
8. **User Story 8 (Gatekeeper stops smoke logging)**: Shipped in T116; `VerificationLoop` dropped `_append_smoke_log` and `smoke_log_path`.
9. **User Story 9 (Fail-closed human approval intact)**: Shipped in T116; `VerificationLoop` requires explicit `ApprovalDecision.APPROVE` in human mode to reach commit.
10. **User Story 10 (One-shot notify CLI)**: Shipped in T114; `ticket_runner.py notify <message>` subcommand posts single message and exits cleanly.
11. **User Story 11 (Triage via smoke-fail)**: Shipped in T118; `smoke-fail` skill parses `[failed]` entries from `.agent/live-qa_log_<slug>.md`.
12. **User Story 12 (Templates teach live-qa discipline)**: Shipped in T115 & T118; `PromptBuilder` invariants and skills teach post-green `/live-qa`.
13. **User Story 13 (Living documents reflect live-qa gate)**: Shipped in T117 & T119; `AGENTS.md`, `README.md`, `CONTEXT.md`, and `ARCHITECTURE.md` aligned with zero contradictions.
14. **User Story 14 (Parser tolerates legacy headings)**: Shipped in T115; `TicketMarkdownParser` treats `### Smoke Scenarios` as inert markdown without error.

### Acceptance Criteria
- Every Spec 14 user story is checked off against observed behavior (evidence noted in the ticket body before relocation).
- Spec, CONTEXT.md, AGENTS.md, README, and shipped behavior agree with zero contradictions.
- The closing live-qa session's verdicts land in `.agent/live-qa_log_<slug>.md` and stream to Discord via `notify` in the same run.
- The migration-overlap note is removed from the spec.

### Smoke Scenarios
**Scenario: full-chain live-qa rehearsal**
- Setup: Discord configured and reachable; a scratch pending ticket with an implemented change; app under test = the Runner terminal UI itself; bot credentials present.
- Why: This is the spec's entire promise in one motion — a human driving the real app while machines record and stream, with nothing authoring scenario text.
- Steps: 1. Run the Gatekeeper cycle to an Evidence Card; confirm no checklist renders. 2. Run `/live-qa` on the change with two human-driven scenarios (one verified, one skipped). 3. Watch the Discord channel during the session. 4. Open the live-qa log after.
- Expected: Card shows machine-checked facts only; log holds exactly two timestamped entries in the shipped format with `[skipped]` carrying a reason; Discord received one streamed line per verdict; no `smoke_log_*` file exists.

### Gotchas
- If T117/T118 landed with drift, fix the documents here rather than reopening code tickets — code is truth.
