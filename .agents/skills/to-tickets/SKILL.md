---
name: to-tickets
description: "Break a plan, spec, or conversation into compact Human+AI interactive tickets (Specimen B) with status flow, inline orientation jump-starts, and acceptance checkboxes."
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices for Human + AI interactive pairing (such as in `Healthyasat` or developing `D:\Projects`), each declaring its blocking edges, inline jump-start, and acceptance checkboxes.

> **Note**: For autonomous execution by Ticket Runner (`ticket_runner.py`), use `/to-ticket-runner` instead, which authors canonical 5-section tickets.

The issue tracker and triage label vocabulary should have been provided to you. If not, tell the user to run `/setup-matt-pocock-skills`.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier: "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice **under-fills** its window: sized to finish inside one fresh context session with room to spare. A slice that spills into a second session costs more in resume than it saved in size.
- Any prefactoring should be done first
- Any slice touching security boundaries (credentials, subprocesses, path sanitization, network, untrusted inputs) must be flagged with `**Security:** required` in the ticket header and declare explicit security verification in acceptance criteria

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

Human verification happens post-green via `/live-qa`.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name (`T<NNN>: <Title>`)
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work
- **Jump-start summary**: files to touch, seams, and verification command

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?

Iterate until the user approves the breakdown.

### 5. Publish the tickets to the configured tracker

- **Local file queue (`docs/tickets/<spec-slug>/`)** → when using file-based tickets in a repository:
  - Dynamically inspect `docs/tickets/` across all spec subdirectories (both active and `completed/` folders) to find the highest existing `T<NNN>` identifier. If none exist, start at `T001`.
  - Ensure the spec directory `docs/tickets/<spec-slug>/` exists, along with its sibling archive directory `docs/tickets/<spec-slug>/completed/`.
  - Ensure `docs/tickets/gotchas.md` exists to store cross-ticket lessons learned.
  - Write each ticket as an individual file: `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` using the `<to-tickets-template>` below, numbered in dependency order.
- **A real issue tracker (GitHub, Linear, …)** → publish one issue per ticket in dependency order (blockers first) so each ticket's blocking edges can reference real identifiers. Use the platform's native blocking / sub-issue relationship where it has one; otherwise set each ticket's "Blocked by" to the blocking issues. Apply the `ready-for-agent` triage label unless instructed otherwise; the tickets are agent-grabbable by construction.
- **Local scratch** → fallback: write one file per ticket under `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` in dependency order.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue.

<to-tickets-template>

# T<NNN>: <Ticket title>

**Status:** ready-for-agent
**Labels:** ready-for-agent
Reasoning: medium  # optional: low | medium | high | max (provider-specific; omit to use config default)
**Security:** required (optional: include when slice touches trust boundaries / auth / RLS / subprocesses / secrets)
**Parent:** docs/specs/<spec-slug>.md

**What to build:** <the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.>

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:** <concrete paths>
- **Seams:** <seams to work at>
- **Existing-code anchors:** <functions/types/patterns to model against>
- **Verify:** <the command or demo that verifies the slice>

**Blocked by:** <the numbers/titles of the tickets that gate this one, or "None (can start immediately)">

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2

</to-tickets-template>

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
