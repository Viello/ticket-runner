---
name: handoff
description: Compact the current conversation into a handoff document for another agent to pick up.
argument-hint: "<target_path> [focus of next session]"
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent can seamlessly continue the work.

## Destination

If a target file path is provided in arguments (e.g. `.agent/checkpoints/T001/handoff.md`), save the handoff document directly to that path, creating parent directories if needed.

If no file path is specified, save to the OS temporary directory.

## Content Structure

Structure the document with:

1. **Active Context**: Current ticket or goal and acceptance criteria.
2. **Completed Work**: Modified files and the rationale for each change.
3. **Pending State**: Unresolved decisions, open seams, or active errors.
4. **Suggested Skills**: Specific skills the resuming agent should invoke.
5. **Immediate Next Steps**: Concrete actions for the next turn.

## Reference & Hygiene

- Reference existing specs, plans, ADRs, and commits by path rather than duplicating their text.
- State file modifications and reasons directly so the resuming agent does not need to re-read unchanged files.
- Redact credentials, tokens, or sensitive values.
- Tailor the document to any focus area specified in arguments.

