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

**Worker Skill**:
A structured methodology handbook stored as a markdown file under `.agents/skills/<name>/SKILL.md` that guides Worker discipline across lifecycle phases (implementation, pre-signal review, security, and debugging) via direct file reads.
_Avoid_: Plugin, slash command, agent tool

**TUI Session**:
An OpenCode session run in interactive TUI mode (without `--format json`) against the same session id as the active Worker Session, launched by the Runner after pausing at a signal boundary to allow direct user inspection or input. The Runner is blind to all activity during a TUI Session: tokens are untracked, Signals are not emitted, and the Gatekeeper does not run.
_Avoid_: Live session, interactive session, direct session, manual session

**Status Card**:
The pinned message at the top of a Ticket's Discord thread, edited in-place at every phase transition, showing ticket ID, slug, spec, current phase, attempt count, token usage, and start/last-updated timestamps. A stale Last updated timestamp is the canonical indicator of a crashed bot or frozen Runner.
_Avoid_: Pinned header, ticket dashboard, summary message

**Live Digest**:
A single plain-text Discord message posted at the start of each Session Run and edited in-place to show a rolling 500-character window of the LLM's current response content. Always posted regardless of Presence Mode. Marked `[done]` when the Session Run ends.
_Avoid_: LLM stream, rolling excerpt, live feed, output log

**DiscordGateway**:
The raw Discord API seam (a protocol/interface) exposing primitive operations — `post_message`, `edit_message`, `pin_message`, `create_thread`, `edit_thread`, `archive_thread` — without embedding any routing or formatting logic. Implemented by the real discord.py adapter and by in-memory test doubles.
_Avoid_: Discord client, Discord adapter, bot interface

**DiscordLogger**:
The logging logic port that sits above `DiscordGateway`. Owns severity routing (critical vs routine), embed construction, message chunking at 1,950 characters, Status Card edits, and Live Digest rate-limited edits. Accepts structured log events from the Runner and decides format, targeting, and dispatch.
_Avoid_: Discord notifier, log sink, message sender

**Model Selection**:
The startup-time choice of which configured LLM (`provider/model` string) the Runner will use for the entire session. Presented as an interactive numbered prompt when multiple models are configured; auto-selected silently when exactly one model is configured; overridable via `--model <id>` CLI flag. The selected model is session-scoped — fixed until the Runner restarts — and stored in `.agent/state.json` for crash recovery.
_Avoid_: Model switch, model picker, LLM choice

**Reasoning Variant**:
The per-ticket reasoning depth setting declared in a ticket's `Reasoning:` frontmatter field and passed to OpenCode as `--variant`. Controls the model's thinking effort (e.g. `low`, `medium`, `high`, `max` on Anthropic; provider-specific strings on others). Resolved in priority order: ticket `Reasoning:` field → `model.default_reasoning` in config → flag omitted (OpenCode default). Applied uniformly across all Session Runs under the ticket.
_Avoid_: Thinking level, reasoning mode, inference depth

**Crash Recovery**:
The startup procedure that inspects `.agent/state.json` and `git status --porcelain` to safely resume an in-flight ticket, reconnect to an active Worker Session, or restore from a Checkpoint after an unexpected termination.
_Avoid_: Reboot recovery, auto-resume, restart handler

**State Store**:
The persistence seam responsible for atomic, durable reads and writes of runner execution state to `.agent/state.json`.
_Avoid_: State manager, DB, cache

**Terminal Display**:
The local terminal user interface built with Rich Live that renders the pinned status header, token gauge, scrolling telemetry ring buffer, and hotkey legends during execution.
_Avoid_: Dashboard, console UI, terminal viewer

**Smoke Scenarios**:
The named, human-executable verification scripts embedded in each ticket under `### Smoke Scenarios`. Each scenario specifies Setup (synthetic conditions to manufacture), Steps (numbered operator actions), and Expected (observable outcome). Populated during ticket drafting; audited for automated coverage by the Worker at Smoke Scenarios Handoff; human-action scenarios forwarded to the operator via terminal and ready signal.
_Avoid_: Manual Verification, Human Verification, Operator Checklist, manual tests
