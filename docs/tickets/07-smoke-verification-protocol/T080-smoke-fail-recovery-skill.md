# T080 — Smoke failure recovery skill and regression ticket template
Status: pending
Spec: docs/specs/07-smoke-verification-protocol.md
Blocked by: T079

### Requirements
- Update `.agents/skills/smoke-fail/SKILL.md` to provide a complete interactive recovery guide when an operator encounters a failed smoke scenario during batch review:
  - Reference the durable smoke log at `.agent/smoke_log_<spec-slug>.md`.
  - Provide a step-by-step triage sequence: locate scenario in the log, capture observed vs expected outcome, trigger `/diagnosing-bugs` if an active test loop is needed.
  - Specify the standard regression ticket format adhering strictly to the Ticket Runner domain schema (`Status: pending`, `### Requirements`, `### Acceptance Criteria`, `### Smoke Scenarios`, `### Gotchas`).
  - Ensure the regression ticket automatically copies the failing smoke scenario into its own `### Smoke Scenarios` section so that the fix is verified against the human check.
  - Fix any legacy header references (e.g. replace `Status: todo` with `Status: pending`).
- Jump-start:
  - Files to touch: `.agents/skills/smoke-fail/SKILL.md`
  - Anchor patterns: `ticket-runner-template` in `.agents/skills/to-tickets/SKILL.md`, ticket entity parser in `runner/domain/ticket.py`
  - Verification: Validate markdown structure and ensure template compatibility with `runner.domain.ticket.Ticket.parse`

### Acceptance Criteria
- `.agents/skills/smoke-fail/SKILL.md` documents the batch review failure triage steps against `.agent/smoke_log_<spec-slug>.md`.
- Regression ticket template adheres strictly to `Ticket.parse` format (`Status: pending`, standard sections).
- The skill instructs the agent to embed the failing scenario into the regression ticket's `### Smoke Scenarios`.
- No non-standard frontmatter or invalid status strings are present in the skill template.

### Smoke Scenarios
**Scenario: Verify regression ticket template validity with Ticket parser**
- Setup: Create a test string containing the template defined in `smoke-fail/SKILL.md`.
- Steps: Run `python -c "from runner.domain.ticket import Ticket; content = '''# T999 — Smoke regression: Sample\nStatus: pending\nSpec: docs/specs/07-smoke-verification-protocol.md\nBlocked by: None\n\n### Requirements\n- Fix issue\n\n### Acceptance Criteria\n- Works\n\n### Smoke Scenarios\n**Scenario: Retry**\n- Setup: None\n- Steps: Test\n- Expected: Pass\n\n### Gotchas\n- None\n'''; t = Ticket.parse(content, 'T999'); assert t.id == 'T999'; print('Template valid')"`
- Expected: Prints `Template valid` with exit code 0.

### Gotchas
- The Ticket parser (`runner/domain/ticket.py`) strictly expects `Status: pending` (or `completed` / `skipped`). Do not introduce `Status: todo` or unparsed metadata fields.
