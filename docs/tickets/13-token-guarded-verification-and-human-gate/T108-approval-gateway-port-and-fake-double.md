# T108 — Approval Gateway Port & Fake Double
Status: pending
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: T107

### Requirements
- Define the `ApprovalGateway` protocol port at `runner/ports/approval_gateway.py` with a single async method: `request_approval(card: EvidenceCard) -> ApprovalDecision`.
- Build `FakeApprovalGateway` test double at `tests/fakes/fake_approval_gateway.py` that accepts a pre-scripted sequence of `ApprovalDecision` values, records all `EvidenceCard`s received, and replays decisions in order.
- Wire the new port into `runner/ports/__init__.py` exports.
- Jump-start: Follow the existing port pattern in `runner/ports/intervention.py` (Protocol with `@runtime_checkable`). Model the fake after `tests/fakes/fake_intervention.py`. Import `EvidenceCard` and `ApprovalDecision` from the domain module created in T107.

### Acceptance Criteria
- `ApprovalGateway` is a `@runtime_checkable Protocol` with `async def request_approval(self, card: EvidenceCard) -> ApprovalDecision`.
- `FakeApprovalGateway` records received cards in `.received_cards` and returns pre-scripted decisions from a queue.
- `FakeApprovalGateway` raises `IndexError` when decisions are exhausted (fail-fast in tests).
- Unit tests in `tests/unit/ports/test_approval_gateway.py` verify protocol compliance and fake behavior.

### Smoke Scenarios
**Scenario: Fake gateway approve flow**
- Setup: None (runs from repo root).
- Why: Validates that the test double correctly replays an approval decision, which all downstream Gatekeeper tests depend on.
- Steps:
  1. Create `FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])`.
  2. Call `await gateway.request_approval(card)`.
  3. Inspect `gateway.received_cards`.
- Expected: Returns `ApprovalDecision.APPROVE`. `gateway.received_cards` contains the submitted card.

**Scenario: Fake gateway exhaustion**
- Setup: None (runs from repo root).
- Why: Ensures tests fail fast if more approvals are requested than scripted, catching test setup bugs.
- Steps:
  1. Create `FakeApprovalGateway(decisions=[])`.
  2. Call `await gateway.request_approval(card)`.
- Expected: Raises `IndexError`.

### Gotchas
- The protocol method must be `async` because both the terminal and Discord adapters will perform I/O (blocking input or network calls).
