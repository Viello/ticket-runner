---
name: implement-ticket-runner
description: "Autonomous worker skill for Ticket Runner target projects."
disable-model-invocation: true
---

Implement the work described in the active ticket:

1. **Seams & TDD**: Drive implementation test-first at the seams named in `## Jump-start`. Write failing tests, run that file, implement, and re-run.
2. **Verification & Speed**: Run targeted single test files matching your edits during development loops (e.g. `python -m pytest tests/unit/application/test_foo.py -x`). Do NOT repeatedly run full test suites during iteration. Subcommands run under Windows PowerShell; never pipe test output to Unix-only utilities (`tail`, `grep`, `head`). Run broader test suites only once targeted tests pass before signalling readiness. If tests hang or cascade, follow `.agents/skills/diagnosing-bugs/SKILL.md` § Stuck-Test-Suite Protocol.
3. **Review & Severity-Gated Escalation**: Run 3-axis `/code-review` (`Standards`, `Spec`, and `Security` referencing `.agents/skills/security-review/SKILL.md`). Summarize findings in `self_review_notes`.
   - Low and Medium findings never interrupt the human; remediate in-pass or record in `self_review_notes`.
   - Critical and High findings must be remediated in-pass before signalling readiness.
   - ONLY if remediation is blocked by an architectural decision or missing secret does the Worker emit `.agent/questions/<ticket_id>.json` and stop immediately.
4. **Checkbox Boundary**: Flip satisfied criteria from `- [ ]` to `- [x]` under `## Acceptance criteria` in the active ticket file. Modifying any other line or section of the active ticket file, editing `docs/tickets/gotchas.md`, or touching any other file under `docs/tickets/` is strictly forbidden and violates the Gatekeeper dispatch baseline. Never run `git add` or `git commit`.
5. **Readiness Signal**: When all targeted tests pass, broad tests pass, and self-reviews pass, emit `.agent/signals/<ticket_id>_ready.json` with `{"ticket_id": "<ticket_id>", "status": "ready_for_verification", "modified_files": [...], "self_review_notes": "...", "new_gotchas": [...], "timestamp": "..."}`.
6. **Live QA**: Human verification runs after green checks via `/live-qa` run by the human operator. The Worker drafts no scenarios and self-reports no manual verification.
