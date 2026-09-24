# T109 — Gatekeeper Human Approval Mode Integration
Status: pending
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
**Scenario: Human mode pauses and collects approval**
- Setup: Set `lifecycle.approval_mode: "human"` in test config. Wire `FakeApprovalGateway` with `APPROVE`.
- Why: This is the critical new behavior — verification must pause for human sign-off before any commit in human mode.
- Steps:
  1. Run `VerificationLoop` with a passing cycle runner and green gatekeeper.
  2. Assert `FakeApprovalGateway.received_cards` has exactly one `EvidenceCard`.
  3. Assert `VerificationLoopResult.is_passed` is True.
- Expected: Card dispatched, approval received, result is passed. No commit should happen inside the loop itself.

**Scenario: Autonomous mode skips approval**
- Setup: Set `lifecycle.approval_mode: "autonomous"` (default). Wire `FakeApprovalGateway`.
- Why: Existing autonomous behavior must remain unbroken — this guards against regressions.
- Steps:
  1. Run `VerificationLoop` with a passing cycle runner.
  2. Assert `FakeApprovalGateway.received_cards` is empty.
- Expected: No approval requested. Result is passed immediately.

**Scenario: Reject loops back to Worker**
- Setup: Set `lifecycle.approval_mode: "human"`. Wire `FakeApprovalGateway` with `[REJECT, APPROVE]`.
- Why: Rejection must trigger a Worker retry with the operator's feedback, not silently swallow it.
- Steps:
  1. Run `VerificationLoop` with two cycle passes.
  2. Assert first cycle triggered rejection, second triggered approval.
  3. Assert the retry prompt contains the rejection reason.
- Expected: Two cards dispatched. Final result is passed after the second approval.

### Gotchas
- The `EvidenceCard` should include smoke scenarios from the ticket's parsed markdown, not from the signal. The ticket parser already extracts these.
- The approval gate fires *after* Gatekeeper tests pass but *before* `CleanSlate` commits — the commit authoring logic in `ticket_processor.py` must respect the new gate.
