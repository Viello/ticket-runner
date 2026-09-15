# AGENTS.md

Ticket Runner: a planned local Python orchestrator that drives OpenCode through a sequential
`tickets.md` queue with independent verification, context handoffs, and Discord/terminal interaction.

## Repo status: specification only
No implementation exists yet — no `runner/`, `ticket_runner.py`, `config.yaml`, `tickets.md`,
`requirements.txt`, tests, lint, or CI. Don't search for code that isn't there; build against the
plan's target layout (§18). Do not invent test/lint commands — none are defined yet; verification
tooling arrives via an explicit ticket.

## Read before designing
- `ticket-runner-plan.md` — the spec (§17 `config.yaml` schema, §18 directory layout).
- `CONTEXT.md` — domain language; use these exact terms (Runner, Worker, Ticket, Queue, Gatekeeper,
  Checkpoint, Context Handoff, Signal, Presence Mode, Circuit Breaker, Gotchas, Isolation Layer,
  Doctor) and avoid the listed synonyms.
- `docs/adr/` — binding decisions; read before contradicting. New decisions get the next
  `NNNN-*.md` in the same one-paragraph format (`.agents/skills/domain-modeling/ADR-FORMAT.md`).

## Invariants
- OpenCode is invoked as a subprocess, never a daemon: `opencode run --format json --session <id> --auto "<prompt>"`; resume with the same session id (ADR 0001).
- Worker↔Runner messages are durable JSON files (`.agent/signals/{ticket_id}_ready.json`, `.agent/questions/{ticket_id}.json`) — never parse model stdout for state (ADR 0004).
- Only the Runner's Gatekeeper passes a ticket, by running configured test/build commands; Worker self-reports don't count; 3 failed attempts trip the circuit breaker (ADR 0002).
- All automated work happens on `agent/ticket-runner`; the Runner stages/commits (`feat(T001): Title`), and `.git/hooks/pre-push` blocks pushes (ADR 0005). Never `git push`.
- Token budget: warn 120k, handoff 135k, hard ceiling 150k; handoff writes `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- `.agent/` is untracked runtime state; git-ignore it when implementing.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh.
- Planned deps: `discord.py`, `rich`, `pyyaml`; Discord token comes from the `DISCORD_BOT_TOKEN` env var — `config.yaml` stores only the var name, never the token.
- No git hooks are installed yet (only `.sample` files in `.git/hooks/`).

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; `handoff`, `claude-handoff`, `to-tickets` have project-specific edits. Don't bulk-reformat, and don't overwrite local copies with the global ones.
- `.agents/skills/handoff/SKILL.md` is load-bearing (the Runner's handoff protocol calls it by path) — don't move or rename it.
