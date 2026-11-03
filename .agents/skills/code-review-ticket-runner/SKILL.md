---
name: code-review-ticket-runner
description: "Autonomous worker code review skill for Ticket Runner queues: uncommitted working-tree review along Standards and Spec axes with a conditional Security axis, and question signal escalation on blockers."
disable-model-invocation: true
---

# Code Review Ticket Runner

Autonomous Worker code review discipline for Ticket Runner queues. Orchestrated by `ticket_runner.py` via an AI coding agent backend (OpenCode, Antigravity CLI).

You are an autonomous Worker subprocess reviewing uncommitted changes before signalling readiness. Your boundary is strict: you review the uncommitted working-tree diff against `HEAD` and untracked files, remediate findings, and never run `git commit`. The Gatekeeper independently verifies your work and authors the git commit.

## Scope of Review

Review the uncommitted working-tree changes:
- Run `git diff HEAD` to inspect modifications to tracked files.
- Run `git status --short` to inspect untracked new files.

Evaluate the diff across three axes:
1. **Standards**: Does the code conform to documented repository coding standards and Fowler smell baselines?
2. **Spec**: Does the code faithfully implement the originating ticket requirements without scope creep?
3. **Security (conditional)**: Does the code introduce security vulnerabilities or breach trust boundaries? (referencing `.agents/skills/security-review-ticket-runner/SKILL.md`)

The **Standards** and **Spec** axes always run. The **Security** axis runs only when the ticket frontmatter marks security as required (the `Security:` field is `required`, `true`, or `yes`, with or without bold markup). Do not infer it from paths, subprocesses, or other trust boundaries (ADR 0013).

## Review Axes

### 1. Standards Axis

Evaluate changes against repository standards (such as `CODING_STANDARDS.md` or `ARCHITECTURE.md`) and the **smell baseline** below: a fixed set of Fowler code smells (_Refactoring_, ch.3):

- **Mysterious Name**: A function, variable, or type whose name doesn't reveal what it does or holds. → Rename it clearly.
- **Duplicated Code**: The same logic shape appears in more than one hunk or file. → Extract the shared abstraction and call it from both.
- **Feature Envy**: A method that reaches into another object's data more than its own. → Move the method onto the data it envies.
- **Data Clumps**: The same few fields or parameters keep travelling together. → Bundle them into a value object or type.
- **Primitive Obsession**: A primitive or string standing in for a domain concept that deserves its own type. → Create a domain value object.
- **Repeated Switches**: The same `switch` or `if`-cascade on the same type recurs across the change. → Replace with polymorphism or a mapping table.
- **Shotgun Surgery**: One logical change forces scattered edits across many files. → Consolidate the behaviour into one cohesive module.
- **Divergent Change**: One file or module is edited for several unrelated reasons. → Split so each module changes for one reason.
- **Speculative Generality**: Abstraction, parameters, or hooks added for speculative needs the spec doesn't require. → Delete or inline back.
- **Message Chains**: Long `a.b().c().d()` navigation chains. → Hide navigation behind a method on the first object.
- **Middle Man**: A class or function that mostly delegates onward. → Call the real target directly.
- **Refused Bequest**: A subclass or implementer that ignores or overrides most of what it inherits. → Use composition instead of inheritance.

### 2. Spec Axis

Evaluate changes against the originating Ticket:
- Review the Ticket's `## What to build` and `## Acceptance criteria`.
- Verify all required behaviours are implemented and verified by tests.
- Flag any behaviour in the diff that wasn't asked for (scope creep).
- Flag any requirements that look implemented but where the logic or boundary condition is subtly wrong.

### 3. Security Axis (Conditional)

When the active ticket's `Security:` field is `required`, `true`, or `yes`, read `.agents/skills/security-review-ticket-runner/SKILL.md` using your file-reading tool (`read` / `read_file`) and audit the diff across the security boundaries.

## Severity-Gated Escalation & Question Signals

Handle findings according to their severity:

- **`LOW` / `MEDIUM` findings**: Remediate directly in code or record in `self_review_notes` inside your ready signal. Never block or interrupt the human operator for low/medium concerns.
- **`CRITICAL` / `HIGH` findings**: Remediate immediately in the session and verify that targeted tests pass.
- **Un-remediable Blockers**: Only if remediation is genuinely blocked by a required human architectural decision, missing secrets/credentials, or policy ambiguity:
  - Do NOT guess or emit a false ready signal.
  - Emit a durable question signal by writing `.agent/questions/<ticket_id>.json` following the schema in the task prompt's `Question Signal Protocol` section.
  - The Gatekeeper will halt at the intervention gate (`WAITING_FOR_USER`) and prompt the human operator via Discord or Terminal before resuming.

## Permission Boundary

- You must **NEVER** run `git commit`. The Gatekeeper authors the commit after independent verification.
- You must **NEVER** relocate tickets to `completed/`.
- You must **NEVER** edit `docs/tickets/gotchas.md`.
