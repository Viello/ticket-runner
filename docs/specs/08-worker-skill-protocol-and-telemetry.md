# Spec 08: Worker Skill Protocol and Stream Telemetry

## Problem Statement

When autonomous Worker sessions execute development tickets, they frequently bypass established project methodology, repository invariants, and review standards. In particular, when guided only by passive file pointers or interactive slash-command syntax (`/code-review`, `/security-review`), headless CLI agents do not execute these self-checks as tool calls and proceed to signal completion without performing pre-signal verification or TDD discipline. Furthermore, root operational invariants defined in `AGENTS.md` are not automatically ingested by CLI sessions, leading to ungrounded work. Finally, inter-process event streams discard tool execution events when wire event formats drift, leaving the Runner blind to whether project skills and operating rules were consulted during ticket execution.

## Solution

Enforce explicit, tool-directed file-reading instructions in Worker prompts across all lifecycle phases (startup implementation, repository orientation, pre-signal review, security review, and failure diagnostics) while inlining critical `AGENTS.md` invariants directly into the prompt. Update the Runner's stream decoder to recognize live tool use events, track skill and `AGENTS.md` file accesses during Session Runs, and emit soft warnings via console and Discord when a Worker attempts to signal ready without having inspected required review skills or operating invariants, while maintaining independent Gatekeeper verification as the final quality barrier. Extend the Doctor to verify the presence of all required skills and `AGENTS.md` before queue processing begins.

## User Stories

1. As a developer, I want the Worker prompt to explicitly instruct the agent to read and follow the configured execution skill file using its file reading tool before writing any code, so that implementation begins with established TDD and seam discipline.
2. As a developer, I want the Worker prompt to inline the critical `## Invariants` section from `AGENTS.md` and instruct the agent to read the full `AGENTS.md` file using its file reading tool, so that the Worker understands and respects root operating constraints.
3. As a developer, I want the Worker prompt to explicitly instruct the agent to read and follow `.agents/skills/code-review/SKILL.md` using its file reading tool before emitting a ready Signal, so that the agent performs standards and spec reviews without relying on unsupported slash commands.
4. As a developer, I want the Worker prompt to explicitly instruct the agent to read and follow `.agents/skills/security-review/SKILL.md` using its file reading tool when ticket frontmatter declares `Security: required`, so that security self-checks are systematically performed.
5. As a developer, I want the Worker to summarize its findings from the required review skills directly inside the `self_review_notes` field of the ready Signal, ensuring durable auditing of self-checks.
6. As a developer, I want the failure resume prompt on repeated Gatekeeper verification failures (attempt 2 or greater) to explicitly instruct the agent to read and follow `.agents/skills/diagnosing-bugs/SKILL.md` using its file reading tool before modifying code, so that diagnostic discipline is applied to hard failures.
7. As a developer, I want the Runner stream decoder to recognize `tool_use` events emitted by OpenCode CLI, so that tool invocations are not discarded as unknown events.
8. As a developer, I want the Runner to detect when the Worker accesses project-local skill files under `.agents/skills/` or `AGENTS.md` via file-reading tools or commands, recording accessed resources in Session Run telemetry.
9. As a developer, I want the Runner to detect skill and `AGENTS.md` file references in raw stream lines as a fallback mechanism, ensuring robust detection across varied CLI output formatting.
10. As a developer, I want the Runner to emit an immediate warning notice to the terminal and Discord if a Worker emits a ready Signal without having accessed the mandatory code review skill or `AGENTS.md`, alerting the operator while allowing Gatekeeper verification to proceed.
11. As a developer, I want the Runner to emit an immediate warning notice to the terminal and Discord if a Worker emits a ready Signal on a security-flagged ticket without having accessed the security review skill.
12. As a developer, I want the Runner's Doctor to verify that `AGENTS.md`, configured execution skills, and mandatory review skills exist on disk before queue processing starts, preventing broken sessions caused by missing skill handbooks or operating rules.

## Implementation Decisions

- **Direct File-Reading Directives**: Prompts instruct the Worker to use its file reading tool (`read(filePath="...")`) rather than referencing OpenCode internal tool abstractions or interactive slash commands (`/code-review`).
- **Phased Lifecycle Directives**:
  - *Startup Phase*: Directs the Worker to first read `worker.execution_skill` (default `.agents/skills/implement/SKILL.md`), and then read `AGENTS.md` before writing code.
  - *Invariants Inlining*: The `## Invariants` section of `AGENTS.md` is extracted and inlined directly into the prompt's Operational Guardrails section (alongside the Spec Excerpt).
  - *Pre-Signal Review Phase*: Directs the Worker to read `.agents/skills/code-review/SKILL.md` and record findings in `self_review_notes`.
  - *Security Review Phase*: When `ticket.security_required` is true, directs the Worker to read `.agents/skills/security-review/SKILL.md` and record findings in `self_review_notes`.
  - *Failure Diagnostics Phase*: On repeated verification attempts ($\ge 2$), prepends instructions to read `.agents/skills/diagnosing-bugs/SKILL.md` before attempting further fixes.
- **Wire Event Recognition**: Add `tool_use` to `KNOWN_EVENT_TYPES` in the OpenCode CLI stream adapter.
- **Dual Resource Ingestion Detection**: Detect resource accesses (skills and `AGENTS.md`) through structured `tool_use` payload inspection (file paths in `read` and command strings in `bash`) combined with raw line substring scanning.
- **Soft Warning Notification Contract**: When a ready Signal is received, if required review skills or `AGENTS.md` were not accessed during the ticket's session runs, emit a warning via the notification port (`_notify`) and log at `WARNING` level, but proceed unconditionally to Gatekeeper verification.
- **Doctor Pre-flight Verification**: Add `CHECK_AGENTS_MD` to verify `AGENTS.md` exists and is readable at workspace root, and verify that `worker.execution_skill`, `.agents/skills/code-review/SKILL.md`, and `.agents/skills/diagnosing-bugs/SKILL.md` exist and are readable files.

## Testing Decisions

- **External Behavior Seams**:
  - Prompt generation tested by asserting rendered prompt strings: verifying explicit file-reading directives for `execution_skill`, `AGENTS.md`, `code-review`, `security-review`, presence of inlined invariants, and absence of slash commands.
  - Event stream parsing tested by passing raw JSONL event strings representing `tool_use` and verifying decoded events and detected skills / `AGENTS.md`.
  - Supervisor telemetry tested with in-memory command runners emitting scripted JSONL streams and verifying `skills_accessed` on `SessionRunResult`.
  - Soft warning logic tested by verifying that notification spies receive expected warnings when ready Signals arrive with incomplete access sets.
  - Doctor pre-flight checks tested with existing vs missing `AGENTS.md` and skill files.
- **Prior Art**: Models existing tests in `test_prompt_builder.py`, `test_opencode_worker.py`, `test_ticket_processor.py`, and `test_doctor.py`.

## Out of Scope

- Blocking Gatekeeper verification when review skills or `AGENTS.md` are omitted (Gatekeeper remains solely bounded by test/build exit codes).
- Supporting remote or global skills outside the project repository (only `.agents/skills/` and workspace `AGENTS.md` are monitored).
- Modifying OpenCode CLI binary internals or plugin registries.

## Further Notes

- Inlining `AGENTS.md` invariants provides an immediate cognitive guardrail inside the prompt token window, while the file-reading directive prompts the Worker to explore broader architectural rules if needed.
