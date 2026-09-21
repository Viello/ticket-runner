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
5. **Commit** *(interactive mode only — skip in Ticket Runner autonomous execution)*: Stage code changes, the relocated ticket file, and `docs/tickets/gotchas.md` together in the feature commit. Commit to the current branch following the repository convention (`<type>(<scope>): <Title>` with bulleted imperative changes and no ticket numbers). Append scenario names from `### Smoke Scenarios` that require human action as a trailing section in the commit body:
   ```
   Manual verification required:
   - <Scenario name 1>
   - <Scenario name 2>
   ```
   Omit the section if all scenarios are auto-covered.
6. **Smoke Scenarios Handoff**: Read the ticket's `### Smoke Scenarios` section and produce a coverage audit — for each scenario, determine whether the automated test suite fully exercises it (`[auto-covered]` or `[needs human]`). Then branch by execution mode:
   - **Interactive mode**: Print the full `[needs human]` checklist (Setup / Steps / Expected verbatim) to the terminal. If all are auto-covered, emit: `All Smoke Scenarios covered by automated tests — no manual steps required.`
   - **Ticket Runner autonomous mode**: Embed the structured checklist as `manual_verification` in `.agent/signals/<ticket_id>_ready.json` — a JSON array of `{"name", "setup", "steps", "expected"}` objects for each `[needs human]` scenario. The Gatekeeper reads this field, appends scenario names to the commit body, and re-surfaces the full checklist to the operator after committing. Emit an empty array if all scenarios are auto-covered.
