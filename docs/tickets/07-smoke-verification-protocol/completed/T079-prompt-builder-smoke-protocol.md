# T079 — Worker PromptBuilder smoke protocol and completeness contract
Status: completed
Completed: 2026-09-22T07:01:00Z
Spec: docs/specs/07-smoke-verification-protocol.md
Blocked by: T078

### Requirements
- Update `runner/application/prompt_builder.py` prompt template to reflect Spec 07 invariants and the extended `manual_verification` schema:
  - Update the Ready Signal Protocol description of `manual_verification`: describe `name`, `setup`, `steps`, `expected`, `auto_covered` (bool), and `update_notes` (str).
  - Remove obsolete instructions stating that `manual_verification` should be an empty array if all scenarios are automated.
  - Add explicit instructions: every ticket must have at least one Smoke Scenario; automated tests are additive metadata (`auto_covered: true`) and never allow omitting a scenario; if a ticket lacks `### Smoke Scenarios`, the ticket is incomplete and the Worker must not emit a ready signal.
  - Explain the use of `update_notes` when superseding an earlier ticket's scenario.
- Update `tests/unit/application/test_prompt_builder.py` with tests asserting:
  - The generated prompt contains `auto_covered` and `update_notes` schema documentation.
  - The generated prompt explicitly documents the completeness invariant forbidding ready signals for tickets without smoke scenarios.
- Jump-start:
  - Files to touch: `runner/application/prompt_builder.py`, `tests/unit/application/test_prompt_builder.py`
  - Seams: `PromptBuilder.build` prompt string interpolation
  - Anchor patterns: existing ready signal instructions in `runner/application/prompt_builder.py`
  - Verification: `python -m pytest tests/unit/application/test_prompt_builder.py -x -q`

### Acceptance Criteria
- `PromptBuilder.build()` produces instructions detailing `auto_covered: true/false` and `update_notes`.
- Prompt text enforces that every ticket must define at least one `### Smoke Scenarios` entry and that auto-covered scenarios must not be omitted from `manual_verification`.
- Unit tests in `tests/unit/application/test_prompt_builder.py` cover the new prompt requirements and pass.
- All existing tests in `tests/unit/application/test_prompt_builder.py` pass.

### Smoke Scenarios
**Scenario: Verify worker prompt contains Smoke Scenario protocol**
- Setup: None
- Steps: Run `python -c "from runner.application.prompt_builder import PromptBuilder; from runner.domain.ticket import Ticket; p = PromptBuilder.build(Ticket(id='T999', title='Sample', status='pending', spec_path='x', requirements=(), acceptance_criteria=(), gotchas=(), path='x'), 'excerpt'); assert 'auto_covered' in p and 'update_notes' in p; print('Prompt verified')"`
- Expected: Prints `Prompt verified` with exit code 0.

### Gotchas
- The prompt template in `prompt_builder.py` uses format-string interpolation; remember to double any literal curly braces (`{{` and `}}`) in JSON schema examples to avoid Python `KeyError` or formatting crashes.
