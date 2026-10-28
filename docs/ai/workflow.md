# Human + AI Workflow

How work moves through this repository. This is the interactive pair-programming track. The autonomous loop in [`product-invariants.md`](product-invariants.md) runs on Target Projects, not here.

## Session start
1. Read `STATUS.md`.
2. State the active ticket, blockers, and next step in four bullets.
3. Confirm the ticket with the human before editing code.

Done when you can name the ticket and the next action.

## 1. Alignment & Design
Use `/grill-me` to stress-test a plan or architecture decision; use `/grill-with-docs` when the decision should become an ADR and a `CONTEXT.md` entry. Use `/prototype` for throwaway state or UI experiments. Use `/improve-codebase-architecture` to surface architectural friction.

Done when the approach is chosen and the trade-offs are written down.

## 2. Specification & Queueing
Use `/to-spec` to turn aligned requirements into `docs/specs/<spec-slug>.md`. Use `/to-tickets` to decompose it into tracer-bullet tickets under `docs/tickets/<spec-slug>/`.

Every queue ends with a spec-closing alignment ticket. Done when each ticket has requirements, acceptance criteria, and a clear seam.

## 3. Execution
Use `/implement` to drive one ticket test-first. Write the failing test, run that file, implement, re-run. Commit automatically once targeted tests and `/code-review` pass.

Done when the ticket's acceptance criteria are covered by tests and no unrelated files changed.

## 4. Quality & Resilience
- `/code-review` before commit: standards and spec axes.
- `/security-review` when the ticket says `Security: required` or the human asks.
- `/diagnosing-bugs` for hard failures; use the Stuck-Test-Suite Protocol when the suite hangs or cascades.
- `/live-qa` after green checks; the human runs it and records the verdict.
- `/smoke-fail` to recover from a failed live-QA verdict.

Done when the targeted tests, full suite, and required reviews are green, or the remaining failure is named.

## Session end
- `/handoff` at 135k tokens or before a context boundary; write `.agent/checkpoints/{ticket_id}/handoff.md`.
- `/retro`, `/handoff`, or `/status save` to refresh `STATUS.md`.

Done when `STATUS.md` names the next ticket and the next action.

## Ticket discipline
Follow the Human + AI ticket track. Keep tickets as tracer bullets: one seam, one verifiable outcome. The ticket file is the record; commits stay free of ticket numbers.
