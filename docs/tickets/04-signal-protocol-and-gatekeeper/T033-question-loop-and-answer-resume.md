# T033 — Question loop and answer resume
Status: pending
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T032

### Requirements
- Handle a pending question in the processor: prompt through `InterventionGateway.ask_question`, write the answer back by rewriting the question Signal (`status: answered`, `answer`), resume the same Worker Session with a prompt carrying the answer (`User answered: <answer>. Proceed with implementation.`), and continue the loop with the budget preserved.
- Precedence when both Signal files exist: a valid ready Signal wins; the stale question is never prompted and is cleaned so it cannot re-trigger.
- A malformed pending question is a failed Verification Attempt with the parse error as diagnostics, matching the ready-Signal regime.
- Sequential questions are supported and never consume the attempt budget.
- Jump-start:
  - Files to touch: `runner/application/ticket_processor.py`, `tests/unit/application/test_ticket_processor.py`, `tests/specs/test_spec_04_gatekeeper.py` (append).
  - Seams: `SignalRepository.read_pending_question` and `write_answer`; loop re-entry with the same session id; scripted answers via the intervention fake.
  - Anchor patterns: resume-with-session tests in `tests/unit/application/test_handoff_coordinator.py`.
  - Verification: `pytest tests/unit/application/test_ticket_processor.py tests/specs/test_spec_04_gatekeeper.py`.

### Acceptance Criteria
- Behavioral: a choice question leads to a scripted answer `A`, the on-disk JSON shows `answered` plus `A`, the resume prompt contains the answer, and a subsequent ready Signal reaches commit.
- Two sequential questions both work with the budget counter unchanged afterwards.
- Ready-wins: with a pending question and a valid ready Signal, verification proceeds with no prompt and the stale question no longer interrupts.
- A malformed question consumes one attempt with the parse error fed back as diagnostics.

### Gotchas
- The answer rewrite must be atomic and preserve every other question field.
- Never resume with a new session id — questions continue the active Worker Session.
- The answered file is retained for audit; single-use deletion applies only to the ready Signal.
