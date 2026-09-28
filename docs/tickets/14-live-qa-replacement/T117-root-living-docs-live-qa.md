# T117 — Root living documents re-pointed at the live-qa ritual
Status: pending
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: T116

### Requirements
- Rewrite the root living documents so they describe the live-qa verification story and carry no surviving instruction that asks any agent to author, embed, echo, or log smoke scenarios:
  - `AGENTS.md`: the two smoke-scenario invariants (scenario-completeness rule; LLM-generated-scenarios/human-verification/smoke-log rule) are replaced by the live-qa invariant — human verification happens via a human-invoked `/live-qa` session after green checks; durable verdicts are recorded by the human's session at `.agent/live-qa_log_<slug>.md`; the Gatekeeper authors no verification logs. The interactive-commit workflow bullet and the Smoke-log-review workflow bullet are rewritten accordingly (failure triage: read `[failed]` entries from the live-qa log, debug via `/diagnosing-bugs`, recover via `/smoke-fail`). Add `live-qa` to the domain vocabulary usage where relevant (`CONTEXT.md` sync belongs to T119's audit if glossary entries shift).
  - `README.md`: the ticket-decomposition paragraph (currently "defines requirements, acceptance criteria, smoke scenarios, and gotchas") and the Human Gate & Completion paragraphs (Evidence Card scenario checklist + smoke-log logging) are rewritten to match the shipped behavior of T115/T116.
- **This ticket's AGENTS.md edits are pre-approved by the user** (spec 14 approval conversation); honor the "don't bulk-reformat" rule — surgical line edits only.
- Jump-start:
  - Files to touch: `AGENTS.md` (invariants block lines ~33–34, workflow lines ~56, ~64), `README.md` (lines ~142, ~147, ~569, ~605).
  - Anchor: the shipped code after T115/T116 is the source of truth — read `runner/application/prompt_builder.py` invariant text and mirror its wording, keeping a single source of truth between Worker prompt and AGENTS.md.
  - Process: **load and apply `/writing-for-agents`** before editing — the invariants are always-loaded context pointers; prune to triggers, keep leading words (`live-qa`, `Evidence Card`, `Gatekeeper`), state prohibitions positively.
  - Verification: `Select-String -Path AGENTS.md,README.md -Pattern "smoke" -CaseSensitive:$false` returns only the Discord `bot --smoke` transport-test references and historical Gotchas pointers — zero scenario-rule references.

### Acceptance Criteria
- No AGENTS.md or README instruction requires an agent to write, carry, render, or log smoke scenarios.
- The live-qa invariant text is unambiguous: human-driven session after green checks; log path and refusal-in-absence semantics stated; Gatekeeper explicitly excluded from verdict authorship.
- Wording of the AGENTS.md invariant and the Worker prompt invariant (T115) is identical or one points at the other — no duplicated drift-prone restatement.
- Docs-only change: full test suite still green (`python -m pytest`).

### Smoke Scenarios
**Scenario: no-requirement grep**
- Setup: Repo root at T117 completion.
- Why: The living documents must stop commanding a mechanism that no longer exists; a leftover line silently re-injects the old discipline into every future Worker prompt.
- Steps: 1. Search `AGENTS.md`, `README.md`, `ARCHITECTURE.md`, `CONTEXT.md` for scenario-related instruction ("smoke scenario", "manual_verification", "smoke_log"). 2. Read the surviving matches.
- Expected: Only legitimate survivors remain — `bot --smoke` (Discord transport check), `/smoke-fail` (triage skill name), historical `docs/tickets/gotchas.md` entries, and the new live-qa pointers. Zero lines instructing anyone to author or log scenarios.

### Gotchas
- `.agents/skills/` copies of edited skills are vendored; the canonical catalog edit belongs to T118 — do not edit skill files here.
- `docs/tickets/gotchas.md` and completed tickets are history: never rewrite them; they legitimately mention the old mechanism.
