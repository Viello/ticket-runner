---
name: implement
description: "Implement a piece of work based on a spec or set of tickets in a Human+AI interactive pairing session."
disable-model-invocation: true
---

# Implement

Interactive Human + AI pair programming execution discipline.

Use this skill when pairing directly with the human operator to implement work from a spec or ticket queue (`docs/tickets/<spec-slug>/`).

> **Note**: For autonomous unattended execution inside Ticket Runner (`ticket_runner.py`), the Runner uses `implement-ticket-runner`. This skill (`implement`) is strictly for interactive human sessions and contains zero autonomous signal noise.

## Execution Discipline

1. **Seams & TDD**: Agree seams with the human partner before writing code. Drive implementation test-first via red-green-refactor cycles.
2. **Verification & Speed**: Run typechecking and tests regularly. During development iterations, run targeted single test files matching your edits. Avoid piping to Unix-only commands (`tail`, `grep`) on Windows. Run broader test suites only once targeted tests pass before signalling completion.
3. **Review**: Run `/code-review` along three axes (`Standards`, `Spec`, and `Security` referencing `.agents/skills/security-review/SKILL.md`) before committing.
   - Low and Medium security findings should be remediated or noted in the review summary.
   - Critical and High findings must be remediated immediately. If blocked by missing secrets or human architectural choice, mark the ticket `**Status:** ready-for-human` and ask the operator.
4. **Ticket Transition & Dialect Closing**: Support both `to-tickets` and `to-ticket-runner` ticket formats:
   - **`to-tickets` format (Specimen B)**:
     - Flip satisfied criteria `- [ ]` → `- [x]`.
     - Update header: set `**Status:** done (reviewed; <summary>)` (or `**Status:** ready-for-human` if blocked).
     - Append verification footer: `**Verified:** <YYYY-MM-DD> — <summary>`.
     - Append newly discovered runtime lessons to `docs/tickets/gotchas.md`.
     - Relocate the ticket file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`.
   - **`to-ticket-runner` format (Specimen A)**:
     - When executing a Ticket Runner ticket interactively without `ticket_runner.py`:
     - Flip satisfied criteria `- [ ]` → `- [x]` under `## Acceptance criteria`.
     - Update the bold-label metadata header in-place with strict `TicketMarkdownParser`-compatible fields:
       - Set `**Status:** completed`
       - Record `**Completed:** <ISO-8601-UTC-timestamp>`
       - Set `**Status note:** reviewed; <summary>`
     - Append newly discovered runtime lessons to `docs/tickets/gotchas.md`.
     - Relocate the ticket file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`.
5. **Commit**: Stage code changes, the relocated ticket file, and `docs/tickets/gotchas.md` together in the feature commit. Automatically execute `git commit` to the current branch once tests and reviews pass, following the repository convention (`<type>(<scope>): <Title>` with bulleted imperative changes and no ticket numbers).
6. **Readiness & Live QA**: Remind the operator that human verification can be driven post-green via `/live-qa`.
