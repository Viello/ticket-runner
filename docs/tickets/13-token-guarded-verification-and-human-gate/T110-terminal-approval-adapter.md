# T110 — Terminal Approval Adapter
Status: pending
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: T108

### Requirements
- Implement `TerminalApprovalAdapter` at `runner/adapters/ui/terminal_approval.py` implementing the `ApprovalGateway` protocol.
- On `request_approval(card)`, render the `EvidenceCard` as a Rich panel showing: ticket ID, test status (pass/fail), harness status, evidence directory path, and smoke scenario checklist.
- Capture operator keystroke input: `[y]` approve & commit → `ApprovalDecision.APPROVE`, `[n]` reject & retry → prompt for rejection reason → `ApprovalDecision.REJECT(reason)`, `[d]` open diagnostic session → `ApprovalDecision.DIAGNOSE`.
- Handle `NonInteractiveError` gracefully when no TTY is available (fall back to `REJECT` with "non-interactive terminal" reason).
- Jump-start: Anchor against `runner/adapters/ui/terminal_prompts.py` for Rich prompt patterns and `runner/adapters/ui/keyboard.py` for non-blocking keyboard reading. Follow the adapter pattern in `runner/adapters/ui/model_prompt.py`.

### Acceptance Criteria
- `TerminalApprovalAdapter` satisfies `isinstance(adapter, ApprovalGateway)`.
- Rich panel renders ticket ID, verification status, evidence paths, and smoke scenarios.
- `[y]` → `APPROVE`, `[n]` → prompts for reason → `REJECT`, `[d]` → `DIAGNOSE`.
- Non-interactive fallback returns `REJECT` with descriptive reason.
- Unit tests in `tests/unit/adapters/test_terminal_approval.py` using mocked stdin/Rich console verify all three input paths and the non-interactive fallback.

### Smoke Scenarios
**Scenario: Terminal approve via keystroke**
- Setup: Mock stdin to provide `y` character. Construct an `EvidenceCard` with passing status.
- Why: The terminal is the primary approval surface for Nearby mode — the happy path must render cleanly and capture the keystroke.
- Steps:
  1. Instantiate `TerminalApprovalAdapter` with mocked console and stdin.
  2. Call `await adapter.request_approval(card)`.
  3. Capture rendered output.
- Expected: Returns `ApprovalDecision.APPROVE`. Rich output contains ticket ID, "PASSED" status, and evidence path.

**Scenario: Terminal reject with reason**
- Setup: Mock stdin to provide `n` followed by `"tests look flaky"`.
- Why: Rejection must capture operator feedback to guide the Worker retry — without a reason, the retry prompt has no direction.
- Steps:
  1. Call `await adapter.request_approval(card)`.
  2. Inspect returned decision.
- Expected: Returns `ApprovalDecision.REJECT` with `reason="tests look flaky"`.

### Gotchas
- The Rich panel must not exceed terminal width — use `Console(width=...)` clamping in tests.
- The adapter must work in both sync-wrapped and native async contexts since `TerminalDisplay` is sync-oriented.
