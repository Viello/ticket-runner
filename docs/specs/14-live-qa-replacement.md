# Spec 14: Live QA Replacement of the Smoke Scenario Mechanism

## Problem Statement

The current Human-in-the-Loop gate rests on **smoke scenarios**: text blocks embedded in tickets at authoring time, echoed by the Worker into the ready Signal, rendered as a checklist on the Evidence Card, and appended by the Gatekeeper to a cumulative smoke log after an *automated* green run. The human never actually drives the running application — they read a checklist someone else generated and press `y`. Verification decays into ritual: the operator approves words on a card instead of observing behavior in a live system.

The `live-qa` skill (published to the user's `Viello/agent-skills` catalog and vendored at `.agents/skills/live-qa/`) inverts this: the human drives the real, running app scenario by scenario while the agent transcribes verdicts into a durable log. For that to be the single verification story, the old mechanism must go.

## Solution

Remove the smoke-scenario data path end to end — Ticket entity, ready Signal field, Gatekeeper logging, Evidence Card rendering, Worker prompt invariants — and replace it with the `live-qa` human-driven session as a purely human-side ritual, coupled to the Gatekeeper by nothing. Add a one-shot `notify` CLI subcommand so a `live-qa` session can stream per-scenario verdicts to the configured Discord channel while the session itself stays terminal-synchronous. Re-point the existing `smoke-fail` triage skill and the ticket-authoring guidance (`to-tickets`, `implement`) at the new world.

## User Stories

1. As an operator, I want to verify a finished ticket by driving the real app myself, so that my approval rests on observed behavior rather than a generated checklist.
2. As an operator, I want each scenario verdict I give to be recorded durably with a timestamp, so that the verification trail survives the session.
3. As an operator, I want the live session refused when I am not at the machine, so that a relayed second-hand "looks fine" can never count as verification.
4. As an operator, I want per-scenario verdicts streamed to Discord while I drive locally, so that a remote observer follows the session without driving it.
5. As an operator, I want the Evidence Card to stop showing a smoke-scenario checklist, so that the card reflects only what the machine actually checked.
6. As a Worker agent, I want ticket authoring to no longer require a `### Smoke Scenarios` section, so that I spend no tokens drafting scenarios a human will re-derive live anyway.
7. As a Worker agent, I want the ready Signal schema freed of the manual-verification payload, so that my completion protocol has one fewer self-report surface to get wrong.
8. As a Gatekeeper, I want to stop appending smoke-log entries, so that durable verification logs have exactly one author: the human in `live-qa`.
9. As a Gatekeeper, I want fail-closed human approval to survive the removal untouched, so that no commit is reachable without an explicit APPROVE in human mode.
10. As a Runner host, I want a `notify` subcommand that posts one message to the configured Discord channel and exits, so that external tooling can stream into the status channel without running the full bot.
11. As an operator triaging a failed live scenario, I want `smoke-fail` to find the failing entry in the live-QA log, so that the squash-or-new-commit recovery flow keeps working after the rename.
12. As a spec author, I want ticket templates and Worker prompt invariants to teach the live-qa discipline instead of the smoke-scenario discipline, so that new queues start already correct.
13. As a documentation reader, I want AGENTS.md, README, and CONTEXT.md to describe the live-qa gate, so that the living documents stay authoritative over dead mechanisms.
14. As an operator, I want the parser to tolerate a legacy `### Smoke Scenarios` heading in old ticket files, so that completed tickets from earlier specs remain readable and re-parsable.

## Implementation Decisions

- **Domain**: the Ticket entity loses its smoke-scenario collection; the Ticket Markdown parser stops extracting the `### Smoke Scenarios` region and simply ignores it as inert content (legacy tolerance, story 14). The ticket "at least one scenario" completeness rule is deleted everywhere it is enforced or echoed.
- **Signal**: the ready Signal loses the manual-verification payload and its validator; the Signal remains a durable JSON file (ADR 0004 unchanged). Old signals on disk carrying the key must parse without crashing — unknown-key tolerance, not a migration.
- **Gatekeeper**: the verification loop drops smoke-log appending, the scenario fallback chain, the empty-manual-verification warning, the commit-body scenario injection, and the terminal checklist print. `EvidenceCard` loses its scenario field; the fail-closed approval contract (human mode ⇒ explicit APPROVE only) is untouched and its existing tests must still pass. The runtime-paths smoke-log helper is removed.
- **Prompt surface**: the Worker prompt's default invariants and completion protocol replace the smoke-scenario contract with the live-qa contract: human verification happens *after* green checks via a `/live-qa` session the human runs; the Worker drafts no scenarios and self-reports no manual verification.
- **Approval adapters**: the terminal panel and the Discord embed drop their scenario checklist sections and the scenario-specific truncation/paging logic that exists only to fit that checklist into Discord's field limits. Secret scrubbing and all other card content remain.
- **CLI `notify`**: a new top-level subcommand mirroring the existing `bot` subcommand's construction path — validates Discord enablement, channel id, and the token env var, builds the bot container, posts one message via the existing gateway port's message-posting method, exits. Non-zero exit with a clear diagnostic when configuration is missing. No changes to the gateway port itself.
- **Skill/docs surface** (each of these tickets invokes `/writing-for-agents`): `smoke-fail` re-targeted to read `[failed]` entries from `.agent/live-qa_log_<slug>.md` and to name the originating context accordingly; `to-tickets` template guidance drops the mandatory Smoke Scenarios section and points at `live-qa`; `implement` skill guidance updated to match; AGENTS.md invariants (the scenario-completeness and smoke-log lines, and the Smoke-log-review workflow bullet) rewritten for the live-qa ritual; README and spec-13-era documentation mentions aligned. Vendored project copies stay in sync with the canonical `Viello/agent-skills` repo.
- **No gate coupling**: the Gatekeeper never invokes, blocks on, or reads the live-qa log. The live-qa session is the human's own discipline before approving a card.
- **Config**: `config.yaml` schema unchanged; `notify` reuses the existing Discord settings. The live-qa probe cache and log live in `.agent/` (already git-ignored runtime state).

## Testing Decisions

- Test external behavior only, at existing seams; no new seams.
- **Primary seam**: the verification loop driven with fake approval gateway and fake Discord gateway (prior art: the human-approval unit tests and the full-lifecycle integration test). Assert the card carries no scenario field, approval remains fail-closed, and no smoke log is written.
- **CLI seam for notify**: the bot-subcommand test pattern — inject a fake gateway, run the subcommand, assert exactly one posted message and clean failure paths when config or token is absent (prior art: the bot subcommand and CLI tests).
- **Domain/parser seams**: signal schema tests assert the removed key is tolerated on old files and absent on new; parser tests assert the legacy heading is inert; evidence-card and runtime-paths tests prune to their surviving behavior; prompt-builder tests assert the new invariant text replaces the old.
- The spec-contract test suite from Spec 13 that asserted scenario counts is rewritten to assert the removal (their inverse) rather than deleted wholesale.

## Out of Scope

- Any Gatekeeper↔live-qa automation (the session is human-invoked by design).
- Launching, probing, or managing the app-under-test from Runner code — that logic lives in the `live-qa` skill markdown and is already shipped.
- Changing the Circuit Breaker, retry, diagnostics, or token-budget machinery.
- Editing the already-published `live-qa` skill itself beyond nothing — it ships as authored in `Viello/agent-skills`.
- Retro-filling live-qa logs for completed Spec 13 tickets.

## Further Notes

- The live-qa log path `.agent/live-qa_log_<slug>.md` is authored solely by the skill session, keeping durable-verification authorship with the human.
- Domain vocabulary per CONTEXT.md: Runner, Worker, Ticket, Queue, Gatekeeper, Evidence Card, Presence Mode (Nearby/Away), Circuit Breaker, Gotchas, Live QA Session.
