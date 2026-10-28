# AGENTS.md

Ticket Runner: an external multi-agent Python orchestrator that drives AI coding agents (OpenCode, Antigravity CLI) through a sequential directory queue under Target Project's `docs/tickets/` with independent verification, context handoffs, and Discord/terminal interaction.

## Implementation status
Specs 01–16 are implemented and tested; Spec 17 is decomposed into `T124`–`T129`; live-test sequence under Target Project (`agent-skills`) is ready to resume.

## Read before designing
- `ARCHITECTURE.md` — target Clean Architecture directory tree.
- `ticket-runner-plan.md` — the spec (§17 `config.yaml` schema).
- `CONTEXT.md` — domain language; use these exact terms (Runner, Worker, Ticket, Queue, Gatekeeper, Checkpoint, Context Handoff, Signal, Presence Mode, Circuit Breaker, Gotchas, Isolation Layer, Doctor) and avoid the listed synonyms.
- `docs/adr/` — binding decisions; read before contradicting. New decisions get the next `NNNN-*.md` in the same one-paragraph format (`.agents/skills/domain-modeling/ADR-FORMAT.md`).

## Working on this repo (Human + AI workflow)
Working on `D:\Projects` itself is strictly an interactive **Human + AI pair-programming workflow**, never autonomous Ticket Runner execution:
- **Interactive pair programming**: You are pairing directly with the human developer to design, implement, and maintain Ticket Runner. Never emit `.agent/signals/{ticket_id}_ready.json`, never emit `.agent/questions/{ticket_id}.json`, and never wait for an automated Gatekeeper when working in this repository.
- **Ticket discipline**: Follow the Human + AI ticket track (`/to-tickets` for decomposition, `/implement` for implementation, `/code-review` for standards and spec reviews, and `/security-review` when flagged).
- **Interactive commit execution**: Drive implementation test-first at agreed seams. Automatically stage and author git commits once targeted tests and reviews pass, without pausing for confirmation.
- **Git isolation**: All work happens on branch `agent/ticket-runner`; `.git/hooks/pre-push` blocks pushes (ADR 0005). Never `git push`.
- **Commit format**: Title must be `<type>(<scope>): <Title>` where `<scope>` names the architectural layer or subsystem (`packaging`, `domain`, `ports`, `adapters`, `git`, `doctor`, `queue`, `discord`, `ui`), never a ticket number. Follow with a blank line and hyphen-bulleted (`- <action>`) imperative changes without trailing periods. No ticket numbers in title or body.
- **Source of truth**: Working code, unit tests, and CLI interfaces are authoritative over markdown documentation. Specifications and tickets are ephemeral scaffolding; never modify root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`) without explicit user approval.

## Dual-backend parity (OpenCode & Antigravity CLI)
Ticket Runner treats OpenCode and Antigravity CLI as equal first-class agent backends. Every new feature, CLI flag, or architectural change must account for both:
- **Universal compatibility**: Any feature or modification touching agent invocation, process supervision, streaming telemetry, model/reasoning selection, session management, Doctor environment checks, or TUI launching must work seamlessly with both **OpenCode** (`OpenCodeWorker`) and **Antigravity CLI** (`AntigravityWorker`).
- **Bridge in adapter code**: When the two CLIs differ natively in arguments, outputs, or mechanics (e.g. `--variant` vs `--effort`, session ID formats `ses_…` vs UUID, JSON streaming event structures), write adapter code in `runner/adapters/opencode/` and `runner/adapters/antigravity/` to bridge and normalize them into domain models (`WorkerEvent`, `AgentWorker`).
- **Explicit graceful gating**: If a capability genuinely cannot be supported on one backend due to upstream CLI limitations, explicitly gate or disable it for that backend with an informative log or fallback so the rest of the Runner pipeline never breaks.
- **Dual test coverage**: Every agent-facing change must be accompanied by unit or adapter tests covering both `OpenCodeWorker` and `AntigravityWorker`.

## Product architecture invariants (Target Project orchestration)
These invariants govern how Ticket Runner orchestrates an external Target Project (`--project-dir <path>`):
- **Subprocess execution**: Agent backends (OpenCode, Antigravity CLI) are invoked as subprocesses, never daemons, each with its own structured streaming envelope (OpenCode: `opencode run --format json --session <id> --auto "<prompt>"`; Antigravity: `agy -p "<prompt>" --output-format stream-json [--conversation <uuid>]`). Resumption uses the session id each backend emits (`ses_…` for OpenCode, `conversation_id` UUID for Antigravity).
- **External path resolution**: Treat the Target Project directory as execution `CWD`. Resolve all paths inside `.agent/`, `docs/tickets/`, `docs/specs/`, and `.agents/skills/` relative to the Target Project root; the Runner's source repository and installation remain separate and independent.
- **Autonomous Worker contract**: The autonomous Worker subprocess implements tickets via configured `worker.execution_skill` (`.agents/skills/implement-ticket-runner/SKILL.md`), but never commits directly, moves files, or edits `docs/tickets/gotchas.md`.
- **Durable signals**: Worker↔Runner messages are durable JSON files (`.agent/signals/{ticket_id}_ready.json`, `.agent/questions/{ticket_id}.json`) — never parse model stdout for state (ADR 0004).
- **Independent Gatekeeper**: Only the Runner's Gatekeeper passes a ticket, by running configured test/build commands; Worker self-reports don't count; 3 failed attempts trip the circuit breaker (ADR 0002).
- **Stuck-suite triage**: Before emitting `{ticket_id}_ready.json`, Worker confirms the test suite is not stuck following `/diagnosing-bugs` § Stuck-Test-Suite Protocol.
- **Token-preserving verification**: Behavioral verification harnesses execute out-of-band and persist full logs, traces, screenshots, and DOM snapshots to `.agent/evidence/<ticket_id>/`. The agent context receives only a bounded excerpt (maximum 30 lines / 1,000 characters) on verification failure.
- **Human-in-the-Loop gate**: In Human-in-the-Loop mode, Gatekeeper verification halts after green checks to present an Evidence Card via the active presence channel (Terminal prompt or Discord Status Card); commits strictly require human approval.
- **Token budget**: warn 120k, handoff 135k, hard ceiling 150k; handoff writes `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- **Single commit per ticket**: Gatekeeper approval authors exactly one commit combining code, tests, newly logged gotchas, and the relocated ticket file (`Status: completed`); never record commit SHA in ticket frontmatter (ADR 0012).
- **Runtime state**: `.agent/` is untracked runtime state; git-ignore it when implementing.
- **Out-of-band Live QA**: Human verification happens after green checks via a human-invoked `/live-qa` session (refused in human absence); durable verdicts are recorded by the human's session at `.agent/live-qa_log_<slug>.md`; the Gatekeeper authors no verification logs; the Worker drafts no scenarios and self-reports no manual verification.
- **Spec-closing alignment ticket**: Every ticket queue under `docs/tickets/<spec-slug>/` must include a final closing ticket tasked with auditing implementation against the spec and updating root living documents if any architectural details shifted.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh.
- Dependencies: `discord.py`, `rich`, `pyyaml`, `pytest` (see `requirements.txt`). Discord token comes from the `DISCORD_BOT_TOKEN` env var — `config.yaml` stores only the var name, never the token.
- Discord and terminal-UI adapters are implemented under `runner/adapters/discord/` and `runner/adapters/ui/`.
- Pre-push hook guardrail is installed via `runner/adapters/git/pre_push_hook.py` reading `scripts/pre-push.sh`.

## Development workflow
The project moves across four rungs. The human–agent pair drives all four interactively; the planned Ticket Runner automates the Queue Execution rung on Target Projects.

### 1. Alignment & Design
- **Stress-test** plans or architecture decisions: `/grill-me` (or `/grill-with-docs` to capture decisions as ADRs and glossary entries in `CONTEXT.md`).
- **Throwaway** state or UI experiments before committing to a design: `/prototype`.
- **Deepen** shallow modules and surface architectural friction with an HTML report: `/improve-codebase-architecture`.

### 2. Specification & Queueing
- **Synthesize** aligned requirements into a formal spec without interviewing: `/to-spec`.
- **Decompose** a spec or conversation into tracer-bullet tickets under `docs/tickets/<spec-slug>/`: `/to-tickets` (always conclude each spec queue with a spec-closing alignment ticket).

### 3. Execution (Interactive)
- **Implement** tickets using TDD at pre-agreed seams with frequent typechecks and test runs: `/implement`.
- **Interactive commit execution**: The assistant automatically stages and commits once targeted tests and code/security reviews pass, without pausing for confirmation.

### 4. Quality & Resilience
- **Pre-signal review**: Conduct standards and spec review before committing: `/code-review`.
- **Security review**: When explicitly flagged by ticket requirements/frontmatter (`Security: required`) or the user, invoke `/security-review` before committing.
- **Root-cause debugging**: Build a tight, red-capable feedback loop when diagnosing hard failures: `/diagnosing-bugs`.
- **Stuck-suite triage**: When the verification suite hangs or cascades, classify the failure and isolate the first failing test before retrying or escalating — `/diagnosing-bugs` § Stuck-Test-Suite Protocol.
- **Live QA & failure triage**: After green checks, human verification is conducted via `/live-qa` recording verdicts in `.agent/live-qa_log_<spec-slug>.md`. For failure triage: read `[failed]` entries from the live-qa log, debug via `/diagnosing-bugs`, and recover via `/smoke-fail`.
- **Context preservation**: Checkpoint progress to `.agent/checkpoints/{ticket_id}/handoff.md` at 135k tokens: `/handoff`.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; `handoff`, `claude-handoff`, `to-tickets` have project-specific edits. Don't bulk-reformat, and don't overwrite local copies with the global ones.
- `.agents/skills/handoff/SKILL.md` is load-bearing (the Runner's handoff protocol calls it by path) — don't move or rename it.
- `.agents/skills/implement/SKILL.md` defines the interactive Human+AI worker implementation discipline.
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline (ADR 0013).

## Session Orienting & Status
- At the start of every session or when resuming, read root `STATUS.md` if present.
- Present the 4-bullet "Welcome Back" briefing and confirm the active ticket and immediate next step before modifying code.
- Before concluding a session or handing off, invoke `/retro`, `/handoff`, or `/status save` to refresh `STATUS.md`.
