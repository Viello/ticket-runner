---
spec_id: 17-human-first-ticket-document-format
triage: ready-for-agent
status: settled
date: 2026-10-27
author: Gab
target_project: D:\Projects (Runner) & live-test Target Projects (D:\Repos\agent-skills, D:\Repos\agent-runner-driver, D:\Sandbox\ticket-runner-live-target, D:\Repos\empty-starter)
related_adrs:
  - ADR 0002 (Independent Gatekeeper Verification)
  - ADR 0004 (Explicit Signal Files)
  - ADR 0010 (Directory-Based Ticket Queue with Sentinel Lock)
  - ADR 0012 (Single-Commit Ticket Lifecycle and Ephemeral Queue Clean Slate) — amended by this spec
  - ADR 0017 (Invalid Signal Consumes Verification Attempt)
  - ADR 0023 (Wayfinder Ticket Type Label Convention)
---

# Spec 17: Human-First Ticket Document Format with Checkbox Acceptance Criteria

## Problem Statement

A Ticket is the Runner's unit of work and the only durable statement of what must be built. Today the Ticket document is a machine-first artifact: a flat `Key: value` metadata block followed by three undifferentiated `###` sections. That format was adequate when a Ticket was nothing more than a payload the Runner parsed and re-rendered, but it has since been asked to serve a second audience that it serves poorly, and the resulting compromise has produced four concrete costs.

1. **Orientation is not removed, only deferred.** The canonical `to-tickets` Worker Skill template compresses the entire orientation payload — which files to touch, which seam to work at, which existing anchors to model against, and which verification command proves the slice — into a single trailing bullet of `### Requirements`. A Worker or a human pairing with an AI therefore opens a Ticket, learns nothing actionable, and pays the most expensive step of implementation (exploration) before it can begin. The Runner's own Queue reproduces this: its live Tickets carry long prose paragraphs describing symptoms, but no structured statement of where to work or how to verify.

2. **Acceptance criteria are indistinguishable from Gotchas.** Acceptance criteria are plain `-` bullets, structurally identical to the entries under `### Gotchas`. Nothing in the document records which criteria are satisfied. A Ticket that is nine-tenths complete and a Ticket that has not been started present the same way to every reader, and to the Runner itself.

3. **The metadata block reads as configuration rather than as a document header.** Flat `Key: value` lines are legible to `METADATA_PATTERN` and illegible to a person scanning a Ticket. The Runner's own Wayfinder ticket type label (ADR 0023) already proves that the bold-label form is acceptable inside a Ticket — the convention binds every Ticket under the Runner's Queue to carry a `**Type:**` line — yet the Runner's own template omits that line and the Runner's parser cannot read it. The Runner's Ticket dialect is therefore the only dialect in the Skills Catalog that no other project consumes and no person reads comfortably.

4. **The Runner's Queue has forked away from the rest of the Skills Catalog.** The `to-tickets` Worker Skill exists in divergent copies across the Runner repository, the published Skills Catalog, and live-test Target Projects, and the copies disagree on the Ticket template itself. New Tickets are therefore authored in whatever dialect the local copy happens to prescribe, so a Ticket authored for one Target Project may be unreadable by the Runner that is meant to execute it. The Runner's Queue is additionally worked by a human pairing with an AI rather than by the Runner, which means the same documents must satisfy two consumers — a parser and a person — with one compromise shape that serves neither well.

The consequence is that the Runner's most durable artifact is its least legible one, and the format that the Gatekeeper trusts is a format its authors cannot comfortably write.

## Solution

Replace the Ticket document format with a single human-first canonical format that the Runner's parser reads natively, so that one document shape serves both a person reading a Ticket and the Gatekeeper verifying it:

1. **Adopt a canonical Ticket document shape** with a bold-label metadata header and five top-level sections: `## What to build`, `## Jump-start`, `## Acceptance criteria`, `## Smoke scenarios`, and `## Gotchas`. The shape is defined once, as a specimen, in the `to-tickets` Worker Skill, which becomes the single source of truth for Ticket authoring across the Runner and every Target Project.
2. **Separate outcome from orientation.** `## What to build` states the end-to-end behaviour the Ticket makes work, in the user's terms. `## Jump-start` carries the orientation as four named sub-fields — files/areas to touch, seams, existing-code anchors, and verification commands — so that orientation is opt-in, uniform, and impossible to bury inside prose.
3. **Make acceptance criteria checkboxes.** Acceptance criteria become `- [ ]` / `- [x]` entries. The marker is stripped from the criterion text and recorded separately, so the domain model can distinguish satisfied from unsatisfied criteria without polluting the rendered text.
4. **Let the Worker acknowledge criteria, and let the Gatekeeper police it.** The Worker may flip an acceptance criterion from `- [ ]` to `- [x]` while implementing the Ticket. The Gatekeeper holds a dispatch baseline of the Ticket document taken before the Worker began, and refuses the ready Signal if the Ticket document changed in any way other than a checkbox flip. The Tick is documentary: the Gatekeeper's own verification decides whether the Ticket is approved, and any criterion the Worker left unticked is surfaced on the Evidence Card for the operator.
5. **Preserve every architectural boundary the Runner already draws.** The Queue layout, the `T###` identifier scheme, the `completed/` archive relocation, the single-commit lifecycle, the enum-constrained Ticket status, the strict Worker Skill discipline, and the Gatekeeper's exclusive ownership of `docs/tickets/` all remain exactly as they are. Only the document syntax changes.

## User Stories

1. As a Worker agent opening a Ticket, I want the files to touch, the seam to work at, the existing anchors to model against, and the verification command to be named in a dedicated section, so that I can begin implementation without an exploratory pass.
2. As a Worker agent opening a Ticket, I want the end-to-end behaviour the Ticket makes work stated separately from the mechanical orientation, so that I do not confuse "what the user gets" with "where the code lives".
3. As a human pairing with an AI on the Runner's own Queue, I want a Ticket to read as a brief rather than as a configuration file, so that I can review a Ticket's intent without decoding a flat metadata block.
4. As a human reviewer, I want acceptance criteria rendered as checkboxes, so that I can see at a glance which criteria are satisfied and which are outstanding.
5. As a human reviewer, I want the diff of a Ticket to show exactly which criteria flipped, so that a completed Ticket carries its own account of what was proven.
6. As a human reviewer, I want the Tick to be treated as the Worker's claim and the Gatekeeper's verification to be treated as the evidence, so that a self-reported Tick never substitutes for independent verification (ADR 0002).
7. As an operator, I want every acceptance criterion the Worker left unticked listed on the Evidence Card, so that an approved-but-incomplete Ticket is visible to me before I approve it.
8. As an operator, I want a Worker caught editing a Ticket beyond its Tick permission to have its ready Signal refused, so that Ticket content stays trustworthy (ADR 0012).
9. As an operator, I want a refused Signal to consume a Verification Attempt, so that a Worker that rewrites its own Ticket cannot retry indefinitely before the Circuit Breaker trips (ADR 0017, ADR 0002).
10. As a maintainer, I want the Ticket status to remain a strict enum, so that the Runner's Queue state machine cannot be driven into a state it does not understand.
11. As a maintainer, I want the Ticket status to carry a human-readable note beside the strict status value, so that a Ticket can say "done (reviewed; Security PASSED)" without widening the enum.
12. As a maintainer, I want the Security flag to be readable when it carries its rationale inline, so that a Ticket can explain why security review applies without a second field.
13. As a maintainer, I want the Spec linkage to remain derivable from the Queue layout when the header omits it, so that scaffolded and hand-authored Tickets behave identically (ADR 0010).
14. As a maintainer, I want the blocking edges to remain a comma-separated list of Ticket identifiers, so that a Ticket states its dependencies in a form the Runner can eventually enforce without a second migration.
15. As a maintainer, I want the Ticket's reasoning effort to remain a first-class header field, so that the per-Ticket model effort selection is unaffected by the format change.
16. As a maintainer, I want the Wayfinder ticket type label to remain on the second line of the Ticket, so that ADR 0023's convention is preserved rather than silently restated.
17. As a maintainer, I want the legacy Smoke Scenarios heading to remain inert and tolerated, so that historical Tickets and superseded verification rituals keep parsing (CONTEXT.md, Spec 14).
18. As a maintainer, I want the `to-tickets` Worker Skill to define exactly one Ticket template, so that Tickets authored for any project are authored in the same shape.
19. As a maintainer, I want the `to-tickets` Worker Skill's template to be the specimen the Runner's parser is tested against, so that the format has one authoritative expression instead of three drifting copies.
20. As a maintainer, I want the published Skills Catalog to carry the canonical template, so that a newly scaffolded Target Project starts with Tickets the Runner can parse.
21. As a maintainer, I want the Runner's own Queue Tickets rewritten into the canonical shape, so that the Runner's Queue demonstrates the format it mandates.
22. As a maintainer, I want the live-test Target Projects' Tickets rewritten into the canonical shape, so that the Runner can execute those Queues against the new format without a translation layer.
23. As a maintainer, I want the archived Tickets in the Runner's own Queue left in their original shape, so that history is not churned and ADR 0023's archive exemption is honoured.
24. As a maintainer, I want the Runner's domain glossary updated to describe the Ticket, the Reasoning Variant, and the Smoke Scenarios as they now exist, so that the living vocabulary matches the format.
25. As a maintainer, I want the global Gotchas log corrected where it misdescribes which sections the parser recognises, so that future sessions are not misled about the Ticket format.
26. As a maintainer, I want the Runner's operational prompt, the Doctor's remediation text, the scaffolder's welcome Ticket, and the sanitiser's Spec rewrite to speak the canonical format, so that no part of the Runner describes a Ticket in a dialect the Runner cannot read.
27. As a maintainer, I want the Tick permission stated explicitly in the Worker's execution discipline, so that the Worker knows what it may change about its own Ticket and what it may not.
28. As an operator, I want the Queue's completion detection to keep working for Target Projects whose archived Tickets predate this format, so that a completed Ticket is never mistaken for pending work.

## Implementation Decisions

The decisions below were reached in a design session that compared the Runner's current Ticket dialect against the richer Ticket dialect used elsewhere in the Skills Catalog, and resolved the differences in favour of one canonical shape.

- **The canonical Ticket shape is the following specimen.** It is reproduced verbatim because the shape is the decision, and prose cannot state a document format as precisely as the document itself can:

  ```markdown
  # T<NNN> — <Ticket title>
  **Type:** wayfinder:task (AFK)
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

- **The metadata header is bold-label.** Each header field is a `**Label:** value` line rather than a flat `Key: value` line. The header begins on the line immediately after the Ticket title, with no intervening blank line, so that the Wayfinder ticket type label remains on the second line of the Ticket document as ADR 0023 binds it.

- **Header field semantics are unchanged in substance, changed only in presentation.** `**Status:**` carries the strict `TicketStatus` enum and nothing else; `**Status note:**` carries any human prose beside it, including the reason a Ticket was skipped. `**Spec:**` remains optional and continues to fall back to the Spec path derived from the Queue directory, so that scaffolded Tickets with no Spec directory keep resolving. `**Blocked by:**` continues to carry a comma-separated list of Ticket identifiers and remains unenforced, exactly as it is today. `**Security:**` is read on its first whitespace-delimited token and compared case-insensitively, so that a value carrying its rationale inline still resolves to the security-review requirement. `**Reasoning:**` continues to feed the per-Ticket Reasoning Variant selection.

- **Sections are top-level headings, and their names are fixed.** The parser recognises exactly five section names: `What to build`, `Jump-start`, `Acceptance criteria`, `Smoke scenarios`, and `Gotchas`. A recognised heading at any other level is inert, and a section the parser does not recognise is inert. The legacy `### Smoke Scenarios` heading remains tolerated and inert, per CONTEXT.md's treatment of the superseded ritual.

- **The domain model gains two fields and changes no existing one's type.** The Ticket entity gains a `jump_start` field holding the orientation entries, and a `checked_criteria` field holding the text of the criteria the Worker has acknowledged. The `acceptance_criteria` field continues to hold criterion text only, with the checkbox marker stripped, so no existing consumer of criterion text sees the marker. The `requirements` field continues to hold a sequence of strings, but now carries the `What to build` prose — each bullet, and each contiguous prose paragraph, is one entry. The `gotchas` field continues to hold the Gotchas entries. The Ticket status enum is unchanged.

- **The Worker may acknowledge criteria; the Gatekeeper polices the boundary.** This is the one intentional departure from the Runner's existing discipline, and it is carved out explicitly rather than opened generally. The Worker may flip an acceptance criterion from `- [ ]` to `- [x]` and may change nothing else in the Ticket document. The Gatekeeper takes a dispatch baseline of the Ticket document before the Worker begins, and at verification time computes the difference between the baseline and the current document, allowing only checkbox flips on acceptance-criterion entries. Any other difference is a violation: the ready Signal is refused, and the refusal consumes a Verification Attempt, so a Worker that rewrites its own Ticket exhausts the Circuit Breaker rather than retrying indefinitely (ADR 0017, ADR 0002).

- **Acknowledgement is documentary; verification decides.** The Gatekeeper's approval rests on its own verification commands, never on the Worker's acknowledgement. On approval, the Gatekeeper stamps the Ticket's completion metadata and relocates the document into the archive directory as it does today. Any criterion the Worker left unacknowledged is listed on the Evidence Card so the operator can see the gap before approving, and the Gatekeeper never un-acknowledges a criterion and never rewrites criterion text.

- **The skipped path converges on the status note.** When the Circuit Breaker skips a Ticket, the Gatekeeper writes the strict skipped status together with a human-readable status note carrying the failure text, plus one labelled line per additional detail the skip reports, such as the attempt count or the reason. This replaces the separate failure field and keeps all human prose in one place.

- **The serialiser patches the header in place and never touches the body.** The serialiser locates the header region, replaces or inserts labelled header lines in a fixed order, and leaves every byte after the header region untouched, including line endings, comments, and a missing trailing newline. It must not produce a second copy of a header field, and it must not insert a flat `Key: value` line into a labelled header.

- **Completion detection continues to read the archived document.** The Runner's completion check parses the archived Ticket document and reads its status, exactly as it does today. It is not made directory-aware, because the archived documents in the live-test Target Projects are part of the format change and are migrated with everything else.

- **The `to-tickets` Worker Skill is the single source of truth for the Ticket shape.** The Skill defines exactly one Ticket template — the specimen above — and one Ticket identifier scheme. The Ticket identifier remains the `T###` form bound by the Queue layout decision (ADR 0010) and enforced by the domain entity. The Skill's separate publishing branches continue to differ only in where the document is written, never in what the document contains.

- **The canonical template is republished through the Skills Catalog.** The Runner repository's copy of the `to-tickets` Worker Skill is the authoring source; the published catalogue carries it to every Target Project through the existing synchronisation path, so a newly scaffolded project begins with Tickets the Runner can parse. The Runner's own live-test Target Projects and sandboxes are resynchronised as part of the change.

- **The sibling Ticket templates are brought into line.** The regression-ticket template carried by the smoke-failure Worker Skill and the worked examples carried by the Wayfinder Worker Skill both adopt the canonical shape, because both are parsed or asserted against by the Runner's test suite.

- **The Runner's operational prose is brought into line.** The Worker prompt's active-Ticket rendering adopts the canonical section names and gains the orientation section, and its operational guardrails state the Tick permission and its limit. The Doctor's remediation text, the scaffolder's welcome Ticket, and the sanitiser's Spec rewrite all speak the canonical format. The Worker execution discipline's Ticket-transition step states the canonical header fields, and its autonomous-execution branch states that the Worker may acknowledge criteria and may not do anything else to the Ticket document.

- **ADR 0012 is amended in place.** Its statement that the relocated Ticket carries `Status: completed` and `Completed: <timestamp>` is restated in the canonical header form. No new decision record is created. The Wayfinder ticket type label decision is read against the canonical shape and requires no amendment, because the label's position and format are preserved by the new header.

- **The domain glossary is updated.** The Ticket definition, the Reasoning Variant definition, and the superseded Smoke Scenarios definition are restated against the canonical shape.

- **The Runner's own Queue Tickets are rewritten into the canonical shape, and the live-test Target Projects' Tickets with them.** The Runner's own live Tickets are rewritten because they are pending work that the new format must carry. The live-test Target Projects' Tickets are rewritten because those Queues are executed by the Runner and must parse. The archived Tickets in the Runner's own Queue and the historical archive are left untouched, honouring ADR 0023's archive exemption and the Runner's own Queue being worked by a human pairing with an AI rather than by the Runner.

## Testing Decisions

- **A good test asserts the document contract from outside.** A format change is proven by putting a real document on disk and asserting what comes back, and by asking the serialiser to write and asserting the bytes. No test asserts on the parser's internal helpers, on regular expressions, or on the shape of an intermediate structure that is not part of the domain contract.
- **The document contract is tested at the document-I/O seam — the highest seam for a format change.** `TicketMarkdownParser` parses a canonical Ticket document into the domain entity, and `TicketMarkdownSerializer` writes one back. Every header field's presence, absence, tolerance, and failure mode is asserted here: the strict status enum and its rejection of an unknown value; the status note's tolerance of arbitrary prose; the optional Spec field and its directory-derived fallback; the Security field read on its first token with and without an inline rationale; the Reasoning field's case-insensitive read; the type label's position on the second line; and the rejection of a Ticket document whose header is malformed.
- **The section contract is tested at the same seam.** Each of the five recognised sections is asserted to map to its domain field; an unrecognised section is asserted to be inert; the legacy Smoke Scenarios heading is asserted to remain inert and tolerated; prose in the outcome section is asserted to survive intact as requirement entries; and the orientation sub-fields are asserted to reach the domain entity as the orientation entries.
- **The checkbox contract is tested at the same seam.** A criterion is asserted to arrive with the marker stripped, with the acknowledged set holding exactly the criteria the Worker flipped, and with an unacknowledged criterion absent from that set. The criterion text is asserted to be unchanged by acknowledgement.
- **The Queue lifecycle is tested at the Queue-lifecycle seam.** The store's completion finalisation is asserted to write the canonical header, to stamp the completion timestamp, to relocate the document into the archive directory, and to leave the document body byte-identical. The skip finalisation is asserted to write the strict skipped status with the human-readable status note. The serialiser is asserted to preserve custom formatting, CRLF line endings, a missing trailing newline, and body text that resembles header fields — and is asserted never to emit a duplicate header field.
- **The Tick boundary is tested at the Gatekeeper-verification seam.** A Worker that flips a criterion and changes nothing else is accepted. A Worker that flips a criterion and also edits the outcome section, the orientation section, the Gotchas, the header, or the criterion text is refused. The refusal is asserted to consume a Verification Attempt. The dispatch baseline is asserted to be taken before the Worker runs and to be re-read at verification time.
- **The Worker prompt is tested at the prompt-construction seam.** The prompt is asserted to carry the canonical section names, the orientation entries, and the acknowledged criteria, and to state both the Tick permission and its limit. The prompt's operational guardrails are asserted to remain present.
- **The whole chain is tested once, end to end, at the Spec level.** A canonical Ticket document is written to a temporary Queue, parsed, rendered into a Worker prompt, acknowledged by a simulated Worker, verified by the Gatekeeper, approved, and finalised into the archive directory — asserting the resulting document and the authored commit contents.
- **Prior art for these tests is the existing suite.** The parser, serialiser, Queue-lifecycle, prompt-construction, and Gatekeeper test modules already exist and already cover the current format at these seams; they are updated to the canonical format rather than replaced. The Spec-level end-to-end pattern follows the previous Spec's spec test module.

## Out of Scope

- **The Spec document format.** The Spec file format, its frontmatter, and its seven sections are unchanged, as is the `to-spec` Worker Skill.
- **The Queue layout and identifier scheme.** The Queue's directory structure, the `completed/` archive directory, the sentinel lock, the global Gotchas log's location, and the `T###` identifier scheme are unchanged (ADR 0010).
- **The Ticket status enum.** The strict set of status values is unchanged; the human-readable note is a separate field rather than a widened enum.
- **Enforcing the blocking edges.** The comma-separated blocker list remains unenforced, exactly as it is today.
- **The Worker execution discipline beyond the Tick permission.** The Worker Skill's review, security-review, and live-verification obligations are unchanged.
- **Other projects' existing Tickets.** The live-test Target Projects and sandboxes named in this Spec are migrated because the Runner executes their Queues; every other project's existing Tickets, including any already written in a richer dialect, are left as they are.
- **The archived Ticket documents in the Runner's own Queue, and the historical archive.** Both are left in their original shape.
- **Machine-wide skill environment repair.** The state of the user-global skills directory is a separate concern from the Runner's canonical format.

## Further Notes

- **Seams proposed for confirmation.** The document contract and the section and checkbox contracts are asserted at the document-I/O seam; the Queue lifecycle is asserted at the Queue-lifecycle seam; the Tick boundary is asserted at the Gatekeeper-verification seam; the Worker prompt is asserted at the prompt-construction seam; and the chain is asserted once end to end at the Spec level. The Tick boundary is the only behaviour that is new rather than relocated; its placement in the Gatekeeper is what makes the dispatch baseline a Gatekeeper concern rather than a Worker concern.
- **A consequence worth naming explicitly.** The Worker's permission to acknowledge criteria is the first sanctioned write a Worker has ever had to a Ticket document. The dispatch-baseline comparison is what keeps that permission from widening into the general write that ADR 0012 and the Worker's own execution discipline forbid. If the baseline cannot be established for a Ticket, the safe behaviour is to refuse the Signal rather than to skip the comparison.
- **The Runner's own Queue is worked by a human pairing with an AI rather than by the Runner**, so its Tickets are documents for people and the Runner's parser is not their primary reader. The live-test Target Projects' Queues are the opposite: the Runner is their reader. Both are migrated to the same canonical shape because one shape that a person likes is cheaper to maintain than two shapes.
- **Two sources of drift are worth closing while this is in flight.** The `to-tickets` Worker Skill exists in divergent copies across the Runner repository, the published catalogue, and live-test Target Projects, and those copies disagree about the Ticket template. The canonical template is defined once and republished through the catalogue, which removes the need to reason about which copy is current.
- **The global Gotchas log currently states that the parser recognises a Smoke Scenarios section.** It does not, and has not since the Spec 14 rework made that heading inert. The correction belongs with this change.
- **The Runner's Spec archive contains a Spec file that no longer exists.** The previous Spec's file was removed by the ephemeral clean slate while every Ticket of that Spec still names it. The `**Spec:**` field remains optional for exactly this reason, and the rewrite does not alter which Spec path a Ticket resolves to.
