---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described in the active ticket or spec:

1. **Seams & TDD**: Agree seams before writing code. Drive implementation test-first via red-green cycles.
2. **Verification**: Run typechecking and tests regularly; ensure the full test suite passes.
3. **Review**: Run `/code-review` to verify standards and spec alignment before committing.
4. **Ticket Transition**: When executing a ticket under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md`:
   - Update frontmatter: set `Status: completed` and record `Completed: <ISO-8601-UTC-timestamp>`.
   - Relocate the ticket file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`.
5. **Commit**: Stage code changes together with the relocated ticket file. Commit to the current branch following the repository convention (`<type>(<scope>): <Title>` with bulleted imperative changes and no ticket numbers).
