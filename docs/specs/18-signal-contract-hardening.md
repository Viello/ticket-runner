---
spec_id: 18-signal-contract-hardening
triage: ready-for-agent
status: settled
date: 2026-10-30
author: Gab
target_project: D:\Projects (Runner) and provisioned Target Projects (e.g. D:\Repos\ticket-runner-site)
related_adrs:
  - ADR 0002 (Independent Gatekeeper Verification)
  - ADR 0004 (Explicit Signal Files)
  - ADR 0008 (Configurable Worker Execution Skill)
  - ADR 0017 (Invalid Signal Consumes Verification Attempt) — amended by this spec
  - ADR 0024 (Signal Schema Ownership and Contract Checks) — proposed by this spec
  - ADR 0025 (Malformed Signal Retention and Retry) — proposed by this spec
---

# Spec 18: Signal Contract Hardening — One Schema Authority, Pre-Dispatch Contract Checks, and Cheap Malformed Signals

## Problem Statement

A Ticket in a Target Project can be implemented correctly, verified green, and still be rejected at the last step because the Runner shipped two contradictory definitions of the ready Signal. In the incident that motivated this Spec, a Worker followed the execution skill it was explicitly told to read first, wrote `new_gotchas` as an array of `{problem, solution}` objects, and the Gatekeeper rejected the Signal as malformed. The file was then deleted, the run escalated on the first failure, and the queue stopped with no commit authored — after roughly 146,000 of a 200,000-token budget and 42 minutes of Queue time. The completed working tree survived; the run did not.

The failure was not "the model produced bad JSON". It was five structural problems in the Runner:

1. **There is no single authority for the Signal schema.** Four hand-maintained copies exist: the execution skill, the task prompt, the ready Signal parser, and the question Signal parser. The skill says objects; the prompt says strings; the parser enforces strings. The Worker is instructed to read the skill before doing anything else, so the first document it reads is the one the enforcement point rejects.

2. **The question Signal schema is already invalid and has not fired yet.** The execution skill documents a question shape the Runner cannot parse. Any Worker that blocks and asks for clarification will hit the same wall, from the opposite direction.

3. **Nothing validates a provisioned skill copy before dispatch.** A test in the Runner repository cannot protect a Worker Skill already copied into an arbitrary Target Project. The Runner's own Doctor checks that the configured execution skill exists and is readable, not that its content is compatible with the protocol it will be judged against.

4. **A malformed Signal is treated as a run-ending event rather than a cheap correction.** The invalid file is deleted before the operator sees it, the diagnostic report is written only when the operator declines to intervene, and the configured escalation policy fires on the first occurrence. A self-correctable typo costs the same as a security boundary violation.

5. **Different presence and entry paths disagree about the same failure.** Interactive and non-interactive runs take different decisions on the same malformed Signal, and two malformed-question handlers apply different accounting.

The cost is paid by the Target Project operator: a completed Ticket, a preserved working tree, and no commit — plus the tokens and wall-clock time to produce neither.

## Solution

Make the Signal schema a property of the domain, render it into the prompt, and make every other copy defer to it or be machine-checked against it. Then make a malformed Signal cheap: archive it, diagnose it, retry once when the failure is self-correctable, and escalate when it is not.

1. **The domain owns the schema.** A frozen field-spec value object describes every field of the ready and question Signals, and renderers produce both the example payload and the human-readable protocol text. The prompt renders from those functions instead of maintaining hand-written bullets. A test reflects over the Signal dataclasses and fails if a field exists in the parser but not the renderer, or the renderer advertises a field the parser rejects.

2. **Human-readable metadata tolerates documented shapes; load-bearing fields stay strict.** `new_gotchas` accepts the canonical `{problem, solution}` object, the `fix` alias, and plain strings, canonicalising all three to the text form the Gotchas store already understands. Ticket identity, status, modified files, timestamp, and scope remain strict.

3. **The execution skill stops duplicating the schema.** Both JSON blocks are removed and replaced with a pointer to the prompt's protocol section. The prompt gains one sentence declaring that section authoritative over any other document.

4. **Every provisioned copy is machine-checked before dispatch.** A pure contract checker extracts fenced JSON blocks from markdown, classifies ready versus question examples, substitutes documented placeholders, and validates them through the real parsers. It runs as a Doctor pre-flight check, as a gate in the skills publish step, and as a repository test over the canonical execution skill.

5. **A malformed Signal is archived, diagnosed, and retried before escalation.** The raw payload is copied to a stable archive path before consumption, the diagnostic report is written before the operator is prompted, and a format error is classified separately from a boundary violation. The first format error per Ticket run is retried automatically; the second follows the configured escalation policy. Ticket deletion and unauthorized ticket mutation still escalate immediately.

## User Stories

1. As a Target Project operator, I want the execution skill and the task prompt to describe the same Signal schema, so that a Worker that follows its instructions is never rejected for obeying a document the Runner shipped.
2. As a Target Project operator, I want the schema to have one authority in the domain, so that a schema change cannot silently leave a stale prompt or a stale skill behind.
3. As a Worker, I want the ready Signal example in the prompt to be a payload I can copy and have accepted, so that finishing the work is not followed by a format rejection.
4. As a Worker, I want the prompt to state that its schema section wins over any other document, so that I know which example to follow when two documents disagree.
5. As a Worker, I want to express a Gotcha as a problem and a solution, so that the lesson I learned is recorded with its remedy instead of being flattened into one line.
6. As a Worker, I want a plain-string Gotcha to remain acceptable, so that an older or hand-written Signal is not rejected over presentation.
7. As a maintainer, I want unknown keys inside a Gotcha object to be ignored, so that the Signal schema can grow without breaking older Workers.
8. As a Worker, I want a malformed Signal to come back to me as a parser error in the same Worker Session, so that I can correct it without losing the context of the work I just finished.
9. As an operator, I want the first malformed ready Signal of a Ticket run to retry automatically, so that a typo costs one Verification Attempt instead of the run.
10. As an operator, I want the second malformed ready Signal to follow my configured escalation policy, so that a Worker that cannot produce a valid Signal still reaches me.
11. As an operator, I want ticket deletion and unauthorized ticket mutation to escalate immediately, so that a security boundary violation is never mistaken for a typo.
12. As an operator, I want the raw malformed payload archived before it is consumed, so that I can inspect what the Worker actually wrote after the fact.
13. As an operator, I want a diagnostic report written whichever way I answer the escalation prompt, so that declining to intervene is not the only path that leaves evidence.
14. As an operator, I want the automatic retry to appear as a status event, so that an attempt incrementing without explanation is not mistaken for a crash or a frozen Runner.
15. As an operator, I want a malformed question Signal to follow the same retry policy as a ready Signal, so that a typo in a question does not leave the Worker waiting for an answer I never saw.
16. As an operator, I want an operator-initiated RETRY at the Circuit Breaker to remain a deliberate escalation event, so that the exemption cannot be farmed indefinitely by repeatedly granting retries.
17. As a maintainer, I want the Doctor to validate the Target Project's provisioned execution skill before dispatch, so that a stale skill is caught before a Worker spends a run following it.
18. As a maintainer, I want the Doctor failure to name the skill file and the rule it violates, so that the remediation is actionable without network access or a republished catalog.
19. As a maintainer, I want the skills publish step to refuse a catalog whose Signal examples would be rejected, so that a broken Worker Skill cannot reach other projects through the Skills Catalog.
20. As a maintainer, I want a repository test that validates the canonical execution skill, so that reintroducing an embedded example fails locally rather than in a Target Project.
21. As a maintainer, I want the prompt to show one example and mention the accepted fallback, so that it teaches one way without hiding the tolerance the parser actually provides.
22. As a maintainer, I want the schema-ownership decision and the retention-and-retry decision recorded as ADRs, so that a future change knows which document to amend.
23. As a maintainer, I want the ownership rule stated as an invariant in the operating contract, so that every Worker prompt carries the rule without it being restated per Ticket.
24. As an operator whose Worker already produced a valid implementation, I want the recovery path to preserve the working tree, so that a schema rejection never costs completed work.
25. As a maintainer, I want the Target Project's skill copy to be repairable without waiting for a catalog publish, so that a project can be brought into compliance by editing one file.

## Implementation Decisions

### 1. Domain ownership of the Signal schema

A new domain module owns the field inventory for both Signals. It exposes:

- A frozen `SignalFieldSpec` value object with `name`, `description`, and `example`.
- Ordered tuples of field specs for the ready Signal and the question Signal.
- Renderers that return a complete example payload and a complete protocol text for each Signal, parameterised by Ticket id and using a fixed valid timestamp.

Field specs are data, not markdown. The prompt builder renders them; it does not own the list. A test reflects over the Signal dataclasses and asserts every field name appears in the corresponding spec tuple, and that each rendered example parses through the real parser. This catches drift in both directions: a field added to the parser but not the prompt, and a prompt field the parser rejects.

No JSON Schema dependency is introduced. The parser is the enforcement point; the renderer and the contract checker call it.

Canonical `new_gotchas` wire shape:

```text
Canonical:          { "problem": "<non-empty>", "solution": "<non-empty>" }
Accepted alias:     { "problem": "<non-empty>", "fix": "<non-empty>" }   // "solution" wins when both are present
Accepted fallback:  "<plain text>"                                       // unchanged from today
Unknown keys:       ignored when both required keys are present
Blank required key: rejected with an error naming the field and entry index
```

All three accepted shapes are canonicalised to a `Problem: …` / `Solution: …` text form, which is already the Gotchas store's native input. Nothing downstream of the parser needs to change.

Strict fields remain `ticket_id`, `status`, `modified_files`, `timestamp`, and `scope`. The question Signal's `type`, `options`, `status`, `answer`, and `created_at` also remain strict.

### 2. Prompt renders; the execution skill defers

The ready and question protocol sections of the prompt are produced by the domain renderers. Each section states that it is authoritative: if the execution skill or any other document shows a different example, the prompt section wins.

The canonical execution skill drops both embedded JSON examples and gains one pointer sentence naming the prompt's protocol section. The pointer is the only schema-adjacent text left in the skill.

The prompt advertises the object Gotcha shape and one line stating that plain strings are also accepted. The `fix` alias is accepted by the parser but not advertised, so the prompt teaches one way while the parser absorbs a plausible near-miss.

### 3. Contract checking for provisioned skill copies

A new pure domain module extracts and validates Signal examples from markdown:

- Scan fenced `json` blocks.
- Parse each block; ignore blocks that are not mappings.
- Classify a block as a ready example when it carries the Ticket id and either `modified_files` or a ready status; classify it as a question example when it carries the Ticket id and `question`.
- Substitute documented placeholders (`<ticket_id>` and the timestamp placeholder family) recursively; leave unknown placeholders in place so the parser error names them.
- Validate through the real parsers and return indexed error strings.

Three consumers:

1. **Doctor pre-flight.** A new check constant runs after the existing skills check and reads the Target Project's configured execution skill. It fails with a remediation that names the skill file and the rule, and mentions the skills sync command only as a post-republish step. A skill with no embedded examples passes.
2. **Skills publish gate.** The publish script validates the catalog before staging and aborts on any rejected example. The script currently imports only the standard library and PyYAML, so it needs the repository root on its import path.
3. **Repository contract test.** A test validates the canonical execution skill in this repository. After the pointer edit it has no examples and passes; before it, the stale question block fails.

### 4. Malformed Signal retention

The runtime paths value object gains two contained paths under the logs directory: one for a malformed ready Signal and one for a malformed question Signal, named by Ticket id.

Before consuming a malformed Signal, the Gatekeeper reads the raw file and writes it atomically to the archive path. The archive path is appended to the diagnostics string. When the runtime paths are unavailable, as in some tests or standalone constructions, archiving is skipped and the Gatekeeper continues.

The archive is one stable file per Ticket and Signal kind, overwritten on each occurrence. It lives under untracked runtime state.

### 5. Diagnostic on every escalation

The existing diagnostic-writing block currently lives only in the operator-declined branch. It is extracted into a single helper and called before the operator is prompted, so both answers leave a diagnostic report on disk. The duplicate write in the declined branch is removed.

### 6. Escalation split: format error versus boundary violation

A new display label, `SIGNAL_FORMAT`, joins the failure-label vocabulary and its suggested-actions map. The label is used for the operator-facing report only; no branch compares label strings.

The escalation check gains a structured `self_correctable` boolean, defaulting to false, and the protocol-diagnostic builder gains a label parameter. Only the two Signal parse branches — malformed ready and malformed question — pass `SIGNAL_FORMAT` and `self_correctable=True`. Ticket deletion, unauthorized ticket mutation, and a missing Signal file keep `PROTOCOL` and escalate immediately.

Per-Ticket verification-loop state tracks whether the exemption has been used. The rule is:

- The exemption applies only when the failure is self-correctable **and** the configured escalation policy would otherwise have escalated now. An attempt that was never going to prompt does not consume it.
- When it applies, the check returns without prompting, the attempt is consumed, and the Worker Session is resumed with the parser error as diagnostics.
- The second occurrence follows the configured policy.
- An operator RETRY at the Circuit Breaker does **not** re-arm the exemption.

The exemption is per-Ticket, not per-Signal: a malformed ready Signal and a malformed question Signal share the single exemption.

### 7. Observability

The automatic retry publishes a `SIGNAL_FORMAT_RETRY` status event in the verifying state, carrying the current attempt number and a summary that names the offending field, alongside a log line. Status event names are free-form strings and no production code branches on them, so the new event requires no schema change.

### 8. Delivery and repository decisions

- Two commits: a **contract** commit (domain tolerance, renderers, prompt, canonical skill) and an **enforcement and resilience** commit (contract checker, Doctor, publish gate, archive, diagnostic, escalation split, ADRs, Gotcha, operating-contract invariant, status note).
- The ADRs introduced are numbered **0024** and **0025**; 0022 and 0023 are already taken.
- The operating contract gains one invariant: signal payload schemas live in the domain, the prompt renders them, and the execution skill defers to them.
- Catalog publishing is deferred to an explicit operator step and recorded as pending in the status document. The Target Project's skill is repaired in place so the Doctor passes without a publish.

## Testing Decisions

A good test here observes external behaviour only: the payload a parser accepts or rejects, the text a prompt contains, the files a Gatekeeper leaves behind, the decisions a Doctor returns. It does not reach into private helpers or assert on rendering internals beyond the public protocol text.

Four existing seams are used; no new seam is introduced.

| Seam | What it proves | Prior art |
| :--- | :--- | :--- |
| Domain Signal parse | Tolerance matrix, canonicalisation, strict-field rejection, rendered examples round-trip through the parser | The existing domain Signal tests |
| Prompt builder output | Every field appears, the ready status is exact, the authority sentence is present, the fallback note is present | The existing prompt-builder tests |
| Doctor pre-flight | A stale skill fails before dispatch with an actionable remediation; a clean or example-free skill passes | The existing Doctor tests |
| Gatekeeper verification loop | First format error retries without prompting; second follows policy; boundary violations still prompt; archive and diagnostic files exist for both answers; question Signals follow the same policy; operator RETRY does not re-arm | The existing verification-loop and escalation tests |

The contract checker is exercised through the Doctor seam rather than through a fourth kind of test; its pure-function cases (classification, placeholder substitution, non-Signal JSON ignored) are covered as domain unit tests behind that seam.

Behavioural coverage that must exist:

- Object, `fix`-alias, and string Gotchas are accepted and canonicalised identically; junk, nested lists, blank required keys, and non-mapping entries are rejected with a `new_gotchas` error.
- Every ready and question dataclass field is represented in its renderer.
- A rendered example parses for both Signals.
- The prompt contains each field name and the exact ready status, plus the authority sentence.
- The canonical execution skill contains no embedded Signal JSON examples.
- The contract checker accepts a valid example, rejects the stale question block naming the missing fields, and ignores non-Signal JSON.
- Doctor fails on a provisioned stale skill and passes on a clean one.
- The publish step aborts before publishing an invalid catalog.
- A malformed ready Signal with a policy of one attempt does not prompt, consumes one attempt, resumes the session, and a later valid Signal passes.
- A second malformed ready Signal prompts.
- Ticket deletion still prompts on the first occurrence.
- The archive file exists after a malformed Signal, and the diagnostics name it.
- The diagnostic report exists after escalation whether the operator answers yes or no.
- The retry status event is published with the attempt number and a summary naming the offending field.
- The malformed-question path applies the same exemption.

Verification runs per commit: the targeted suites above, Ruff and mypy over the changed files, then the full suite. The live Doctor proof needs a scratch Target Project or an old-skill fixture, because the site is repaired before the new check exists; the repaired site proves only the green path.

## Out of Scope

- Reworking the full failure analyser or changing `bug_escalation_at` semantics for test failures.
- Adding a JSON Schema dependency.
- Regenerating the rendered HTML guide.
- Session resume and restart behaviour after a Context Handoff.
- Discord pin permission repair.
- Publishing the Skills Catalog; that is deferred to an explicit operator step.
- Decomposing this Spec into a Ticket Queue; it is a document only.
- The one-off T004 recovery, which is operational and precedes the code changes.

## Further Notes

- **Incident record.** The motivating run consumed roughly 146,000 of a 200,000-token budget over 2,530 seconds, authored zero commits, and left the Ticket pending at `WAITING_FOR_USER`. The working tree was preserved and must not be reset.
- **ADR numbering.** The earlier plan assumed 0022 and 0023 were free; both already exist. The new ADRs are 0024 (schema ownership and contract checks) and 0025 (malformed-signal retention and retry).
- **Accepted residue.** Three imperfections are deliberate and should be recorded in ADR 0025 rather than fixed: after an operator RETRY the next format error prompts; the processor-side malformed-question catch remains a best-effort race guard that does not consume an attempt; and a Target Project repaired by hand carries string examples where the prompt shows objects until the catalog is republished, at which point a sync overwrites the repair.
- **Recovery sequence.** The Target Project is repaired first so the blocked Ticket can complete against existing code, then the two commits land, then the Doctor check is proven green against the repaired project.
- **Catalog dependency.** The skills sync command pulls from the published catalog, so it cannot be the sole remediation while publishing is deferred. The Doctor message names the file and the rule first for exactly that reason.
