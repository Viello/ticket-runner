# AGENTS.md

Ticket Runner: a planned local Python orchestrator that drives OpenCode through a sequential
`tickets.md` queue with independent verification, context handoffs, and Discord/terminal interaction.

## Repo status: specification only
No implementation exists yet — no `runner/`, `ticket_runner.py`, `config.yaml`, `tickets.md`,
`requirements.txt`, tests, lint, or CI. Don't search for code that isn't there; build against the
plan's target layout (§18). Do not invent test/lint commands — none are defined yet; verification
tooling arrives via an explicit ticket.

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
- Worker executes tickets via configured `worker.execution_skill` (`.agents/skills/implement/SKILL.md`), performing pre-signal `/code-review` self-checks, but never commits directly
- Worker↔Runner messages are durable JSON files (`.agent/signals/{ticket_id}_ready.json`, `.agent/questions/{ticket_id}.json`) — never parse model stdout for state (ADR 0004).
- Only the Runner's Gatekeeper passes a ticket, by running configured test/build commands; Worker self-reports don't count; 3 failed attempts trip the circuit breaker (ADR 0002).
- All automated work happens on `agent/ticket-runner`; the Runner stages/commits (`feat(T001): Title`), and `.git/hooks/pre-push` blocks pushes (ADR 0005). Never `git push`.
- Token budget: warn 120k, handoff 135k, hard ceiling 150k; handoff writes `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- `.agent/` is untracked runtime state; git-ignore it when implementing.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh.
- Planned deps: `discord.py`, `rich`, `pyyaml`; Discord token comes from the `DISCORD_BOT_TOKEN` env var — `config.yaml` stores only the var name, never the token.
- No git hooks are installed yet (only `.sample` files in `.git/hooks/`).

## Development workflow
The project moves across four rungs. The human–agent pair drives all four interactively; the planned Ticket Runner automates the Queue Execution rung.

### 1. Alignment & Design
- **Stress-test** plans or architecture decisions: `/grill-me` (or `/grill-with-docs` to capture decisions as ADRs and glossary entries in `CONTEXT.md`).
- **Throwaway** state or UI experiments before committing to a design: `/prototype`.
- **Deepen** shallow modules and surface architectural friction with an HTML report: `/improve-codebase-architecture`.

### 2. Specification & Queueing
- **Synthesize** aligned requirements into a formal spec without interviewing: `/to-spec`.
- **Decompose** a spec or conversation into tracer-bullet tickets directly in `tickets.md`: `/to-tickets`.

### 3. Execution (Interactive or Ticket Runner)
- **Implement** tickets using TDD at pre-agreed seams with frequent typechecks and test runs: `/implement`.
- **Autonomous queue execution**: When driven by Ticket Runner, the Worker implements the active ticket slice guided by `config.yaml: worker.execution_skill` (`.agents/skills/implement/SKILL.md`), but NEVER commits; Gatekeeper alone commits upon passing independent tests (ADR 0002, ADR 0008).

### 4. Quality & Resilience
- **Pre-signal review**: Conduct two-axis standards and spec review before committing or emitting `{ticket_id}_ready.json`: `/code-review`.
- **Root-cause debugging**: Build a tight, red-capable feedback loop when diagnosing hard failures: `/diagnosing-bugs`.
- **Context preservation**: Checkpoint progress to `.agent/checkpoints/{ticket_id}/handoff.md` at 135k tokens: `/handoff`.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; `handoff`, `claude-handoff`, `to-tickets` have project-specific edits. Don't bulk-reformat, and don't overwrite local copies with the global ones.
- `.agents/skills/handoff/SKILL.md` is load-bearing (the Runner's handoff protocol calls it by path) — don't move or rename it.
- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline (`worker.execution_skill`).

