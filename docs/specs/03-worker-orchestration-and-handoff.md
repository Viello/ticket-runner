# Spec 03: Worker Orchestration and Context Handoff

## Problem Statement

Large-scale coding tasks quickly exhaust LLM context windows, leading to hallucination, forgotten requirements, and degraded code quality. Furthermore, spawning background daemons or attempting unguided execution risks runaway token costs and unrecoverable sessions when context exhaustion limits are exceeded.

## Solution

Manage the OpenCode Worker as an isolated CLI subprocess with real-time JSON event telemetry. The Runner directs the Worker to the project's configured execution skill (`.agents/skills/implement/SKILL.md`) via a scoped prompt pointer while enforcing operational guardrails (overriding commits in favor of ready signals and requiring pre-signal `/code-review` self-checks). Monitor token consumption against a 150k-token budget, triggering an automated Context Handoff protocol at 135k tokens via `.agents/skills/handoff/SKILL.md`. If a Worker crashes or context limits are breached without creating a Checkpoint, trip the Circuit Breaker to alert the user, supporting emergency fallback checkpoint synthesis to guarantee zero lost work.

## User Stories

1. As a developer, I want the Runner to invoke OpenCode as a managed CLI subprocess with `--format json --auto`, so that execution lifecycle and telemetry are directly supervised without persistent daemon state.
2. As a developer, I want the Runner to inject a scoped prompt containing the active Ticket slice, an automated Spec Excerpt from the parent Spec, global Gotchas, the configured `execution_skill` pointer, and operational rules, so that the Worker's context is grounded in architectural intent while focused on the immediate task.
3. As a developer, I want the Runner's prompt to instruct the Worker to follow the discipline of `.agents/skills/implement/SKILL.md` (TDD at seams, regular test/typecheck runs), so that implementation quality remains consistent.
4. As a developer, I want the Runner's prompt to strictly forbid Worker git commits, requiring instead that the Worker emit `.agent/signals/{ticket_id}_ready.json` upon completion, so that git history authority remains solely with the Gatekeeper.
5. As a developer, I want the Worker to conduct a `/code-review` self-check against the ticket acceptance criteria and record the findings in the `self_review_notes` of the ready signal, so that Gatekeeper has visibility into implementation verification.
6. As a developer, I want the Worker to have access to `.agents/skills/diagnosing-bugs/SKILL.md` on disk for non-trivial test failures, so that root-cause debugging discipline is available when needed.
7. As a developer, I want the Runner to parse JSON stream events in real time to capture token usage, tool invocations, and textual progress.
8. As a developer, I want the Runner to emit a warning when token usage crosses 120,000 tokens, so that I am aware that the session is approaching capacity.
9. As a developer, I want the Runner to issue an automated Context Handoff instruction to the active session when token usage reaches 135,000 tokens, instructing the Worker to run `.agents/skills/handoff/SKILL.md` and exit.
10. As a developer, I want the Runner to verify that `.agent/checkpoints/{ticket_id}/handoff.md` was successfully written before terminating Session A, ensuring implementation progress is persisted on disk.
11. As a developer, I want the Runner to launch Session B using a fresh session ID, instructing it to resume from the handoff Checkpoint and inspect `git status`, providing seamless continuation.
12. As a developer, I want the Runner to enforce a hard ceiling at 150,000 tokens, forcefully killing the subprocess if the Worker ignores the handoff trigger and continues running.
13. As a developer, I want the Runner to trip the Circuit Breaker and alert me immediately if the Worker crashes or exceeds the ceiling without writing a handoff Checkpoint, so that I am notified of the disruption.
14. As a developer, I want the option during Circuit Breaker escalation to authorize an emergency Checkpoint synthesis from `git status` and `git diff`, allowing Session B to launch automatically without discarding uncommitted work.
15. As a developer, I want all session telemetry and raw JSON event streams logged to `.agent/logs/{ticket_id}_session_{session_id}.jsonl`, so that I can audit every tool call and model interaction.

## Implementation Decisions

- **Subprocess Invocation Contract**: The Worker is executed using:
  `opencode run --format json --session <session_id> --auto "<prompt>"`.
  Output is read line-by-line from standard output, with each line parsed as an independent JSON event.
- **Worker Skill Integration & Prompt Composition (ADR 0008, ADR 0011)**:
  The prompt builder in `runner/opencode.py` reads `worker.execution_skill` from `config.yaml` (default: `.agents/skills/implement/SKILL.md`). The prompt explicitly injects:
  1. Active Ticket slice (ID, title, requirements, acceptance criteria, ticket gotchas).
  2. Spec Excerpt (ADR 0011): `## Problem Statement` and `## Solution` extracted from the parent Spec (`Spec:` header or inferred from `docs/specs/<spec-slug>.md`), along with a link to the full spec file.
  3. Global Gotchas from `docs/tickets/gotchas.md`.
  4. Execution discipline from `worker.execution_skill` (TDD at seams, frequent tests/typechecks).
  5. Pre-signal `/code-review` self-check against acceptance criteria.
  6. Direct override forbidding git staging or commits.
  7. Instruction to write `.agent/signals/{ticket_id}_ready.json` with `self_review_notes` upon completion.
  8. Pointer to `.agents/skills/diagnosing-bugs/SKILL.md` on disk for non-trivial test failures.
- **Token Telemetry Extraction**: The runner extracts cumulative input and output token counts from streaming JSON payload metadata. The effective context limit is calculated as $\min(\text{configured\_ceiling}, \text{model\_context\_limit})$.
- **Handoff Protocol Execution**:
  1. Token count $\ge 135,000$: Runner sends high-priority message:
     `Context budget threshold reached (135k tokens). Execute the handoff skill at .agents/skills/handoff/SKILL.md. Save the handoff document directly to .agent/checkpoints/{ticket_id}/handoff.md. Include modified files, architectural decisions, test status, and immediate next steps. Then exit.`
  2. Runner waits for process exit. If process does not exit within 30 seconds or hits 150k, Runner sends `SIGTERM` / `TerminateProcess`.
  3. Runner validates existence of `.agent/checkpoints/{ticket_id}/handoff.md`.
  4. Runner instantiates `session_b_id` and launches with prompt referencing the checkpoint file and `git status`.
- **Emergency Fallback Checkpoint**: If Session A terminates without producing a handoff document, the Circuit Breaker halts the queue and alerts the user. If recovery is confirmed, the Runner inspects `git status --porcelain` and `git diff --stat`, formats a minimal synthetic Checkpoint markdown document, and resumes with Session B.
- **Process Supervision Seam**: Process spawning, streaming, and termination are mediated through the `CommandRunner` protocol.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify state transitions based on streamed token thresholds: warning emitted at 120k, handoff prompt dispatched at 135k, process termination enforced at 150k, and Session B resumed with checkpoint references. Tests also verify that prompt composition properly includes the configured execution skill pointer and ready-signal instructions. Tests do not depend on internal line buffer implementations.
- **Modules Tested**: Worker process supervisor, prompt builder, token telemetry monitor, handoff manager, and emergency checkpoint synthesizer.
- **Seams and Test Doubles**: Tests use a fake `CommandRunner` configured to yield mock JSON streams representing OpenCode events, verifying proper event parsing and process control without spawning live binaries.

## Out of Scope

- Modifying the internal logic of `.agents/skills/handoff/SKILL.md` (the skill is invoked as an external dependency).
- Multi-model dynamic routing during a single ticket run.
- Real-time token streaming visualization of raw tokens (handled at higher UI layer).

## Further Notes

- Context Handoff ensures that complex tickets spanning hundreds of file edits or complex refactors can continue indefinitely across chained sessions without hitting provider token context cliffs.

