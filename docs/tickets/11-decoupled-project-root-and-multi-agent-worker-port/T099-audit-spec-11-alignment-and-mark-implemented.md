# T099 — Audit Spec 11 Alignment and Mark Spec Implemented
Status: pending
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
Blocked by: T098
Reasoning: medium

### Requirements
- Execute the closing audit for Spec 11:
  1. Review all implemented code, tests, and CLI flags against all 13 user stories and implementation decisions of `docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md`.
  2. Verify markdown links and code block fence balance across all updated documentation files (`ARCHITECTURE.md`, `README.md`, `CONTEXT.md`, `AGENTS.md`).
  3. Verify that terminology is 100% consistent across all documents and zero forbidden synonyms from `CONTEXT.md` are used.
  4. Update `AGENTS.md` Implementation status marking Spec 11 as implemented.
  5. Record any cross-ticket lessons learned in `docs/tickets/gotchas.md`.
  6. Mark the ticket completed and relocate to `docs/tickets/11-decoupled-project-root-and-multi-agent-worker-port/completed/T099-audit-spec-11-alignment-and-mark-implemented.md`.
- Jump-start:
  - Files to touch: `AGENTS.md`, `docs/tickets/gotchas.md`, `ARCHITECTURE.md`, `README.md`, `CONTEXT.md`.
  - Seams: Spec 11 alignment audit script, documentation review.
  - Verification: Run documentation audit script in PowerShell and `pytest tests/specs/test_spec_11_decoupled_runner.py`.

### Acceptance Criteria
- All 13 user stories and decisions from Spec 11 are verified as implemented and tested.
- Zero terminology collisions with `CONTEXT.md` forbidden synonyms.
- `AGENTS.md` reflects Spec 11 as implemented.
- `docs/tickets/gotchas.md` contains any lessons learned during Spec 11 execution.

### Smoke Scenarios
**Scenario: End-to-End Alignment Audit** [also auto-covered]
- Setup: None (runs from repo root).
- Why: Confirm the repository is fully aligned with Spec 11, links and code blocks are valid, and domain terminology is clean before proceeding to Spec 12.
- Steps:
  1. Run PowerShell verification script testing forbidden terms, code fence balance, and spec completion status in `AGENTS.md`:
     ```powershell
     python -c @"
     from pathlib import Path
     import re

     agents_md = Path('AGENTS.md').read_text(encoding='utf-8')
     assert 'Specs 01–11' in agents_md or 'Spec 11' in agents_md, 'AGENTS.md not updated with Spec 11 status'

     for f in ['README.md', 'ARCHITECTURE.md', 'AGENTS.md', 'CONTEXT.md', 'docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md']:
         text = Path(f).read_text(encoding='utf-8')
         lines = text.splitlines()
         quad = sum(1 for line in lines if line.strip().startswith(chr(96)*4))
         tri = sum(1 for line in lines if line.strip().startswith(chr(96)*3) and not line.strip().startswith(chr(96)*4))
         assert quad % 2 == 0 and tri % 2 == 0, f'Unbalanced code fence in {f}'

     print('PASS: Spec 11 alignment and living documentation verified.')
     "@
     ```
  2. Run `pytest tests/unit tests/specs/test_spec_11_decoupled_runner.py`.
- Expected: Terminal prints `PASS: Spec 11 alignment and living documentation verified.` with exit code 0.

### Gotchas
- This is the closing alignment ticket for Spec 11. It must not add new features, only audit and verify alignment.
