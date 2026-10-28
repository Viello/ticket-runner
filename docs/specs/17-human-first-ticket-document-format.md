---
spec_id: 17-human-first-ticket-document-format
triage: ready-for-agent
status: settled
date: 2026-10-28
author: Gab
target_project: D:\Projects (Runner) & live-test Target Projects (D:\Repos\agent-skills, D:\Repos\agent-runner-driver, D:\Sandbox\ticket-runner-live-target, D:\Repos\empty-starter)
related_adrs:
  - ADR 0002 (Independent Gatekeeper Verification)
  - ADR 0004 (Explicit Signal Files)
  - ADR 0008 (Configurable Worker Execution Skill) — amended by this spec
  - ADR 0010 (Directory-Based Ticket Queue with Sentinel Lock)
  - ADR 0012 (Single-Commit Ticket Lifecycle and Ephemeral Queue Clean Slate) — amended by this spec
  - ADR 0013 (Ticket-Driven Security Review)
  - ADR 0017 (Invalid Signal Consumes Verification Attempt)
  - ADR 0023 (Wayfinder Ticket Type Label Convention) — superseded for implementation queues by this spec
---

# Spec 17: Human-First Ticket Document Formats, Dual-Track Authoring & Execution Skills (`to-tickets` vs `to-ticket-runner`), and Human-First Gatekeeper Controls

## Problem Statement

A Ticket is the unit of work and the only durable statement of what must be built. Today the Ticket document and the skills that author and execute it (`to-tickets` and `implement`) suffer from five concrete structural problems:

1. **Orientation is not removed, only deferred.** The current Ticket Runner template compresses the entire orientation payload — which files to touch, which seam to work at, which existing anchors to model against, and which verification command proves the slice — into a single trailing bullet of `### Requirements`. A Worker or a human pairing with an AI therefore opens a Ticket, learns nothing actionable, and pays the most expensive step of implementation (exploration) before it can begin.

2. **Acceptance criteria are indistinguishable from Gotchas.** Acceptance criteria in the Runner dialect are plain `-` bullets, structurally identical to the entries under `### Gotchas`. Nothing in the document records which criteria are satisfied. A Ticket that is nine-tenths complete and a Ticket that has not been started present the same way to every reader, and to the Runner itself.

3. **The metadata block reads as configuration rather than as a document header, and conflates Wayfinder planning with implementation.** Flat `Key: value` lines are legible to `METADATA_PATTERN` and illegible to a person scanning a Ticket. Meanwhile, ADR 0023 injected `**Type:** wayfinder:task (AFK)` onto the second line of implementation Tickets even though `wayfinder` is a separate fog-of-war decision-mapping workflow (`planning/<map-slug>/`) that Ticket Runner is never meant to execute.

4. **One overloaded skill pair (`to-tickets` and `implement`) tries to serve two distinct workflows and serves neither cleanly.**
   - In a **Human + AI interactive workflow** (such as `C:\Healthyasat\Healthyasat` or developing the Runner repository `D:\Projects` itself), a human and AI pair-program directly without `ticket_runner.py`. They want a compact, triage-driven brief (`**Status:** ready-for-agent` → `done` or `ready-for-human`, inline `**What to build:**` and `**Jump-start:**`, 3-axis `/code-review`, and direct git commits).
   - In an **Autonomous Ticket Runner workflow** (executing Target Project queues via `ticket_runner.py`), an autonomous Worker subprocess must never commit, relocate tickets, or edit `docs/tickets/gotchas.md`, because the Gatekeeper owns those boundaries. Cramming both modes into a single `implement/SKILL.md` with parenthetical disclaimers (`*(interactive mode only — skip in Ticket Runner autonomous execution)*`) repeatedly tempts autonomous Workers into violating Gatekeeper boundaries, while forcing Human+AI projects to maintain forked copies of `to-tickets`, `implement`, and `code-review`.

5. **Autonomous execution lacks a pre-dispatch Human-First (`HITL`) halt and severity-gated security escalation.** When a ticket in a Ticket Runner queue is marked `HITL` (or when a 3-axis security review hits an un-remediable `CRITICAL`/`HIGH` blocker that would become `ready-for-human` in an interactive session), the Runner must never charge ahead on its own. It needs to stop completely and wait for the human's decision via Discord or the Terminal before proceeding or cancelling.

## Solution

1. **Split Ticket authoring and execution into two explicit skill tracks in `Viello/agent-skills` (and `.agents/skills/`), both using the `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` (and `completed/`) directory layout:**
   - **Human + AI Interactive Track (`to-tickets` + `implement`)**:
     - `to-tickets` authors compact Human+AI tickets modeled on Healthyasat (`**Status:** ready-for-agent`, `**Labels:** ready-for-agent [, security]`, `**Security:** required`, `**Parent:** docs/specs/<spec-slug>.md`, inline `**What to build:**`, `**Jump-start:**`, `**Blocked by:**`, and `- [ ]` acceptance criteria checkboxes). Used when `ticket_runner.py` is not used, including `D:\Projects`'s own development queue.
     - `implement` is the pure Human+AI interactive execution skill (zero autonomous signal noise). Crucially, `implement` supports running **both** `to-tickets` files AND `to-ticket-runner` files interactively without `ticket_runner.py` — closing out `to-ticket-runner` files with strict `TicketMarkdownParser`-compatible headers (`**Status:** completed`, `**Completed:** <ISO-8601-UTC>`, optional `**Status note:**`) so a queue remains 100% compatible with `ticket_runner.py`.
   - **Autonomous + Human-Compatible Ticket Runner Track (`to-ticket-runner` + `implement-ticket-runner`)**:
     - `to-ticket-runner` authors tickets in the canonical 5-section Ticket Runner format with a bold-label header (`**Mode:** AFK | HITL`, `**Status:** pending`, `**Spec:**`, `**Blocked by:**`, `**Security:**`, `**Reasoning:**`) and five `##` sections (`## What to build`, `## Jump-start`, `## Acceptance criteria`, `## Smoke scenarios`, `## Gotchas`).
     - `implement-ticket-runner` becomes the Runner's default `worker.execution_skill` (`.agents/skills/implement-ticket-runner/SKILL.md`), containing strictly autonomous Worker instructions (TDD at seams, Stuck-Test-Suite Protocol, 3-axis review, ticking `- [ ]` → `- [x]`, and emitting `.agent/signals/<ticket_id>_ready.json` — never committing or relocating files).

2. **Decouple `wayfinder` from implementation queues and enforce a Pre-Dispatch `HITL` Gate in the Runner:**
   - Supersede ADR 0023 for `docs/tickets/` implementation queues: `wayfinder` stays a separate planning-map workflow (`planning/<map-slug>/`), while `to-ticket-runner` places `**Mode:** AFK` (or `**Mode:** HITL`) on line 2 (defaulting to `AFK` when omitted).
   - When `ticket_runner.py` encounters a ticket with `**Mode:** HITL` (or `**Status:** blocked`), the Gatekeeper halts **before** spawning any Worker subprocess, transitions to `WAITING_FOR_USER`, and prompts the human via Discord/Terminal to: (a) provide human decision/instructions to inject into the Worker prompt and proceed, (b) skip the ticket, or (c) cancel/abort the run immediately. Human decision always comes first.

3. **Let the Worker acknowledge checkbox criteria, and let the Gatekeeper police the boundary:**
   - Acceptance criteria are `- [ ]` / `- [x]` checkboxes. The marker is stripped from `Ticket.acceptance_criteria` and recorded in `Ticket.checked_criteria`.
   - During autonomous execution, the Worker may flip `- [ ]` to `- [x]` under `## Acceptance criteria` and change nothing else in the ticket file. The Gatekeeper takes a dispatch baseline before Worker execution and refuses the ready Signal (consuming a Verification Attempt) if any other line in the ticket changed. Unticked criteria are surfaced on the Evidence Card.

4. **Unify 3-axis `/code-review` + `/security-review` with severity-gated `ready-for-human` escalation:**
   - Upgrade `Viello/agent-skills/code-review` to Healthyasat's 3-axis parallel review (`Standards`, `Spec`, and `Security` referencing `.agents/skills/security-review/SKILL.md`).
   - Low and Medium security findings never block or interrupt the human. Critical and High findings require immediate in-session remediation; **only if remediation is blocked** (requiring human architectural decision or missing secrets — i.e. `ready-for-human`) does `implement` set `**Status:** ready-for-human` in interactive mode, and `implement-ticket-runner` emit `.agent/questions/<ticket_id>.json` in autonomous mode so the Gatekeeper halts and waits for the human on Discord/Terminal.

## User Stories

1. As a developer working with an AI assistant without Ticket Runner (e.g. in `D:\Projects` or `Healthyasat`), I want `/to-tickets` to generate compact, human-first tickets under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` with `**Status:** ready-for-agent`, inline `**What to build:**` and `**Jump-start:**`, and `- [ ]` checkboxes, so that interactive sessions stay lightweight and fast.
2. As an operator orchestrating autonomous runs with Ticket Runner, I want `/to-ticket-runner` to generate structured 5-section tickets under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` that `TicketMarkdownParser` parses natively, so that the Gatekeeper and Worker have unambiguous machine and human contracts.
3. As a developer who occasionally wants to run a `/to-ticket-runner` ticket manually with an AI assistant (without invoking `ticket_runner.py`), I want `/implement` to recognise and close out `to-ticket-runner` tickets using strict `TicketMarkdownParser`-compatible headers (`**Status:** completed`, `**Completed:** <ISO-8601-UTC>`, optional `**Status note:**`) and relocate them to `completed/`, so that `ticket_runner.py` can seamlessly resume the rest of the queue later.
4. As a maintainer, I want autonomous Workers driven by `ticket_runner.py` to use a dedicated `.agents/skills/implement-ticket-runner/SKILL.md` skill that never mentions interactive git commits or manual ticket relocation, so that Workers are never tempted by prompt instructions to violate Gatekeeper ownership of `docs/tickets/` and git history.
5. As an operator, I want `to-ticket-runner` tickets to carry `**Mode:** AFK` or `**Mode:** HITL` instead of `**Type:** wayfinder:task`, so that `wayfinder` remains a separate planning workflow and implementation tickets clearly declare whether they can start autonomously (`AFK`) or require human direction first (`HITL`).
6. As an operator, when `ticket_runner.py` reaches a ticket with `**Mode:** HITL`, I want the Gatekeeper to stop completely before launching the Worker and prompt me on Discord/Terminal to provide instructions and proceed, skip the ticket, or cancel the run, so that Ticket Runner never charges ahead on human-first work without my decision.
7. As a Worker agent opening a Ticket, I want the files to touch, the seam to work at, the existing anchors to model against, and the verification command named in a dedicated `Jump-start` section, so that I can begin implementation without an exploratory pass.
8. As a Worker agent opening a Ticket, I want the end-to-end behaviour (`What to build`) stated separately from the mechanical orientation (`Jump-start`), so that I do not confuse "what the user gets" with "where the code lives".
9. As a human reviewer, I want acceptance criteria rendered as `- [ ]` / `- [x]` checkboxes in both `to-tickets` and `to-ticket-runner`, so that I can see at a glance which criteria are satisfied and which are outstanding.
10. As a human reviewer, I want the autonomous Worker's checkbox tick (`- [x]`) treated as the Worker's claim and the Gatekeeper's verification treated as the evidence, so that a self-reported tick never substitutes for independent verification (ADR 0002).
11. As an operator, I want every acceptance criterion the Worker left unticked listed on the Evidence Card, so that an approved-but-incomplete Ticket is visible to me before I approve it.
12. As an operator, I want a Worker caught editing a `to-ticket-runner` file beyond flipping `- [ ]` to `- [x]` in `## Acceptance criteria` to have its ready Signal refused and consume a Verification Attempt, so that Ticket content stays trustworthy and a rogue Worker trips the Circuit Breaker (ADR 0012, ADR 0017).
13. As a maintainer, I want `/code-review` in `Viello/agent-skills` to run a 3-axis review (`Standards`, `Spec`, and `Security` referencing `.agents/skills/security-review/SKILL.md`), so that security boundaries are audited consistently in both interactive and autonomous workflows.
14. As an operator, I want Low and Medium security findings to be handled without interrupting me, while un-remediable Critical or High security findings (which become `**Status:** ready-for-human` in interactive mode) trigger a `.agent/questions/<ticket_id>.json` signal in autonomous mode so the Gatekeeper halts and waits for my decision.
15. As a maintainer, I want `to-ticket-runner`'s `**Status:**` field to remain a strict `TicketStatus` enum while `**Status note:**` carries arbitrary human prose (such as `"reviewed; Security PASSED"` or skip reasons), so that the Runner's state machine stays strict while keeping human commentary in the header.
16. As a maintainer, I want `**Security:**` read on its first whitespace-delimited token case-insensitively, so that inline rationale (`**Security:** required (trust boundaries: subprocess escaping)`) resolves cleanly.
17. As an operator, if I accidentally run `ticket-runner doctor` or `ticket_runner.py` against a `docs/tickets/` queue authored with the interactive-only `to-tickets` skill, I want a clear diagnostic explaining that the tickets use the interactive `to-tickets` (Human+AI) dialect and pointing me to `/implement` or `/to-ticket-runner`.
18. As a maintainer, I want `Viello/agent-skills` updated with the two new skills (`to-ticket-runner` and `implement-ticket-runner`, each with `agents/openai.yaml`) and aligned across `to-tickets`, `implement`, `code-review`, `ask-matt`, `smoke-fail`, and `README.md` (50 canonical skills total).
19. As a maintainer, I want `D:\Projects`'s own active Tickets migrated to the `to-tickets` (Human+AI) format and the live-test Target Projects' Tickets migrated to the `to-ticket-runner` format, while leaving archived Tickets in `D:\Projects` untouched.

## Implementation Decisions

### 1. Dual-Track Skill Architecture (`Viello/agent-skills` & `.agents/skills/`)

The catalog and local skill vendor split ticket authoring and execution into two explicit tracks that share the `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` (with sibling `completed/` and `docs/tickets/gotchas.md`) filesystem layout:

| Concern | Human + AI Interactive Workflow | Autonomous Ticket Runner Workflow (+ Human-Compatible) |
| :--- | :--- | :--- |
| **Authoring Skill** | `to-tickets` | `to-ticket-runner` |
| **Primary Execution Skill** | `implement` | `implement-ticket-runner` (default `worker.execution_skill`); also runnable interactively by Human+AI via `implement` |
| **Queue Path** | `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` (or external tracker: GitHub/Linear/GitLab) | `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` |
| **Archive Path** | `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md` | `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md` |
| **Where Used** | Projects worked interactively by Human + AI without `ticket_runner.py` (including `D:\Projects` itself and `Healthyasat`) | Target Projects executed by `ticket_runner.py` (`D:\Repos\agent-skills`, `D:\Repos\agent-runner-driver`, `D:\Sandbox\ticket-runner-live-target`, `D:\Repos\empty-starter`) |

### 2. Specimen A — `to-ticket-runner` Canonical Document Shape (Autonomous + Human-Compatible)

Defined in `to-ticket-runner/SKILL.md` and parsed natively by `TicketMarkdownParser`:

```markdown
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
```

- **Bold-label metadata header**: Begins on the line immediately after `# T<NNN> — <Ticket title>` with no blank line in between.
  - `**Mode:**`: `AFK` or `HITL` (case-insensitive; defaults to `AFK` when omitted). Replaces `**Type:** wayfinder:...` in implementation queues, superseding ADR 0023 for `docs/tickets/`.
  - `**Status:**`: Strict `TicketStatus` enum (`pending`, `in_progress`, `completed`, `failed`, `blocked`, `skipped`).
  - `**Status note:**`: Optional freeform human prose beside the strict status value (e.g., `reviewed; Security PASSED` when closed interactively via `/implement`, or the failure reason when skipped by the Circuit Breaker).
  - `**Spec:**`: Optional path to the originating Spec; falls back to `docs/specs/<spec-slug>.md` derived from the Queue directory.
  - `**Blocked by:**`: Comma-separated `T<NNN>` identifiers or `None`.
  - `**Security:**`: Read on its first whitespace-delimited token case-insensitively (`required` / `true` / `yes`), tolerating inline rationale (e.g., `**Security:** required (trust boundaries: subprocess shell quoting)`).
  - `**Reasoning:**`: Optional per-ticket model effort (`low`, `medium`, `high`, `max`).
- **Five recognised top-level `##` sections**: `What to build`, `Jump-start`, `Acceptance criteria`, `Smoke scenarios`, and `Gotchas`. Any other section or heading level is inert (including legacy `### Smoke Scenarios`).
- **Domain model (`Ticket` entity)**:
  - Gains `mode: str = "AFK"` (`"AFK"` or `"HITL"`), `status_note: str | None = None`, `jump_start: tuple[str, ...] = ()`, and `checked_criteria: frozenset[str] = frozenset()`.
  - `acceptance_criteria` continues to hold criterion strings with `- [ ] ` / `- [x] ` markers stripped.
  - `requirements` holds the `What to build` entries (each bullet or contiguous prose paragraph).
  - `gotchas` holds the `Gotchas` entries.

### 3. Specimen B — `to-tickets` Compact Document Shape (Human + AI Interactive Only)

Defined in `to-tickets/SKILL.md` (modeled on `C:\Healthyasat\Healthyasat\.agents\skills\to-tickets\SKILL.md`, publishing local files to `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` with a `completed/` archive subfolder, or to an external tracker like GitHub/Linear):

```markdown
# T<NNN>: <Ticket title>

**Status:** ready-for-agent
**Labels:** ready-for-agent [, security]
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
```

- When completed interactively via `/implement`, the agent ticks `- [ ]` → `- [x]`, updates `**Status:** done (reviewed; ...)` (or `**Status:** ready-for-human` if blocked), appends a `**Verified:** <YYYY-MM-DD> — <summary>` line at the bottom, logs lessons to `docs/tickets/gotchas.md`, relocates the file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`, and commits.
- **Parser & Doctor Dialect Detection**: If `TicketMarkdownParser` (or `ticket-runner doctor`) encounters a `to-tickets` Human+AI file (e.g., `**Status:** ready-for-agent` or inline `**What to build:**` without `##` sections), it raises a descriptive `TicketParseError` explaining that the ticket uses the interactive `to-tickets` (Human+AI) format and should either be executed interactively with `/implement` or authored via `/to-ticket-runner` for autonomous execution.

### 4. Dual-Mode Execution: `implement` vs `implement-ticket-runner`

- **`implement` (`.agents/skills/implement/SKILL.md` — Human + AI Interactive Skill)**:
  - Used exclusively in interactive Human + AI sessions. Contains no autonomous signal or Gatekeeper boilerplate.
  - Supports **both** `to-tickets` files and `to-ticket-runner` files:
    1. On a **`to-tickets`** file: ticks `- [ ]` → `- [x]`, updates `**Status:** done (reviewed; ...)`, appends `**Verified:** <YYYY-MM-DD> — <summary>`, updates `docs/tickets/gotchas.md`, relocates to `completed/`, and commits.
    2. On a **`to-ticket-runner`** file (when a human runs a `to-ticket-runner` ticket manually without `ticket_runner.py`): ticks `- [ ]` → `- [x]` under `## Acceptance criteria`, updates the bold-label header in-place using strict `TicketMarkdownParser` fields (`**Status:** completed`, `**Completed:** <ISO-8601-UTC>`, and `**Status note:** reviewed; <summary>`), updates `docs/tickets/gotchas.md`, relocates to `completed/`, and commits. This guarantees `ticket_runner.py` can still parse `completed/` if started later on the same queue.
- **`implement-ticket-runner` (`.agents/skills/implement-ticket-runner/SKILL.md` — Autonomous Worker Skill)**:
  - Becomes the new default `worker.execution_skill` across Ticket Runner (`doctor.py`, `prompt_builder.py`, `ticket_processor.py`, `handoff_coordinator.py`, `scaffold_sandbox.py`, `config.yaml`, `config.example.yaml`, amending ADR 0008).
  - Contains strictly autonomous Worker obligations:
    1. Drive implementation test-first at the seams named in `## Jump-start`.
    2. Run targeted tests during iteration and the broad suite before signalling readiness, applying `/diagnosing-bugs` § Stuck-Test-Suite Protocol if tests hang or cascade.
    3. Run `/code-review` (3-axis: Standards, Spec, and Security when `**Security:** required` or security boundaries are touched, reading `.agents/skills/security-review/SKILL.md`).
    4. Flip satisfied criteria from `- [ ]` to `- [x]` under `## Acceptance criteria` in the active ticket file, and **modify no other line or section** of the ticket file (nor any other file under `docs/tickets/`). Never run `git commit`.
    5. Emit `.agent/signals/<ticket_id>_ready.json` with `new_gotchas`, `modified_files`, and `self_review_notes` (or emit `.agent/questions/<ticket_id>.json` if blocked by a `ready-for-human` decision or un-remediable Critical/High security finding).

### 5. Human-First Pre-Dispatch `HITL` Gate & Mid-Run Decision Escalation

- **Pre-Dispatch `HITL` Gate (`**Mode:** HITL`)**:
  - When `TicketProcessor` / `VerificationLoop` picks up a ticket whose `ticket.mode == "HITL"`, the Gatekeeper **does not spawn the Worker subprocess**.
  - Instead, it transitions state to `WAITING_FOR_USER` (`RunState.WAITING_FOR_USER`, updating the Discord Status Card and scheduling presence escalation if away) and prompts the human via `InterventionGateway` (Discord / Terminal) before any work begins:
    1. **Proceed with human guidance**: Human supplies instructions/decision text, which is prepended to the Worker's initial prompt, and execution proceeds.
    2. **Skip ticket**: Marks the ticket `**Status:** skipped` with `**Status note:** Skipped by operator at HITL pre-dispatch gate` and moves to the next ticket.
    3. **Cancel / Abort run**: Raises `UserAbortError` and stops `ticket_runner.py` immediately.
- **3-Axis Security Escalation (`ready-for-human` → Question Signal)**:
  - In `Viello/agent-skills/code-review/SKILL.md`, the 3-axis review runs `Standards`, `Spec`, and (when flagged by `**Security:** required` or diff heuristic) `Security` referencing `.agents/skills/security-review/SKILL.md`.
  - Low and Medium findings never require human intervention (remediated in-pass or noted in `self_review_notes`).
  - Critical and High findings trigger immediate code remediation and re-testing. **Only if remediation is blocked** (architectural constraint, missing secret, or human policy choice — the condition that sets `**Status:** ready-for-human` in interactive mode) does the autonomous Worker emit `.agent/questions/<ticket_id>.json`. The Gatekeeper then halts completely (`QUESTION_PENDING` → `WAITING_FOR_USER`) and waits for the human's decision on Discord/Terminal (answer to resume, or cancel/abort).

### 6. Gatekeeper Dispatch-Baseline Tick Boundary & In-Place Header Serializer

- **Dispatch baseline comparison**: Before the Worker runs on a `to-ticket-runner` ticket, the Gatekeeper snapshots the ticket file on disk. When a ready Signal arrives, the Gatekeeper compares the current ticket file against the baseline:
  - The **only** permitted change is flipping `- [ ] ` to `- [x] ` (or `- [X] `) on existing lines inside `## Acceptance criteria`.
  - Any other edit to the ticket (header, `## What to build`, `## Jump-start`, criterion text, `## Smoke scenarios`, `## Gotchas`, or adding/removing lines) is rejected, restores the baseline on disk, refuses the ready Signal, and consumes a Verification Attempt (ADR 0017, ADR 0002).
- **Evidence Card unticked criteria**: Any acceptance criterion left `- [ ]` by the Worker is surfaced on the `EvidenceCard` (`unticked_criteria: tuple[str, ...] = ()`) so the operator sees unacknowledged criteria before approving.
- **`TicketMarkdownSerializer` in-place header patching**: Locates the bold-label header region, updates/inserts `**Status:**`, `**Status note:**`, `**Completed:**`, etc. in canonical order (`Mode`, `Status`, `Status note`, `Completed`, `Spec`, `Blocked by`, `Security`, `Reasoning`), and leaves every byte after the header region untouched (preserving `- [x]` ticks, CRLF/LF line endings, and trailing newline state).

### 7. Catalog, Living Docs & Queue Synchronization

- **`Viello/agent-skills` (`D:\Repos\agent-skills`)**:
  - Add `to-ticket-runner/` (`SKILL.md` + `agents/openai.yaml`) and `implement-ticket-runner/` (`SKILL.md` + `agents/openai.yaml`).
  - Update `to-tickets/SKILL.md`, `implement/SKILL.md`, `code-review/SKILL.md`, `ask-matt/SKILL.md`, `smoke-fail/SKILL.md`, and `README.md` (50 canonical skills).
  - Vendor updated skills into `D:\Projects\.agents\skills/` and synchronize to live-test Target Projects (`D:\Repos\agent-runner-driver`, `D:\Sandbox\ticket-runner-live-target`, `D:\Repos\empty-starter`).
- **Queue Migrations**:
  - Migrate `D:\Projects`'s own active tickets (`docs/tickets/15-...`) to the `to-tickets` (Human+AI) format (and remove or archive the completed wayfinder map `T000`). Leave `D:\Projects` archived tickets untouched.
  - Migrate live-test Target Projects' queues (`D:\Repos\agent-skills`, `D:\Repos\agent-runner-driver`, `D:\Sandbox\ticket-runner-live-target`, `D:\Repos\empty-starter`) to the `to-ticket-runner` canonical format.
- **ADR & Glossary Updates**:
  - Amend ADR 0008 (default `worker.execution_skill` is `.agents/skills/implement-ticket-runner/SKILL.md`), ADR 0012 (canonical bold-label `**Status:** completed` and `**Completed:** <timestamp>`), and ADR 0023 (scope `wayfinder` type labels strictly to `wayfinder` planning maps, superseded by `**Mode:** AFK | HITL` in `to-ticket-runner` implementation queues).
  - Update `CONTEXT.md`, `AGENTS.md`, and `docs/tickets/gotchas.md` to reflect the dual-track skills and canonical ticket formats.

## Testing Decisions

- **Document I/O Seam (`TicketMarkdownParser` & `TicketMarkdownSerializer`)**:
  - Assert parsing of Specimen A (`to-ticket-runner` canonical format): `**Mode:** AFK | HITL` (and default `"AFK"` when omitted), strict `**Status:**` enum, freeform `**Status note:**`, optional `**Spec:**` with directory fallback, `**Security:**` first-token case-insensitive read with inline rationale, `**Reasoning:**`, the five `##` sections (`What to build`, `Jump-start`, `Acceptance criteria`, `Smoke scenarios`, `Gotchas`), stripped checkbox markers in `acceptance_criteria`, and populated `checked_criteria`.
  - Assert descriptive `TicketParseError` remediation message when a `to-tickets` (Human+AI dialect, e.g. `**Status:** ready-for-agent` or inline `**What to build:**`) file is passed to `TicketMarkdownParser`.
  - Assert `TicketMarkdownSerializer` patches bold-label headers in-place (`**Status:** completed`, `**Completed:**`, `**Status note:**` on skip) while preserving body bytes, `- [x]` checkboxes, and line endings untouched.
- **Gatekeeper Tick-Boundary & Pre-Dispatch `HITL` Gate Seam (`GatekeeperVerificationLoop` & `TicketProcessor`)**:
  - Assert that when `ticket.mode == "HITL"`, the Gatekeeper halts before calling `cycle_runner`, transitions to `WAITING_FOR_USER`, and prompts via `InterventionGateway`: proceeding with injected human prompt on guidance, marking skipped on skip, and raising `UserAbortError` on cancel/abort.
  - Assert that a Worker flipping `- [ ]` → `- [x]` in `## Acceptance criteria` passes the dispatch-baseline check, while any edit to the header, `## What to build`, `## Jump-start`, criterion text, or `## Gotchas` is refused, restores the baseline, and consumes a Verification Attempt.
  - Assert that unticked criteria are populated on `EvidenceCard.unticked_criteria`.
- **Prompt Construction & Default Execution Skill Seam (`PromptBuilder`, `Doctor`, `Scaffold`)**:
  - Assert default `execution_skill` resolves to `.agents/skills/implement-ticket-runner/SKILL.md`.
  - Assert Worker prompt renders the canonical section names (`What to build`, `Jump-start`, `Acceptance criteria`, `Gotchas`) and states the strict checkbox Tick permission boundary.
- **End-to-End Spec Seam**:
  - Full lifecycle test covering a `to-ticket-runner` ticket from queue parse → Pre-Dispatch `HITL`/`AFK` check → Worker checkbox tick → Gatekeeper baseline check & verification → Evidence Card unticked criteria check → in-place header finalization & archive relocation.

## Out of Scope

- **The Spec document format (`to-spec`)**: Unchanged.
- **Enforcing `Blocked by` edges at runtime in `ticket_runner.py`**: Remains documentary in the header for now.
- **Executing `wayfinder` maps inside `ticket_runner.py`**: `wayfinder` is explicitly a planning workflow (`planning/<map-slug>/`), not an autonomous implementation queue.
- **Retroactively rewriting archived tickets in `D:\Projects`**: Historical completed tickets in `D:\Projects` remain in their original format.

## Further Notes

- **Why two skill tracks solve the drift permanently**: Previously, every improvement to the Human+AI workflow in `Healthyasat` (compact headers, `ready-for-agent` / `ready-for-human` status flow, 3-axis `/code-review`, direct commits in `/implement`) clashed with Ticket Runner's strict autonomous Worker constraints. Splitting `to-tickets` + `implement` (Human+AI) from `to-ticket-runner` + `implement-ticket-runner` (Autonomous Runner + Human-compatible) lets both workflows excel without compromise, while keeping `to-ticket-runner` tickets 100% runnable by a human + AI via `/implement` whenever manual intervention is desired.
