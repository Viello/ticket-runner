# T110 — Terminal Approval Adapter
Status: completed
Completed: 2026-09-27T12:24:45Z
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
- Setup: None (runs directly from repo root with Python).
- Why: Tests that the terminal approval adapter displays the evidence card in a Rich panel and captures the operator pressing 'y' to approve the verification.
- Steps:
  1. Run the following command in PowerShell to instantiate `TerminalApprovalAdapter` with mocked stdin providing `'y\n'`, verify that `request_approval` renders the ticket details, and confirm that `ApprovalDecision.APPROVE` is returned:
     ```powershell
     python -c "import asyncio, io; from rich.console import Console; from runner.adapters.ui.terminal_approval import TerminalApprovalAdapter; from runner.domain.evidence import ApprovalDecision, EvidenceCard; MockStdin = type('MockStdin', (), {'__init__': lambda self, content: (setattr(self, '_s', io.StringIO(content))), 'isatty': lambda self: True, 'read': lambda self, n=1: self._s.read(n), 'readline': lambda self: self._s.readline()}); out = io.StringIO(); adapter = TerminalApprovalAdapter(console=Console(file=out, width=80), stdin=MockStdin('y\n')); card = EvidenceCard(ticket_id='T110', test_status='passed', evidence_paths=('.agent/evidence/T110',)); res = asyncio.run(adapter.request_approval(card)); assert res == ApprovalDecision.APPROVE; rendered = out.getvalue(); assert 'T110' in rendered and 'PASSED' in rendered and '.agent/evidence/T110' in rendered; print('PASS: Terminal approve via keystroke')"
     ```
- Expected: Prints `PASS: Terminal approve via keystroke` with exit code 0.

**Scenario: Terminal reject with reason**
- Setup: None (runs directly from repo root with Python).
- Why: Tests that pressing 'n' prompts the operator for a rejection explanation and returns `ApprovalDecision.REJECT` annotated with the provided feedback to direct the worker retry.
- Steps:
  1. Run the following command in PowerShell to simulate an operator hitting `'n'` and providing `"tests look flaky"` as the rejection reason:
     ```powershell
     python -c "import asyncio, io; from rich.console import Console; from runner.adapters.ui.terminal_approval import TerminalApprovalAdapter; from runner.domain.evidence import ApprovalDecision, EvidenceCard; MockStdin = type('MockStdin', (), {'__init__': lambda self, content: (setattr(self, '_s', io.StringIO(content))), 'isatty': lambda self: True, 'read': lambda self, n=1: self._s.read(n), 'readline': lambda self: self._s.readline(), 'tell': lambda self: self._s.tell(), 'seek': lambda self, p, w=0: self._s.seek(p, w)}); mock_stdin = MockStdin('n\ntests look flaky\n'); adapter = TerminalApprovalAdapter(console=Console(file=io.StringIO(), width=80), stdin=mock_stdin); card = EvidenceCard(ticket_id='T110', test_status='passed'); res = asyncio.run(adapter.request_approval(card)); assert res == ApprovalDecision.REJECT; assert res.reason == 'tests look flaky'; print('PASS: Terminal reject with reason')"
     ```
- Expected: Prints `PASS: Terminal reject with reason` with exit code 0.

### Gotchas
- The Rich panel must not exceed terminal width — use `Console(width=...)` clamping in tests.
- The adapter must work in both sync-wrapped and native async contexts since `TerminalDisplay` is sync-oriented.
