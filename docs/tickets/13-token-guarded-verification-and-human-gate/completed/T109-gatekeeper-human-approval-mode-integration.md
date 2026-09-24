# T109 — Gatekeeper Human Approval Mode Integration
Status: completed
Completed: 2026-09-24T06:30:00Z
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: T107, T108
Security: required

### Requirements
- Extend `LifecycleConfig` with `approval_mode: str` field accepting `"autonomous"` (default) or `"human"`. Validate against an allowlist in `__post_init__`.
- Extend `VerificationLoop` to accept an optional `ApprovalGateway` dependency. When `approval_mode == "human"` and all tests pass, the loop must:
  1. Generate an `EvidenceCard` from the `VerificationReport`, ticket metadata, and smoke scenarios.
  2. Dispatch the card via `ApprovalGateway.request_approval()`.
  3. On `APPROVE`: proceed to commit.
  4. On `REJECT`: loop back into Worker retry with the rejection reason as operator hint.
  5. On `DIAGNOSE`: open a diagnostic session (existing TUI session mechanism).
- In `"autonomous"` mode, the approval gate is skipped entirely (existing behavior).
- Enforce fail-closed authorization: in `"human"` mode, no commit can occur without an explicit `ApprovalDecision.APPROVE`.
- Wire `ApprovalGateway` into the Composition Root (`runner/container.py`) — pass `None` in autonomous mode.
- Jump-start: Work at the seam in `runner/application/gatekeeper.py` (`VerificationLoop.run()`). Read existing `VerificationLoopResult` factory methods. Modify `runner/domain/config.py` `LifecycleConfig`. Update `runner/container.py` to plumb the gateway. Anchor against the `InterventionGateway` plumbing pattern for how ports flow through the container.

### Acceptance Criteria
- `LifecycleConfig(approval_mode="human")` validates; `LifecycleConfig(approval_mode="invalid")` raises `ConfigError`.
- In human mode, `VerificationLoop` dispatches `EvidenceCard` and blocks until `ApprovalDecision` is received.
- `APPROVE` → `VerificationLoopResult.passed()` with approval metadata.
- `REJECT` → Worker retry with rejection reason injected as operator hint.
- `DIAGNOSE` → existing diagnostic session flow triggered.
- In autonomous mode, no `ApprovalGateway` call occurs.
- Security verification: in `"human"` mode, `VerificationLoop` enforces fail-closed authorization (no code commit or pass result is reachable without explicit `ApprovalDecision.APPROVE`; unhandled or missing decisions fail closed to reject/abort).
- Security verification: operator rejection reason is bounded and safely formatted when constructing worker retry hints to prevent prompt injection or credential leakage.
- Unit tests in `tests/unit/application/test_gatekeeper_human_approval.py` using `FakeApprovalGateway` cover: approve, reject-then-approve, autonomous bypass, and fail-closed handling.
- Spec test in `tests/specs/test_spec_13_verification_and_approval.py` simulates a full ticket lifecycle with evidence triage, verification, and mock human approval.

### Smoke Scenarios
**Scenario: Human mode pauses and collects approval** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Validates that in human approval mode, the gatekeeper pauses verification and requests human operator approval with an EvidenceCard before proceeding to commit.
- Steps:
  1. Run the following command in PowerShell to verify `LifecycleConfig` human mode configuration, `EvidenceCard` dispatch, and `ApprovalDecision.APPROVE` collection:
     ```powershell
     python -c @"
     import asyncio
     from runner.domain.config import LifecycleConfig
     from runner.domain.evidence import ApprovalDecision, EvidenceCard
     from tests.fakes.fake_approval_gateway import FakeApprovalGateway

     cfg = LifecycleConfig(approval_mode='human')
     assert cfg.approval_mode == 'human'

     gateway = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])
     card = EvidenceCard(ticket_id='T109', test_status='passed', smoke_scenarios=[{'title': 'Smoke 1'}])
     res = asyncio.run(gateway.request_approval(card))
     assert res == ApprovalDecision.APPROVE
     assert len(gateway.received_cards) == 1
     assert gateway.received_cards[0].ticket_id == 'T109'
     print('SUCCESS: Human mode configured and approval collected!')
     "@
     ```
- Expected:
  - Prints `SUCCESS: Human mode configured and approval collected!`.

**Scenario: Autonomous mode skips approval** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Validates that autonomous mode remains the default behavior and skips the approval gateway completely without regression.
- Steps:
  1. Run the following command in PowerShell to verify default configuration and approval bypass:
     ```powershell
     python -c @"
     from runner.domain.config import LifecycleConfig
     from tests.fakes.fake_approval_gateway import FakeApprovalGateway

     cfg = LifecycleConfig()
     assert cfg.approval_mode == 'autonomous'

     gateway = FakeApprovalGateway(decisions=[])
     assert len(gateway.received_cards) == 0
     print('SUCCESS: Autonomous mode default verified and approval bypassed!')
     "@
     ```
- Expected:
  - Prints `SUCCESS: Autonomous mode default verified and approval bypassed!`.

**Scenario: Reject loops back to Worker** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Validates that an operator rejection safely strips ANSI sequences, redacts secrets, bounds hint length, and allows a subsequent retry cycle to pass on approval.
- Steps:
  1. Run the following command in PowerShell to verify rejection formatting sanitization and multi-cycle approval retry:
     ```powershell
     python -c @"
     import asyncio
     from runner.application.gatekeeper import _format_rejection_hint
     from runner.domain.evidence import ApprovalDecision, EvidenceCard
     from tests.fakes.fake_approval_gateway import FakeApprovalGateway

     gateway = FakeApprovalGateway(decisions=[ApprovalDecision.REJECT, ApprovalDecision.APPROVE])
     card1 = EvidenceCard(ticket_id='T109', test_status='passed')
     decision1 = asyncio.run(gateway.request_approval(card1))
     assert decision1 == ApprovalDecision.REJECT

     raw_feedback = 'Need fix for edge case\x1b[31m colored\x1b[0m and key=sk-abcdef1234567890'
     sanitized = _format_rejection_hint(raw_feedback)
     assert '\x1b' not in sanitized
     assert 'sk-abcdef1234567890' not in sanitized
     assert '[REDACTED]' in sanitized
     assert 'Need fix for edge case' in sanitized

     card2 = EvidenceCard(ticket_id='T109', test_status='passed')
     decision2 = asyncio.run(gateway.request_approval(card2))
     assert decision2 == ApprovalDecision.APPROVE
     assert len(gateway.received_cards) == 2
     print('SUCCESS: Rejection feedback sanitized and retry approval verified!')
     "@
     ```
- Expected:
  - Prints `SUCCESS: Rejection feedback sanitized and retry approval verified!`.

### Gotchas
- The `EvidenceCard` should include smoke scenarios from the ticket's parsed markdown, not from the signal. The ticket parser already extracts these.
- The approval gate fires *after* Gatekeeper tests pass but *before* `CleanSlate` commits — the commit authoring logic in `ticket_processor.py` must respect the new gate.
