# T118 — Agent skill catalog re-targeted: smoke-fail, to-tickets, implement
Status: pending
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: T116

### Requirements
- **`smoke-fail`**: re-target the triage skill from the old smoke log to the live-qa log. Durable-source intake reads `[failed]` entries (and their `Observed:` lines) from `.agent/live-qa_log_<slug>.md`, locating by scenario title or session context; regression-ticket drafting references the originating live-qa session instead of a ticket scenario section; the squash/new-commit paths and `/diagnosing-bugs` core stay. Keep the skill name `smoke-fail` (user's established trigger word) — update its description wording so it fires on live-qa failures.
- **`to-tickets`**: remove the mandatory "every ticket defines at least one human-verifiable smoke scenario" rule, the Step-4 scenario-drafting instructions, the `### Smoke Scenarios` block from the ticket-runner template, and the trailing invariant comment; replace with a one-line pointer that human verification happens post-green via `/live-qa`.
- **`implement`**: update any scenario-authoring or `manual_verification` self-report guidance to the live-qa discipline (Worker drafts no scenarios; readiness = green checks + reviews).
- **Vendor sync**: canonical copies live in the `Viello/agent-skills` catalog (local clone at `D:\agent-skills`) — commit and push catalog changes there. Vendored copies under `.agents/skills/` must match, with ONE exception: `to-tickets` carries project-specific queue edits that must not be clobbered by the catalog version — edit the project copy directly and port only the scenario-removal changes to the catalog side, keeping the Ticket Runner queue sections project-canonical.
- Jump-start:
  - Files to touch: `.agents/skills/smoke-fail/SKILL.md`, `.agents/skills/to-tickets/SKILL.md`, `.agents/skills/implement/SKILL.md` (+ their `D:\agent-skills` mirrors as described).
  - Anchor: the shipped `live-qa` skill (`.agents/skills/live-qa/SKILL.md`) defines the exact log entry format `### <scenario title> — [verified|failed|skipped] <timestamp>` + `- Observed:` — `smoke-fail`'s parser instructions must match it verbatim.
  - Process: **load and apply `/writing-for-agents`** — these are skill bodies; prune negations into positive instructions, keep completion criteria sharp, no duplicated rules between `live-qa` and `smoke-fail` (single source of truth for the log format lives in `live-qa`).
  - Verification: `Select-String -Path .agents\skills\*\SKILL.md -Pattern "Smoke Scenarios|manual_verification|smoke_log_"` returns no prescriptive hits (historical or renamed references only).

### Acceptance Criteria
- `smoke-fail` intake resolves a failed entry from the live-qa log format and never mentions `smoke_log_<spec-slug>`.
- `to-tickets` template publishes tickets with no Smoke Scenarios section and no rule requiring one; the spec-closing alignment ticket rule is untouched.
- `implement` guidance contains no scenario authoring or manual_verification self-report steps.
- Catalog (`Viello/agent-skills`) and vendored copies are identical for `smoke-fail` and `implement`; `to-tickets` differs only in its project-specific queue sections, both updated for scenario removal.

### Smoke Scenarios
**Scenario: triage a synthetic live-qa failure**
- Setup: Repo root; craft `.agent/live-qa_log_demo-slug.md` containing one `[failed]` entry with an `Observed:` line and an adjacent `[verified]` entry.
- Why: The renamed log contract is only real if the recovery skill reads it — this checks the intake seam end to end.
- Steps: 1. Invoke `/smoke-fail`, pointing it at the failed entry. 2. Let it take the squash-or-new-commit probe path with no actual fix (abort before any code change; answer the operator prompts to reach the draft stage only).
- Expected: `smoke-fail` extracts scenario title, Setup context, and Observed words verbatim from the live-qa log without asking the operator to retype them; its draft references the live-qa session as originating context.

### Gotchas
- Do NOT bulk-reformat vendored skills; `handoff` and `claude-handoff` are untouched by this ticket entirely.
- The catalog repo is public — no secrets or absolute personal paths in the skill text (`D:\agent-skills` references stay project-side, never in catalog copies).
