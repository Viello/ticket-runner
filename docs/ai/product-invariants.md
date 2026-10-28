# Target Project Invariants

Long-form contract for how the Runner orchestrates a Target Project. `AGENTS.md` carries the short `## Invariants` block that `prompt_builder` inlines into every Worker prompt; this file carries the full rules and the reasons behind them. Read it when changing orchestration, verification, evidence, or human approval.

## Runtime boundary
- The Runner runs from its own installation. `--project-dir <path>` selects the Target Project and becomes the execution CWD.
- Resolve `.agent/`, `docs/tickets/`, `docs/specs/`, and `.agents/skills/` from the Target Project root. The Runner install stays independent.
- `RuntimePaths` is the single path resolver; use it instead of joining paths by hand.
- Discord and terminal-UI adapters live in `runner/adapters/discord/` and `runner/adapters/ui/`. The pre-push guardrail is installed by `runner/adapters/git/pre_push_hook.py` from `scripts/pre-push.sh`.
- Configuration schema: `ticket-runner-plan.md` §17; runtime defaults: `config.example.yaml`.

## Worker adapters
Both worker adapters are subprocesses, never daemons. Each emits a structured stream that the adapter normalizes into `WorkerEvent`.
- OpenCode: `opencode run --format json --session <id> --auto "<prompt>"`. Resume with the same `ses_…` id.
- Antigravity: `agy -p "<prompt>" --output-format stream-json [--conversation <uuid>]`. Resume with the `conversation_id` UUID.
- CLI differences belong in `runner/adapters/opencode/` and `runner/adapters/antigravity/`: `--variant` vs `--effort`, `--session` vs `--conversation`, different JSON event shapes.
- If a capability cannot work on one adapter, gate it with an explicit log or fallback. The Runner keeps going.

## Worker contract
The Worker implements one ticket through the configured `worker.execution_skill` (default `.agents/skills/implement/SKILL.md`). Its write scope is the Target Project's code and tests. Commits, ticket moves, and `docs/tickets/gotchas.md` edits belong to the Runner.

The Worker emits durable signals:
- `.agent/signals/{ticket_id}_ready.json` — implementation ready for verification.
- `.agent/questions/{ticket_id}.json` — a clarification question.

State comes from those files. Model stdout is telemetry, not protocol.

## Gatekeeper and Circuit Breaker
Only the Gatekeeper passes a ticket. It runs the configured `verification.test_cmd`, `verification.build_cmd`, and any verification harness. Worker self-reports do not count.
- A pass moves the ticket to human approval or the commit step, depending on `lifecycle.approval_mode`.
- A failure returns a bounded triage excerpt to the Worker.
- `verification.max_attempts` failures trip the Circuit Breaker and escalate to the operator (`[R]etry`, `[S]kip`, `[A]bort`).

## Token budget and handoff
- 120k: warn.
- 135k: Context Handoff. Write `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- 150k: hard ceiling; force the handoff.

## Evidence and human approval
Verification harnesses run out-of-band and persist full logs, traces, screenshots, and DOM snapshots to `.agent/evidence/<ticket_id>/`. The Worker receives at most a 30-line / 1,000-character excerpt from `evidence_triage.py`.

In `lifecycle.approval_mode: "human"` (the default is `"autonomous"`), green checks produce an Evidence Card on the active presence channel: a terminal prompt in Nearby mode, a Discord Status Card with `/approve` and `/reject` in Away mode. The commit waits for explicit approval.

## Live QA
After green checks, the human runs `/live-qa` and records durable verdicts in `.agent/live-qa_log_<slug>.md`. The Gatekeeper writes no verification log; the Worker drafts no scenarios and self-reports no manual verification.

## Queue closure
Every queue under `docs/tickets/<spec-slug>/` ends with a spec-closing alignment ticket. That ticket audits the implementation against the spec and updates the root living documents when architecture shifted.

## Decisions
- ADR 0001: OpenCode JSON streaming.
- ADR 0002: independent Gatekeeper verification.
- ADR 0004: explicit signal files.
- ADR 0005: local pre-push hook.
- ADR 0012: single commit per ticket.
- ADR 0017: invalid signal consumes a verification attempt.
