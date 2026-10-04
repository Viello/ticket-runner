# T119 — Spec 14 closing alignment audit
Status: pending
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
