# T091 — Update AGENTS.md with External Invariants & Verification Guardrails
Status: completed
Completed: 2026-09-23T07:56:00Z
Spec: docs/specs/10b-living-documentation-and-roadmap.md
Blocked by: T090
Reasoning: medium

### Requirements
- Update `AGENTS.md` to document new system invariants and operational guardrails:
  1. **External Path Resolution Invariant**: Runner execution treats the Target Project as `CWD`. All paths inside `.agent/` and `docs/` resolve relative to the Target Project root, never assuming the runner's source repository is the working tree.
  2. **Token-Preserving Verification Guardrails**: Behavioral verification harnesses run out-of-band. Raw logs, screenshots, and DOM snapshots are saved to `.agent/evidence/<ticket_id>/` and never dumped into the LLM context. On failure, only a bounded 30-line / 1,000-character excerpt is provided.
  3. **Human-in-the-Loop Gate Invariant**: In Human-in-the-Loop mode, Gatekeeper verification halts after green checks to present an Evidence Card via the active presence channel (Terminal prompt or Discord Status Card); commits strictly require human approval.
  4. **Spec-Closing Alignment Ticket Rule**: Every spec queue under `docs/tickets/<spec-slug>/` must include a final closing ticket tasked with auditing implementation against the spec and updating root living documents if any architectural details shifted.
  5. **Interactive Mode Parity**: Update the execution workflow to note that human approval occurs prior to commit in both interactive and autonomous modes.

### Acceptance Criteria
- `AGENTS.md` Invariants section includes the External Path Resolution Invariant, Token-Preserving Verification Guardrail, Human-in-the-Loop Gate Invariant, and Spec-Closing Alignment Ticket Rule.
- The document conforms to the `writing-for-agents` discipline (clear completion bounds, leading words, positive prompts).
### Suggested Skills
- `writing-for-agents`: Positive prompts over prohibitions, eliminating no-ops, preserving agent context budget.

### Smoke Scenarios
**Scenario: Verify AGENTS.md Invariants and Rules**
- Setup: None (runs from repo root).
- Why: Ensure coding agents following `AGENTS.md` abide by the new external pathing, token budgeting, and approval rules.
- Steps:
  1. Run the Python verification script in PowerShell to assert that all four new invariants and approval workflows are present in `AGENTS.md`:
     ```powershell
     python -c @"
     with open('AGENTS.md', 'r', encoding='utf-8') as f:
         content = f.read()

     checks = {
         'External path resolution': 'Target Project' in content and 'CWD' in content,
         'Token-preserving verification': ('30 lines' in content or '30-line' in content) and '.agent/evidence/' in content,
         'Human-in-the-loop gate': 'Evidence Card' in content and 'human approval' in content,
         'Spec-closing alignment ticket': 'closing ticket' in content and 'living documents' in content,
         'Interactive mode parity': 'human approval' in content and 'interactive' in content,
     }

     missing = [k for k, v in checks.items() if not v]
     if missing:
         print('FAILED CHECKS:', missing)
         exit(1)

     print('PASS: All invariants and verification guardrails verified in AGENTS.md.')
     "@
     ```
  2. Inspect the terminal output for the `PASS` confirmation message and exit code 0.
- Expected: Script prints `PASS: All invariants and verification guardrails verified in AGENTS.md.` with exit code 0.

### Gotchas
- Keep `AGENTS.md` lean: avoid verbose prose that bloats agent context windows; use tight leading words.
