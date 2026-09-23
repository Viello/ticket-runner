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
   - **Refine Smoke Scenarios to ELI5 standard**: Before marking completed, refine the ticket's `### Smoke Scenarios` section into concrete, spoon-fed instructions following the 4-part anatomy (Setup, Why, Steps, Expected). Replace abstract draft steps with tested, copy-pasteable commands in the project's native tooling.
   - Update ticket frontmatter: set `Status: completed` and record `Completed: <ISO-8601-UTC-timestamp>`.
   - Relocate the ticket file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`.
5. **Commit** *(interactive mode only — skip in Ticket Runner autonomous execution)*: Stage code changes, the relocated ticket file, and `docs/tickets/gotchas.md` together in the feature commit. Automatically execute `git commit` to the current branch without pausing to ask confirmation once tests, reviews, and local smoke checks pass, following the repository convention (`<type>(<scope>): <Title>` with bulleted imperative changes and no ticket numbers). Append **all** scenario names from `### Smoke Scenarios` as a trailing section in the commit body, tagging those also exercised by automated tests:
   ```
   Manual verification required:
   - <Scenario name 1>
   - <Scenario name 2> [also auto-covered]
   ```
6. **Smoke Scenarios Handoff**:
   - **Completeness gate**: if the ticket has no `### Smoke Scenarios` section, flag it as incomplete and do not emit a ready signal. Every ticket must define at least one human-verifiable scenario.
   - **ELI5 Refinement Standard**: Every scenario must be dead-simple and executable with zero guesswork:
     - **Setup**: Exact prerequisites or "None (runs from repo root)".
     - **Why**: 1-2 sentences in simple plain English explaining what this feature does and why we are checking it, as if explaining to a beginner.
     - **Steps**: Numbered, conversational, spoon-fed instructions including exact copy-pasteable terminal commands, CLI invocations, or self-contained runner snippets in the project's native tooling (e.g. `python -c @"..."@`, `npm run ...`, `node -e "..."`). Verify locally that the command runs cleanly before documenting.
     - **Expected**: Exact observable output / success markers to look for, and clear signs of failure.
   - **Coverage audit**: read the test suite and reason — using agent judgment — about which scenarios the automated suite also exercises end-to-end. Tag those `[also auto-covered]`. This is informative metadata only; tagged scenarios remain in the checklist.
   - **All scenarios are `[needs human]`**: the `[also auto-covered]` tag is additive, never a gate. Every scenario appears in the human checklist verbatim.
   - **Interactive mode**: print the full checklist (Setup / Why / Steps / Expected verbatim) for every scenario, appending `[also auto-covered]` where applicable. Emit nothing if the section is absent (completeness gate already blocked this path).
   - **Ticket Runner autonomous mode**: embed every scenario in `manual_verification` in `.agent/signals/<ticket_id>_ready.json` as a JSON array of `{"name", "setup", "steps", "expected", "auto_covered": true|false, "update_notes": "", "why": ""}` objects. The Gatekeeper reads this array, appends all entries to `.agent/smoke_log_<spec-slug>.md`, includes `[also auto-covered]` tags in the Discord summary, and re-surfaces the full checklist to the operator after committing.
7. **Smoke Log Note** *(autonomous mode only)*: if any scenario in this ticket supersedes or updates a prior ticket's scenario (same feature area, revised behaviour), set `"update_notes": "Updates: T0NN — <prior scenario name>"` on that entry in the ready signal. The Gatekeeper renders it as `> Updates: ...` beneath the scenario block in the smoke log. Leave `update_notes` empty if no prior entry is affected.

