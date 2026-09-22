# T080 — Smoke failure recovery skill and regression ticket template
Status: completed
Completed: 2026-09-22T07:22:00Z
Spec: docs/specs/07-smoke-verification-protocol.md
Blocked by: T079

### Requirements
- Update `.agents/skills/smoke-fail/SKILL.md` to provide a universal, versatile interactive recovery guide when an operator encounters a failed smoke scenario (in Ticket Runner batch review, ad-hoc testing, or PR verification):
  - Smart intake: auto-detect and read `.agent/smoke_log_<spec-slug>.md` if present; fall back to interactive intake (scenario name, setup, steps, observed outcome, expected outcome) for ad-hoc or external testing.
  - Destination tracker auto-detection with interactive confirmation: inspect workspace (`docs/tickets/`, `AGENTS.md`, git/tracker tools) to select Ticket Runner queue, local scratch files, or GitHub/Linear issue trackers.
  - Ticket-first triage sequence: capture, draft, and persist the regression ticket before transitioning to diagnosis.
  - Multi-tracker templates mirroring `to-tickets` conventions:
    - Ticket Runner queue template adhering strictly to domain schema (`Status: pending`, `### Requirements`, `### Acceptance Criteria`, `### Smoke Scenarios`, `### Gotchas`).
    - Local scratch ticket template (`.scratch/<feature-slug>/issues/<NN>-<slug>.md`).
    - Issue tracker template with `bug`/`regression` labels.
  - Ensure the regression ticket automatically copies the failing smoke scenario into its own `### Smoke Scenarios` section so that the fix is verified against the human check.
  - Post-creation handover: offer immediate transition into `/diagnosing-bugs` to isolate the root cause with a tight feedback loop.
  - Authored according to `writing-for-agents` discipline (clear information hierarchy, positive prompting, checkable completion criteria, `disable-model-invocation: true`).
- Jump-start:
  - Files to touch: `.agents/skills/smoke-fail/SKILL.md`
  - Anchor patterns: `to-tickets` templates in `.agents/skills/to-tickets/SKILL.md`, `writing-for-agents` in `.agents/skills/writing-for-agents/SKILL.md`, ticket entity parser in `runner/domain/ticket.py`
  - Verification: Validate markdown structure and ensure template compatibility with `runner.domain.ticket.Ticket.parse`

### Acceptance Criteria
- `.agents/skills/smoke-fail/SKILL.md` documents smart intake against `.agent/smoke_log_<spec-slug>.md` with interactive fallback for ad-hoc testing.
- Destination tracker auto-detection and confirmation supports Ticket Runner queue, local scratch files, and issue trackers.
- Ticket Runner regression ticket template adheres strictly to `TicketMarkdownParser` format (`Status: pending`, standard sections).
- The skill instructs the agent to embed the failing scenario verbatim into the regression ticket's `### Smoke Scenarios`.
- Ticket-first sequencing is documented with post-creation handover to `/diagnosing-bugs`.
- Skill frontmatter uses `disable-model-invocation: true` and adheres to `writing-for-agents`.

### Smoke Scenarios
**Scenario: Verify regression ticket template validity with Ticket parser**
- Setup: None (reads `<ticket-runner-template>` directly from `.agents/skills/smoke-fail/SKILL.md`).
- Steps: Run `python -c "from runner.adapters.markdown.parser import TicketMarkdownParser; from pathlib import Path; import tempfile, re; content = Path('.agents/skills/smoke-fail/SKILL.md').read_text(encoding='utf-8'); match = re.search(r'<ticket-runner-template>\s*([\s\S]*?)\s*</ticket-runner-template>', content); sample = match.group(1).replace('<spec-slug>', '07-smoke-verification-protocol').replace('<slug>', 'sample').replace('<NNN>', '999').replace('<Scenario Title>', 'Test').replace('<originating_id>', 'T042').replace('<observed_output>', 'Crash').replace('<expected_output>', 'Redirect').replace('<files_to_touch>', 'runner/foo.py').replace('<seams_or_modules>', 'domain').replace('<verification_command>', 'pytest').replace('<setup_steps>', 'None').replace('<test_steps>', 'Run check').replace('<Triage insights or quirks noted during failure capture>', 'None'); tmp = Path(tempfile.gettempdir()) / 'T999-test.md'; tmp.write_text(sample, encoding='utf-8'); t = TicketMarkdownParser().parse(tmp); assert t.id == 'T999'; assert t.status.value == 'pending'; print('Template valid')"`
- Expected: Prints `Template valid` with exit code 0.

### Gotchas
- The Ticket parser (`runner/domain/ticket.py`) strictly expects `Status: pending` (or `completed` / `skipped`). Do not introduce `Status: todo` or unparsed metadata fields.
