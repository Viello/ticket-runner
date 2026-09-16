# Ticket Runner

A local Python orchestrator that coordinates OpenCode to execute sequential development tickets autonomously with strict gatekeeping, context handoffs, and remote Discord/CLI interaction.

## Language

**Runner**:
The local Python orchestration process that manages queue progression, supervises Worker execution, runs verification checks, and interfaces with the user.
_Avoid_: Driver, controller, manager

**Worker**:
The OpenCode agent process invoked by the Runner to implement changes for a single ticket.
_Avoid_: Engineer, bot, subagent

**Worker Session**:
An OpenCode conversation bound to one Ticket, identified by a generated `ses_…` session id, spanning one or more Session Runs across Context Handoffs.
_Avoid_: Thread, chat, conversation

**Session Run**:
A single supervised `opencode run` process execution; the unit the Runner spawns, streams, and terminates.
_Avoid_: Invocation, process, attempt

**Ticket**:
A discrete, scoped task defined in an individual markdown file under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` containing requirements, acceptance criteria, notes, and execution status.
_Avoid_: Task, issue, work item

**Queue**:
The ordered directory of pending tickets under `docs/tickets/<spec-slug>/` sequentially executed one at a time.
_Avoid_: Backlog, pipeline

**Gatekeeper**:
The independent verification routine run by the Runner (running tests and build commands) that validates work before accepting a ticket as completed.
_Avoid_: Verifier, validator, test runner

**Checkpoint**:
A persistent snapshot of implementation progress, decisions, modified files, and next steps written to disk when a ticket session must be transferred or paused.
_Avoid_: Savepoint, snapshot, dump

**Context Handoff**:
The automated transfer of work on an active ticket from an expiring Worker session to a fresh session via a Checkpoint to prevent context exhaustion.
_Avoid_: Session rollover, context reset, context transfer

**Signal**:
A durable file written to `.agent/` by the Worker to notify the Runner of a completed implementation, a clarification question, or a pause request.
_Avoid_: Message, event, IPC

**Presence Mode**:
The Runner's operational state (`nearby` or `away`) governing whether interactive prompts stay in the local terminal or escalate to Discord after an idle timeout.
_Avoid_: Status, notification mode

**Circuit Breaker**:
A safety mechanism that halts automatic retry loops after a maximum threshold of verification failures, requiring human intervention before proceeding.
_Avoid_: Retry counter, fail-safe

**Verification Attempt**:
One full cycle of Worker execution, Signal validation, and Gatekeeper verification; exhausting the configured maximum trips the Circuit Breaker.
_Avoid_: Try, pass

**Gotchas**:
Documented quirks, pitfalls, and runtime constraints captured per ticket or globally in `docs/tickets/gotchas.md` to prevent repeated errors across sessions.
_Avoid_: Bugs, tips, notes

**Isolation Layer**:
The set of boundaries (clean git working tree per ticket, scoped prompt extraction, archived Discord threads, scoped runtime signals) preventing past ticket state from polluting active sessions.
_Avoid_: Sandbox, silo, container

**Doctor**:
The pre-flight verification routine run on startup that validates the local environment (CLI binaries, git working tree purity, hook installation, configuration syntax) before queue execution begins.
_Avoid_: Linter, pre-check, validator

**Spec**:
The parent functional specification file under `docs/specs/<spec-slug>.md` from which tickets are decomposed, defining the problem statement, architectural boundaries, and target solution.
_Avoid_: Requirement doc, PRD, epic, design doc

**Spec Excerpt**:
The concise summary (`## Problem Statement` and `## Solution`) extracted from a Spec and injected into the Worker prompt to ground ticket implementation in high-level intent without context bloat.
_Avoid_: Summary, abstract, snippet


