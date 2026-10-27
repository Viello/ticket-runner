# T123 — Sanitize agent-skills Target Project and Audit Spec 16 Alignment
Status: pending
Spec: docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md
Blocked by: T120, T121, T122
Reasoning: medium

### Requirements
- Synchronize the updated `.agents/skills/implement/SKILL.md` from `D:\Projects\.agents\skills\implement\SKILL.md` to the provisioned copy in the `D:\Repos\agent-skills` Target Project (`D:\Repos\agent-skills\.agents\skills\implement\SKILL.md`, keeping its `agents/` subfolder stripped so `T101`'s baseline of 37 `openai.yaml` files remains intact).
- Sanitize `D:\Repos\agent-skills` back to a clean baseline at commit `6912328`: restore `docs/tickets/01-runner-live-test-bootstrap/T101-add-codex-interface-metadata-to-skills-lacking-it.md` and `docs/tickets/gotchas.md`, remove the untracked `docs/tickets/01-runner-live-test-bootstrap/completed/` directory and the 8 uncommitted `*/agents/openai.yaml` files from the aborted run, and remove stale `.agent/state.json`, `.agent/status.json`, `.agent/logs/T101_diagnostic.md`, `.agent/checkpoints/T101/`, `.agent/signals/`, and `docs/tickets/.queue.lock`.
- Create the Spec 16 behavioral verification suite at `tests/specs/test_spec_16_live_run_remediation.py` covering Seam 1 (Windows Gatekeeper shell quoting), Seam 2 (Antigravity per-step context occupancy, stall timer separation, UI tool forwarding, and ready-signal precedence), and Seam 3 (`PromptBuilder` guardrails and idempotent `DirectoryTicketStore.finalize_completed`).
- Audit root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`) and `docs/tickets/gotchas.md` for Spec 16 alignment, update `AGENTS.md` implementation status to reflect Spec 16, and verify markdown links and code-fence balance.
- Jump-start orientation: inspect `docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md`, `AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `docs/tickets/gotchas.md`, `tests/specs/`, and `D:\Repos\agent-skills`. Verify with `python -m pytest tests/unit tests/specs/test_spec_16_live_run_remediation.py -x`.

### Acceptance Criteria
- `tests/specs/test_spec_16_live_run_remediation.py` exists and passes alongside the full unit test suite (`python -m pytest tests/unit tests/specs/test_spec_16_live_run_remediation.py`).
- In `D:\Repos\agent-skills`, `git status --porcelain` is empty, `HEAD` is `6912328`, `T101` and `T102` are both `Status: pending` in `docs/tickets/01-runner-live-test-bootstrap/`, `*/agents/openai.yaml` count is `37`, `.agents/skills/implement/SKILL.md` matches the updated autonomous Step 4/Step 6 rules, and stale `.agent/` state/lock files are cleared.
- `AGENTS.md` implementation status is updated to include Spec 16, cross-ticket lessons from Spec 16 are logged in `docs/tickets/gotchas.md`, and zero forbidden glossary synonyms from `CONTEXT.md` appear in modified documentation.

### Gotchas
- When syncing `.agents/skills/implement/SKILL.md` into `D:\Repos\agent-skills\.agents\skills\implement\SKILL.md`, only copy `SKILL.md` (do not copy any `.agents/skills/*/agents/openai.yaml` files), preserving the 37-file pre-`T101` baseline in `D:\Repos\agent-skills`.
- Preserve `D:\Repos\agent-skills\observations\T101.md` and `T102.md` pre-flight prediction files (which are gitignored) while cleaning `.agent/` runtime artifacts.
