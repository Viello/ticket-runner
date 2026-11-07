---
name: handoff-ticket-runner
description: "Autonomous worker context handoff skill for Ticket Runner queues: writes structured handoff checkpoints directly to .agent/checkpoints/<ticket_id>/handoff.md without touching STATUS.md or prompting."
argument-hint: "<target_path> [focus of next session]"
disable-model-invocation: true
---

# Handoff Ticket Runner

Autonomous Worker context handoff discipline for Ticket Runner queues. Orchestrated by `ticket_runner.py` at the 135k token budget threshold.

When invoked during Context Handoff, write a structured handoff checkpoint directly to the designated checkpoint destination so a fresh Worker session can resume implementation seamlessly without lost context.

## Destination

Save the handoff document directly to the file path supplied in the prompt or arguments:
`.agent/checkpoints/<ticket_id>/handoff.md`

Ensure parent directories are created if needed.

## Content Structure

Structure the handoff checkpoint with the following standard sections:

1. **Active Context**: Current ticket ID, title, parent spec, and acceptance criteria under implementation.
2. **Completed Work**: Modified files in this session and the technical rationale for each change.
3. **Pending State**: Unresolved decisions, active failing tests, or open seams being implemented.
4. **Suggested `-ticket-runner` Skills**: Specific autonomous skills the resuming worker should invoke (such as `implement-ticket-runner`, `code-review-ticket-runner`, `security-review-ticket-runner`, or `diagnosing-bugs-ticket-runner`).
5. **Immediate Next Steps**: Concrete actions and commands for the first turn of the resumed session.

## Critical Invariants & Permissions

- **Never modify `STATUS.md`**: Ticket Runner maintains queue state in `.agent/` and ticket frontmatter; never edit `STATUS.md`.
- **Never prompt for user confirmation**: Context handoff must complete unattended without waiting for interactive terminal input.
- **Never run `git commit`**: The Gatekeeper independently verifies work and authors git commits.
- **Never relocate tickets**: Ticket files stay in their original location until Gatekeeper verification.
- **Redact secrets**: Ensure credentials, API tokens, and private data are completely redacted.
- Complete by writing the markdown checkpoint file so the Worker subprocess can exit cleanly.
