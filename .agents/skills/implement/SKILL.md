---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described in the active ticket or spec:

1. **Seams & TDD**: Agree seams before writing code. Drive implementation test-first via red-green cycles.
2. **Verification & Speed**: Run typechecking and tests regularly. During development iterations, run targeted single test files matching your edits. Avoid piping to Unix-only commands (`tail`, `grep`) on Windows. Run broader test suites only once targeted tests pass before signalling readiness.
3. **Review**: Run `/code-review` to verify standards and spec alignment. If flagged by ticket requirements or frontmatter (`Security: required`), also run `/security-review` before committing or signaling ready.
4. **Ticket Transition & Gotchas**: When executing a ticket under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md`:
   - Append newly discovered runtime lessons and ticket-specified gotchas to `docs/tickets/gotchas.md` as a chronological log with problem and solution sub-bullets:
     - Log non-obvious platform quirks, hidden runtime pitfalls, unwritten repo conventions, and non-trivial TDD diagnosis findings.
     - State positive target behaviors and actionable solutions; prune trivial syntax errors and CLI reference lookups.
   - Update ticket frontmatter: set `Status: completed` and record `Completed: <ISO-8601-UTC-timestamp>`.
   - Relocate the ticket file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`.
5. **Commit** *(interactive mode only — skip in Ticket Runner autonomous execution)*: Stage code changes, the relocated ticket file, and `docs/tickets/gotchas.md` together in the feature commit. Automatically execute `git commit` to the current branch without pausing to ask confirmation once tests and reviews pass, following the repository convention (`<type>(<scope>): <Title>` with bulleted imperative changes and no ticket numbers).
6. **Readiness & Live QA**: Human verification happens post-green via a human-invoked `/live-qa` session. The implementer drafts no scenarios and self-reports no manual verification. Readiness is strictly: all targeted tests pass, broad test suite passes, `/code-review` passes (plus `/security-review` if required), and the ticket is relocated with frontmatter updated.
   - **Interactive mode**: report completed tests, reviews, and git commit; remind the operator that live verification can be driven via `/live-qa`.
   - **Ticket Runner autonomous mode**: emit `.agent/signals/<ticket_id>_ready.json` with `{"ticket_id": "<ticket_id>"}`. The Gatekeeper performs independent test/build checks and human approval without relying on worker self-reports.
