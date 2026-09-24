# T108 — Approval Gateway Port & Fake Double
Status: completed
Completed: 2026-09-24T02:18:02Z
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
**Scenario: Fake gateway approve flow** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Validates that the test double correctly records incoming evidence cards and replays an approval decision, which all downstream Gatekeeper human-approval tests depend on.
- Steps:
  1. Run the following self-contained Python command in PowerShell to instantiate `FakeApprovalGateway` with an approval decision, submit an `EvidenceCard`, and verify recording and decision output:
     ```powershell
     python -c @"
     import asyncio
     from runner.domain.evidence import ApprovalDecision, EvidenceCard
     from tests.fakes.fake_approval_gateway import FakeApprovalGateway

     async def main():
         gateway = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])
         card = EvidenceCard(ticket_id='T108', test_status='passed')
         res = await gateway.request_approval(card)
         assert res == ApprovalDecision.APPROVE
         assert gateway.received_cards == [card]
         print('SUCCESS: Received approval and card recorded!')

     asyncio.run(main())
     "@
     ```
- Expected:
  - Prints `SUCCESS: Received approval and card recorded!`.

**Scenario: Fake gateway exhaustion** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Ensures tests fail fast with an `IndexError` if more approvals are requested than scripted, catching test configuration errors immediately.
- Steps:
  1. Run the following self-contained Python command in PowerShell to verify `FakeApprovalGateway` raises `IndexError` when decisions are exhausted:
     ```powershell
     python -c @"
     import asyncio
     from runner.domain.evidence import EvidenceCard
     from tests.fakes.fake_approval_gateway import FakeApprovalGateway

     async def main():
         gateway = FakeApprovalGateway(decisions=[])
         card = EvidenceCard(ticket_id='T108', test_status='passed')
         try:
             await gateway.request_approval(card)
             print('FAILURE: Expected IndexError!')
         except IndexError:
             print('SUCCESS: FakeApprovalGateway raised IndexError when exhausted!')

     asyncio.run(main())
     "@
     ```
- Expected:
  - Prints `SUCCESS: FakeApprovalGateway raised IndexError when exhausted!`.

### Gotchas
- The protocol method must be `async` because both the terminal and Discord adapters will perform I/O (blocking input or network calls).
- `FakeApprovalGateway` raises `IndexError` on decision exhaustion rather than returning a default or raising generic assertions, enforcing loud and immediate failure when test suites under-script decisions.
