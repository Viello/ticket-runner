---
name: smoke-fail
description: "Create a regression ticket from a failed smoke scenario found during batch review."
disable-model-invocation: true
---

# /smoke-fail

> **Stub** — full automation is deferred. This skill guides an interactive session today.
> When automation is ready, it will read `.agent/smoke_log_<spec-slug>.md` directly and
> file a pre-populated regression ticket without human copy-paste.

## When to use

After reviewing `.agent/smoke_log_<spec-slug>.md` and finding a scenario that failed,
run `/smoke-fail` to capture the failure and create a regression ticket.

## Steps

1. **Identify the failure**. Ask the human:
   - Which ticket ID contained the failing scenario? (e.g. `T042`)
   - What is the exact scenario name from the smoke log?
   - What did you observe? (copy the actual output or behaviour)
   - What did the scenario expect? (copy from the log)

2. **Diagnose first** (if not already done). Open the scenario steps from the smoke log
   and walk through them together. If the failure looks like a code defect, invoke
   `/diagnosing-bugs` before creating a ticket — a tight, red-capable feedback loop first.

3. **Draft the regression ticket**. Create a new ticket file under the same spec slug
   as the originating ticket:

   ```
   docs/tickets/<spec-slug>/T<NNN>-<slug>.md
   ```

   Pre-populate with:
   - `Title`: `Smoke regression: <scenario name>`
   - `Status: todo`
   - A `### Context` section referencing the originating ticket
   - A `### Observed` section with what the human saw
   - A `### Expected` section from the smoke log entry
   - A `### Smoke Scenarios` section carrying the same scenario (so the fix is also smoke-tested)

4. **Confirm with the human** before saving. Read the draft back and ask if it captures the
   failure accurately.

## Future automation target

When implemented, `/smoke-fail` will:
- Parse `.agent/smoke_log_<spec-slug>.md` to locate the entry by ticket ID + scenario name.
- Extract Setup / Steps / Expected automatically.
- Assign the next available ticket number and write the file without human copy-paste.
- Emit a summary of the created ticket.
