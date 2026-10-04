# T099 — Audit Spec 15 Alignment and Mark Spec Implemented
**Type:** wayfinder:task (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012, T013, T014, T015, T016, T017, T018, T019, T020, T021
Reasoning: medium

### Question

Execute the closing audit for Spec 15:

1. Verify all 17 work tickets (T001-T017) have been implemented and tested.
2. Audit `AGENTS.md`, `ARCHITECTURE.md`, `README.md`, `CONTEXT.md` for any
   architectural detail that shifted during Spec 15 implementation (e.g. the
   `AgentWorker` port if a third backend emerged, new env vars, new live-test
   sites).
3. Verify terminology in the new docs (`docs/agents/live-test-sites.md`,
   ADR-0023) is consistent with `CONTEXT.md` and zero forbidden synonyms are
   used.
4. Verify markdown links and code-block fence balance across all updated files.
5. Update `AGENTS.md` Implementation status marking Spec 15 as implemented.
6. Record any cross-ticket lessons learned in `docs/tickets/gotchas.md`.
7. Mark this ticket completed and relocate to
   `docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T099-...md`
   per ADR 0012 (ephemeral queue clean-slate).

### Why this matters

Spec-closing alignment is the gatekeeper for `AGENTS.md` invariants: the closing
ticket ensures the implementation matches the spec, terminology stays canonical,
and root living documents reflect reality. Skipping this leaves architectural
details drifting.

### Requirements

- All 17 prior tickets (T001-T017) must be marked `Status: completed` before this
  ticket may proceed.
- Run the documentation fence-balance / spec-completion verification script (see
  the example in
  `.agent/archive/11-decoupled-project-root-and-multi-agent-worker-port/completed/T099-audit-spec-11-alignment-and-mark-implemented.md`
  for the script structure).
- Run the test suite:
  `pytest tests/unit tests/specs/test_spec_15_multi_agent_and_live_test.py`
  (the spec test must be created during T012 or earlier; if not, this ticket
  creates it).
- Update `AGENTS.md` Implementation status: "Specs 01–15" replacing "Specs 01–14".
- Append any gotchas discovered during Spec 15 execution to `docs/tickets/gotchas.md`.

### Acceptance Criteria

- All 17 prior tickets closed.
- `AGENTS.md` reflects Spec 15 as implemented.
- `ARCHITECTURE.md` updated if any new adapter / port / directory emerged.
- `README.md` updated if any user-facing CLI flag or config key was added.
- `CONTEXT.md` glossary updated if any new domain term was introduced.
- `docs/tickets/gotchas.md` contains any lessons learned.
- This ticket marked `Status: completed` and relocated to
  `docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T099-audit-spec-15-alignment-and-mark-implemented.md`.

### Smoke Scenarios

**Scenario: End-to-End Spec 15 Alignment Audit**

- Setup: All 17 prior tickets must be completed.
- Why: Confirm the repository is fully aligned with Spec 15, links and code blocks
  are valid, and domain terminology is clean before proceeding to Spec 16 (or
  next effort).
- Steps:
  1. Run PowerShell verification script testing forbidden terms, code fence
     balance, and Spec 15 completion status in `AGENTS.md`.
  2. Run the unit suite + spec test for Spec 15.
  3. Confirm `AGENTS.md` mentions "Specs 01–15" (or equivalent).
- Expected: All steps pass.

### Gotchas

- This ticket must NOT add new features — only audit and verify alignment.
- If architectural details shifted, update root living documents. If they did
  not, leave them alone (per `AGENTS.md` invariant: "never modify root living
  documents without explicit user approval" — but spec-closing alignment is the
  *one* approved modification context).