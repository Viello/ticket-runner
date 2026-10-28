---
name: to-ticket-runner
description: "Break a plan, spec, or conversation into canonical 5-section tickets for autonomous Ticket Runner queues, with bold-label headers, orientation jump-starts, and checkbox acceptance criteria."
disable-model-invocation: true
---

# To Ticket Runner

Break a plan, spec, or conversation into a set of **Ticket Runner tickets**: tracer-bullet vertical slices authored in the canonical 5-section autonomous format (`**Mode:** AFK | HITL`), each declaring orientation jump-starts, acceptance criteria checkboxes, smoke scenarios, and blocking edges.

Targeted for autonomous execution by `ticket_runner.py` (which orchestrates OpenCode or Antigravity CLI workers under Gatekeeper verification). Can also be run interactively by a human + AI via `/implement`.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path under `docs/specs/<spec-slug>.md`, an issue number or URL) as an argument, fetch it and read its full body and comments.

### 2. Explore the codebase

Explore the codebase to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary (`CONTEXT.md`) and respect ADRs in `docs/adr/`.

Look for opportunities to prefactor the code to make the implementation easier: "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (domain, ports, application, adapters, tests): vertical, NOT a horizontal slice of one layer.
- A completed slice is demoable or verifiable on its own.
- Sized to under-fill the Worker context window: sized to finish inside one fresh session with room to spare.
- Any prefactoring should be done in an early ticket.
- Any slice touching security boundaries (credentials, subprocesses, path sanitization, network, untrusted inputs) must be flagged with `**Security:** required` in the bold-label metadata header and declare explicit security verification in acceptance criteria.
- Mode assignment:
  - `**Mode:** AFK` (default): Ticket can start immediately and run fully autonomously without human intervention.
  - `**Mode:** HITL`: Ticket requires a human decision, architectural choice, or explicit guidance before the Worker subprocess starts. When `ticket_runner.py` encounters `HITL`, the Gatekeeper halts at the Pre-Dispatch gate and prompts the operator via Discord/Terminal.

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers has `**Blocked by:** None`.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name (`T<NNN> — <Title>`)
- **Mode**: `AFK` or `HITL`
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work
- **Jump-start summary**: files to touch, seams, and verification command

Ask the user:
- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct?
- Are the `AFK` / `HITL` mode designations appropriate?
- Should any tickets be merged or split further?

Iterate until the user approves the breakdown.

### 5. Publish to Ticket Runner queue (`docs/tickets/<spec-slug>/`)

1. Inspect `docs/tickets/` across all spec subdirectories (both active and `completed/` folders) to find the highest existing `T<NNN>` identifier. If none exist, start at `T001`.
2. Ensure the spec directory `docs/tickets/<spec-slug>/` exists, along with its sibling archive directory `docs/tickets/<spec-slug>/completed/`.
3. Ensure `docs/tickets/gotchas.md` exists to store cross-ticket lessons learned.
4. Write each ticket as an individual file: `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` using the `<ticket-runner-template>` block below, numbered in dependency order so file sorting reflects the execution sequence.

<ticket-runner-template>
# T<NNN> — <Ticket title>
**Mode:** AFK
**Status:** pending
**Spec:** docs/specs/<spec-slug>.md
**Blocked by:** None
**Security:** required
**Reasoning:** medium

## What to build

<The end-to-end behaviour this Ticket makes work, from the user's perspective,
not a layer-by-layer implementation list.>

## Jump-start

- **Files/areas to touch:**
  - `path/to/file.py`
- **Seams:** <the seam to work at>
- **Existing-code anchors:** <functions, types, or patterns to model against>
- **Verification commands:** <the command or demo that proves the slice>
- The list is where orientation starts, not where exploration ends — if the code leads
  somewhere it did not name, follow it.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Smoke scenarios

- [ ] Scenario: <name>
  - Setup: <the state to arrange>
  - Why: <what the scenario proves>
  - Steps:
    1. <action>
  - Expected: <the observable outcome>

## Gotchas

- <ticket-specific quirk, pitfall, or constraint>
</ticket-runner-template>
