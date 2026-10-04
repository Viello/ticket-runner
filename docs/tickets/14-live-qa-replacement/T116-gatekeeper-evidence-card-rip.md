# T116 — Gatekeeper and Evidence Card consumers go silent
Status: pending
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: T115

### Requirements
- Remove every surviving consumer of scenario data in the verification path: the `EvidenceCard` value object loses its scenario field; the Gatekeeper drops the scenario sourcing chain, the empty-manual-verification warning, the commit-body scenario injection, the terminal checklist print, and smoke-log appending; `RuntimePaths` loses the smoke-log path helper; the terminal approval panel and the Discord Evidence Card embed drop their scenario checklist sections and the scenario-specific Discord field packing/truncation that exists only for that checklist. The fail-closed human-approval contract is untouched: in `"human"` mode, no commit or pass is reachable without an explicit APPROVE. Secret scrubbing on all surviving embed content remains.
- Rewrite the Spec-13 spec-contract tests that asserted scenario counts (`tests/specs/test_spec_13_verification_and_approval.py` lines ~190/226) to assert the inverse: cards and parsed tickets carry no scenario data. Extend the primary verification-loop seam (fake approval gateway + fake Discord gateway) to assert no smoke log is ever written.
- Jump-start:
  - Files to touch: `runner/domain/evidence.py` (scenario coercion ~79–101), `runner/application/gatekeeper.py` (sourcing 1191–1208, warning 1255–1264, injection 1270–1289, print 1291–1314, `_append_smoke_log` 976–1041, call 1317), `runner/domain/runtime_paths.py` (`smoke_log_path` 149–163), `runner/adapters/ui/terminal_approval.py` (rendering 110–122), `runner/adapters/discord/approval.py` (scenario embed fields 165–223).
  - Seams to work at: `tests/unit/application/test_gatekeeper_human_approval.py` (fail-closed tests must pass unmodified in spirit), `tests/integration/test_discord_e2e.py` (highest seam — full lifecycle with `FakeDiscordGateway`), `tests/unit/adapters/test_terminal_approval.py`, `test_discord_approval.py`, `test_runtime_paths.py`, `test_evidence.py`.
  - Verification: `python -m pytest` full suite green.

### Acceptance Criteria
- `EvidenceCard` carries no scenario field; terminal panel and Discord embed render without a checklist section; the scenario-only embed field packing code is gone while the surviving fields keep their 1024/25-limit handling.
- A full passing verification cycle in human mode produces no `smoke_log_*` file under `.agent/`.
- Fail-closed behavior unchanged: missing gateway, unhandled decision, or operator abort still prevent commit.
- Commit bodies no longer embed scenario checklists; single-commit-per-ticket contract (ADR 0012) otherwise unchanged.
- No `.agent/` path traversal protections are weakened while `smoke_log_path` is deleted (the traversal guard pattern must survive in `RuntimePaths` for remaining paths).

### Smoke Scenarios
**Scenario: gate cycle writes no smoke log**
- Setup: Repo with a synthetic pending ticket and a ready signal under a scratch `.agent/`; human approval mode with the terminal adapter; run the Gatekeeper verification loop to approval with `y`.
- Why: The Gatekeeper must stop authoring verification logs entirely — durable verdicts become the human's live-qa log only.
- Steps: 1. Run the verification loop to completion and approval. 2. Search `.agent/` for any `smoke_log_*` file. 3. Inspect the created commit message body.
- Expected: Exactly one commit created; no `smoke_log_*` file exists anywhere under `.agent/`; commit body has no scenario checklist section.

### Gotchas
- `runner/adapters/discord/approval.py` truncation logic (lines 180–223) is shared-shape code: remove only the scenario field loop, keep limits for evidence paths and other fields.
- Old completed tickets' `### Smoke Scenarios` must NOT break the Queue/Doctor scan even though Gatekeeper no longer parses them (guaranteed by T115's inert-parser work — verify, don't assume).
