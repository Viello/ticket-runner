# AGENTS.md

Ticket Runner: an external multi-agent Python orchestrator that drives AI coding agents (OpenCode, Antigravity CLI) through a sequential directory queue under Target Project's `docs/tickets/` with independent verification, context handoffs, and Discord/terminal interaction.

## Implementation status
Specs 01–12 (Doctor, Queue, Worker, Signal Protocol, Gatekeeper, Telemetry, Handoff, Dual Presence, Discord Bot, Config & Packaging, Living Documentation & Roadmap, Decoupled Root & Multi-Agent, Scaffolding & Skills Distribution) are implemented and tested. Spec 13 (Verification Subsystem & Human Gate) forms the planned roadmap.

## Read before designing
- `ARCHITECTURE.md` — target Clean Architecture directory tree.
- `ticket-runner-plan.md` — the spec (§17 `config.yaml` schema).
- `CONTEXT.md` — domain language; use these exact terms (Runner, Worker, Ticket, Queue, Gatekeeper,
  Checkpoint, Context Handoff, Signal, Presence Mode, Circuit Breaker, Gotchas, Isolation Layer,
  Doctor) and avoid the listed synonyms.
- `docs/adr/` — binding decisions; read before contradicting. New decisions get the next
  `NNNN-*.md` in the same one-paragraph format (`.agents/skills/domain-modeling/ADR-FORMAT.md`).

## Invariants
- OpenCode is invoked as a subprocess, never a daemon: `opencode run --format json --session <id> --auto "<prompt>"`; resume with the same session id (ADR 0001).
- External path resolution: Treat the Target Project directory as execution `CWD`. Resolve all paths inside `.agent/`, `docs/tickets/`, `docs/specs/`, and `.agents/skills/` relative to the Target Project root; the Runner's source repository and installation remain separate and independent.
- Worker executes tickets via configured `worker.execution_skill` (`.agents/skills/implement/SKILL.md`), performing pre-signal reviews (`/code-review`, and `/security-review` when flagged), but never commits directly.
- Before emitting `{ticket_id}_ready.json`, Worker must confirm the test suite is not stuck: if the suite hangs or cascades, classify the failure and isolate the first failing test following `/diagnosing-bugs` § Stuck-Test-Suite Protocol before signalling readiness.
- Worker↔Runner messages are durable JSON files (`.agent/signals/{ticket_id}_ready.json`, `.agent/questions/{ticket_id}.json`) — never parse model stdout for state (ADR 0004).
- Only the Runner's Gatekeeper passes a ticket, by running configured test/build commands; Worker self-reports don't count; 3 failed attempts trip the circuit breaker (ADR 0002).
- Token-preserving verification: Behavioral verification harnesses execute out-of-band and persist full logs, traces, screenshots, and DOM snapshots to `.agent/evidence/<ticket_id>/`. The agent context receives only a bounded excerpt (maximum 30 lines / 1,000 characters) on verification failure.
- Human-in-the-Loop gate: In Human-in-the-Loop mode, Gatekeeper verification halts after green checks to present an Evidence Card via the active presence channel (Terminal prompt or Discord Status Card); commits strictly require human approval.
- All automated work happens on `agent/ticket-runner`; the Runner stages and commits, and `.git/hooks/pre-push` blocks pushes (ADR 0005). Never `git push`.
- Commit format: Title must be `<type>(<scope>): <Title>` where `<scope>` names the architectural layer or subsystem (`packaging`, `domain`, `ports`, `adapters`, `git`, `doctor`, `queue`, `discord`, `ui`), never a ticket number. Follow with a blank line and hyphen-bulleted (`- <action>`) imperative changes without trailing periods. No ticket numbers in title or body.
- Token budget: warn 120k, handoff 135k, hard ceiling 150k; handoff writes `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- Single commit per ticket: Gatekeeper approval authors exactly one commit combining code, tests, newly logged gotchas, and the relocated ticket file (`Status: completed`); never record commit SHA in ticket frontmatter (ADR 0012).
- Source of truth: Working code, unit tests, and CLI interfaces are authoritative over markdown documentation. Specifications and tickets are ephemeral scaffolding; never modify root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`) without explicit user approval.
- Spec-closing alignment ticket: Every ticket queue under `docs/tickets/<spec-slug>/` must include a final closing ticket tasked with auditing implementation against the spec and updating root living documents if any architectural details shifted.
- `.agent/` is untracked runtime state; git-ignore it when implementing.
- Every ticket must define at least one `### Smoke Scenarios` entry; a ticket with no smoke scenarios is incomplete and the Worker must not emit a ready signal.
- Every LLM-generated smoke scenario always requires human verification; automated test coverage is recorded as `[also auto-covered]` metadata only, never a substitute for human eyes. The Gatekeeper appends all scenarios to `.agent/smoke_log_<spec-slug>.md` after each passing cycle.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh.
- Dependencies: `discord.py`, `rich`, `pyyaml`, `pytest` (see `requirements.txt`). Discord token comes from the `DISCORD_BOT_TOKEN` env var — `config.yaml` stores only the var name, never the token.
- Discord and terminal-UI adapters are not yet implemented.
- No git hooks are installed yet (only `.sample` files in `.git/hooks/`).

## Development workflow
The project moves across four rungs. The human–agent pair drives all four interactively; the planned Ticket Runner automates the Queue Execution rung.

### 1. Alignment & Design
- **Stress-test** plans or architecture decisions: `/grill-me` (or `/grill-with-docs` to capture decisions as ADRs and glossary entries in `CONTEXT.md`).
- **Throwaway** state or UI experiments before committing to a design: `/prototype`.
- **Deepen** shallow modules and surface architectural friction with an HTML report: `/improve-codebase-architecture`.

### 2. Specification & Queueing
- **Synthesize** aligned requirements into a formal spec without interviewing: `/to-spec`.
- **Decompose** a spec or conversation into tracer-bullet tickets under `docs/tickets/<spec-slug>/`: `/to-tickets` (always conclude each spec queue with a spec-closing alignment ticket).

### 3. Execution (Interactive or Ticket Runner)
- **Implement** tickets using TDD at pre-agreed seams with frequent typechecks and test runs: `/implement`.
- **Interactive commit execution**: When pair-programming via IDE or CLI, the assistant automatically stages and commits once targeted tests, code/security reviews, and local smoke scenarios pass, without pausing for confirmation. In autonomous Ticket Runner execution, the Worker never commits directly; Gatekeeper alone commits upon passing independent tests and receiving human approval in Human-in-the-Loop mode (ADR 0002, ADR 0008).
- **Autonomous queue execution**: When driven by Ticket Runner, the Worker implements the active ticket slice guided by `config.yaml: worker.execution_skill` (`.agents/skills/implement/SKILL.md`), but NEVER commits directly; Gatekeeper alone commits upon passing independent tests and receiving human approval (ADR 0002, ADR 0008).

### 4. Quality & Resilience
- **Pre-signal review**: Conduct two-axis standards and spec review before committing or emitting `{ticket_id}_ready.json`: `/code-review`.
- **Security review**: When explicitly flagged by ticket requirements/frontmatter (`Security: required`) or the user, invoke `/security-review` before committing or emitting `{ticket_id}_ready.json`.
- **Root-cause debugging**: Build a tight, red-capable feedback loop when diagnosing hard failures: `/diagnosing-bugs`.
- **Stuck-suite triage**: When the verification suite hangs or cascades, classify the failure and isolate the first failing test before retrying or escalating — `/diagnosing-bugs` § Stuck-Test-Suite Protocol.
- **Smoke log review**: After all tickets for a spec complete, open `.agent/smoke_log_<spec-slug>.md` and verify each scenario manually. Debug failures interactively with the agent using `/diagnosing-bugs`. File regression tickets manually or use `/smoke-fail` to auto-create one.
- **Context preservation**: Checkpoint progress to `.agent/checkpoints/{ticket_id}/handoff.md` at 135k tokens: `/handoff`.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; `handoff`, `claude-handoff`, `to-tickets` have project-specific edits. Don't bulk-reformat, and don't overwrite local copies with the global ones.
- `.agents/skills/handoff/SKILL.md` is load-bearing (the Runner's handoff protocol calls it by path) — don't move or rename it.
- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline (`worker.execution_skill`).
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline (ADR 0013).

