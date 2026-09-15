---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described in the active ticket or spec:

1. **Seams & TDD**: Agree seams before writing code. Drive implementation test-first via red-green cycles.
2. **Verification**: Run typechecking and tests regularly; ensure the full test suite passes.
3. **Review**: Run `/code-review` to verify standards and spec alignment before committing.
4. **Ticket Transition & Gotchas**: When executing a ticket under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md`:
   - Append newly discovered runtime lessons and ticket-specified gotchas to `docs/tickets/gotchas.md` as a chronological log with problem and solution sub-bullets:
     - Log non-obvious platform quirks, hidden runtime pitfalls, unwritten repo conventions, and non-trivial TDD diagnosis findings.
     - State positive target behaviors and actionable solutions; prune trivial syntax errors and CLI reference lookups.
   - Update ticket frontmatter: set `Status: completed` and record `Completed: <ISO-8601-UTC-timestamp>`.
   - Relocate the ticket file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`.
5. **Commit**: Stage code changes, the relocated ticket file, and `docs/tickets/gotchas.md` together in the feature commit. Commit to the current branch following the repository convention (`<type>(<scope>): <Title>` with bulleted imperative changes and no ticket numbers).
