---
name: to-tickets
description: Break a plan, spec, or the current conversation into a set of tracer-bullet tickets, each declaring its blocking edges, published to the configured tracker (edges as text in one file per ticket locally, or native blocking links on a real tracker).
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice **under-fills** its window: sized to finish inside one fresh context session with room to spare. A slice that spills into a second session costs more in resume than it saved in size.
- Any prefactoring should be done first
- Any slice touching security boundaries (credentials, subprocesses, path sanitization, network, untrusted inputs) must be flagged with `Security: required` in the ticket header below `Status: pending` and declare explicit security verification in acceptance criteria

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

For each ticket, draft its **Smoke Scenarios**: the named, human-executable verification scripts the operator runs to confirm the feature works at the surface. Derive scenarios from Requirements and Acceptance Criteria, targeting observable UX, CLI behavior, interactive prompts, and visible side-effects. At ticket breakdown time, draft high-level scenario intent: establish the prerequisites, a plain-English explanation of what is being tested and why, and initial verification steps. (The implementer will later refine these into concrete, copy-pasteable commands once code exists.)

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work
- **Smoke Scenarios** (draft): the named scenarios the operator will run to confirm it works

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?
- Does the Smoke Scenarios list cover every edge case you care about? Add or adjust any scenario before approving.

Iterate until the user approves both the breakdown and the scenario coverage.

### 5. Publish the tickets to the configured tracker

- **Ticket Runner Directory Queue (`docs/tickets/<spec-slug>/`)** → when targeting the Ticket Runner:
  - Dynamically inspect `docs/tickets/` across all spec subdirectories (both active and `completed/` folders) to find the highest existing `T<NNN>` identifier. If none exist, start at `T001`.
  - Ensure the spec directory `docs/tickets/<spec-slug>/` exists, along with its sibling archive directory `docs/tickets/<spec-slug>/completed/`.
  - Ensure `docs/tickets/gotchas.md` exists to store cross-ticket lessons learned.
  - Write each ticket as an individual file: `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` using the `<ticket-runner-template>` below, numbered in dependency order so file sorting reflects the execution sequence.
- **Local files** → write one file per ticket under `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` in dependency order (blockers first). Each file's "Blocked by" lists the numbers/titles it depends on. Use the per-ticket file template below: one ticket per file, never a single combined file.
- **A real issue tracker (GitHub, Linear, …)** → publish one issue per ticket in dependency order (blockers first) so each ticket's blocking edges can reference real identifiers. Use the platform's native blocking / sub-issue relationship where it has one; otherwise set each ticket's "Blocked by" to the blocking issues. Apply the `ready-for-agent` triage label unless instructed otherwise; the tickets are agent-grabbable by construction.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue.

<ticket-runner-template>

# T<NNN> — <Ticket title>
Status: pending
Spec: docs/specs/<spec-slug>.md
Blocked by: <comma-separated blocker ticket IDs, or "None">
Security: required # include only if touching credentials, subprocesses, path sanitization, network, or untrusted inputs; omit otherwise
Reasoning: medium  # optional: low | medium | high | max (provider-specific; omit to use config default)

### Requirements
- <What to build: the end-to-end behaviour this ticket makes work, from the user's perspective>
- <Jump-start: files to touch, seams to work at, anchor patterns, and verification commands>

### Acceptance Criteria
- <Criterion 1>
- <Criterion 2>
- <Explicit security verification criterion: required whenever Security: required is set (e.g. input sanitization, safe subprocess invocation, command escaping)>

### Smoke Scenarios
**Scenario: <name>**
- Setup: <config values, env vars, or synthetic conditions the operator must put in place, or "None (runs from repo root)">
- Why: <1-2 sentences in simple plain English: what this feature does and why we are checking it, explained so anyone can understand>
- Steps: <numbered human actions — initial high-level actions/checks to verify the feature; refined with exact commands during implementation>
- Expected: <the exact output, file content, or UX state that confirms it worked, plus failure signs>

<!-- Every ticket must define at least one human-verifiable smoke scenario. Automated test coverage is additive metadata and never replaces human eyes. -->

### Gotchas
- <Ticket-specific quirks, edge cases, or pitfalls discovered during breakdown>

</ticket-runner-template>

<local-ticket-template>

# <NN>: <Ticket title>

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

**Jump-start:** the orientation that removes exploration — name every file the implementer will open
- Files/areas to touch (concrete paths)
- Seams to work at
- Existing-code anchors to model against (functions/types/patterns)
- The command or demo that verifies the slice
- The list is where orientation starts, not where exploration ends — if the code leads somewhere it didn't name, follow it

**Blocked by:** the numbers/titles of the tickets that gate this one, or "None (can start immediately)".

**Status:** ready-for-agent

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2

</local-ticket-template>

<issue-template>

## Parent

A reference to the parent issue on the tracker (if the source was an existing issue, otherwise omit this section).

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective, not layer-by-layer implementation.

## Jump-start

The orientation that removes exploration — name every file the implementer will open:

- Files/areas to touch (concrete paths)
- Seams to work at
- Existing-code anchors to model against (functions/types/patterns)
- The command or demo that verifies the slice
- The list is where orientation starts, not where exploration ends — if the code leads somewhere it didn't name, follow it

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Blocked by

- A reference to each blocking ticket, or "None (can start immediately)".

</issue-template>

Concrete file paths live only in **Jump-start**: a ticket lasts one session — too short to go stale — and naming files there skips the implementer's most expensive step. Everywhere else in either form, avoid specific file paths or code snippets: they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.
