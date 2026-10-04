# T005c — Lock the Curated `AGENTS.md` Subset and Preamble
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-04T22:35:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Blocks: T005b (already implemented; placeholder values now aligned), T006
Reasoning: medium

### Question

T005 locks the sandbox's `AGENTS.md` as a curated subset of
`D:\Projects/AGENTS.md` plus a 5-line orientation preamble. This ticket enumerates
exactly:

1. Which sections of `D:\Projects/AGENTS.md` ship in the sandbox copy.
2. The exact text of the 5-line preamble.
3. The sync-stamp comment format that `scripts/sync_agents_md.py` rewrites on each
   dry-run / write.

### Why this matters

T005's lock is structural (shape and policy); T005c's lock is content (the actual
markdown). Without T005c, `runner.tools.scaffold_sandbox` (T005b) has no source of
truth to copy from and `scripts/sync_agents_md.py` has no subset definition to
diff against. T005c is the leaf decision T005b and T099 both depend on.

### Resolution

**File structure (top-to-bottom order in `D:\Sandbox\ticket-runner-live-target\AGENTS.md`):**

```
<5-line preamble>
<blank line>
<!-- mirrored from D:\Projects/AGENTS.md on YYYY-MM-DD -->
<blank line>
## Invariants (16 bullets, verbatim)
<blank line>
## Environment (1 bullet: Windows/PowerShell + Git for Windows' sh)
<blank line>
## Agent skills (mode-conditional — see below)
```

**Preamble — exact 5 lines** (no top-level heading inside the preamble; the file
opens with "Welcome"):

```
Welcome to your Ticket Runner sandbox — a runnable demo target at `D:\Sandbox\ticket-runner-live-target\`.
First stop: run `ticket-runner --project-dir . doctor` to confirm the sandbox is wired.
Tickets live in `docs/tickets/00-welcome/`.
The scaffold entry point is `python -m runner.tools.scaffold_sandbox`.
Reset with `--force` to wipe and regenerate this tree from the upstream layout lock (T005).
```

**Sync stamp** (written by `scripts/sync_agents_md.py` on every dry-run / write):

```
<!-- mirrored from D:\Projects/AGENTS.md on YYYY-MM-DD -->
```

Date only — no time, no commit SHA. Regex anchor for the parser is
`<!--\s*mirrored from .*? on (\d{4}-\d{2}-\d{2})\s*-->` (already implemented in
`runner/tools/scaffold_sandbox.py:29-31`).

**Section-level rubric** (used by `extract_curated_subset` and by
`sync_agents_md.py`'s drift check):

| Source section | Default mode (`sandbox.skills: default`) | `sandbox.skills: all` (T005d) |
|---|---|---|
| Opening paragraph under `# AGENTS.md` | EXCLUDED (replaced by preamble) | EXCLUDED |
| `## Implementation status` | EXCLUDED — D:\Projects spec-completion state | EXCLUDED |
| `## Read before designing` | EXCLUDED — references Runner-developer docs absent in sandbox | EXCLUDED |
| `## Invariants` (16 bullets) | INCLUDED verbatim | INCLUDED verbatim |
| `## Environment` | INCLUDED with bullet-level trim (1 of 4 bullets survives) | INCLUDED with bullet-level trim |
| `## Development workflow` (4 rungs) | EXCLUDED — points at `/grill-me`, `/to-spec`, `/implement`, `/live-qa` which are D:\Projects scaffolding skills | EXCLUDED |
| `## Agent skills` | INCLUDED with bullet-level trim (2 of 4 bullets survive) | INCLUDED verbatim (all 4 bullets) |

**Bullet-level trim in `## Environment`** (4 source bullets → 1 survives):

| Bullet | Default mode | Rationale |
|---|---|---|
| #1 "Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh." | KEEP | Sandbox IS a Windows tree; T005 confirms the pre-push hook is installed |
| #2 "Dependencies: `discord.py`, `rich`, `pyyaml`, `pytest` (see `requirements.txt`). Discord token comes from the `DISCORD_BOT_TOKEN` env var — `config.yaml` stores only the var name, never the token." | DROP | Sandbox uses `ticket-runner.yaml`, not `requirements.txt` or `config.yaml`. Discord-token config is runner-developer-only |
| #3 "Discord and terminal-UI adapters are implemented under `runner/adapters/discord/` and `runner/adapters/ui/`." | DROP | `runner/adapters/...` are Runner repo paths, absent in sandbox |
| #4 "Pre-push hook guardrail is installed via `runner/adapters/git/pre_push_hook.py` reading `scripts/pre-push.sh`." | DROP | Runner-internal implementation detail; T005 captures the *outcome* (pre-push installed via `PrePushHookInstaller`) at the layout level |

**Bullet-level trim in `## Agent skills`** (4 source bullets → 2 survive in
default mode, all 4 in `all` mode):

| Bullet | Default mode | `sandbox.skills: all` | Rationale (default mode) |
|---|---|---|---|
| #1 "`.agents/skills/` vendors the user's global skill catalog; `handoff`, `claude-handoff`, `to-tickets` have project-specific edits. Don't bulk-reformat, and don't overwrite local copies with the global ones." | DROP | KEEP | References `claude-handoff` and `to-tickets` which the default sandbox does not ship |
| #2 "`.agents/skills/handoff/SKILL.md` is load-bearing (the Runner's handoff protocol calls it by path) — don't move or rename it." | KEEP | KEEP | `handoff` is in the default shipped set |
| #3 "`.agents/skills/implement/SKILL.md` defines the default worker implementation discipline (`worker.execution_skill`)." | KEEP | KEEP | `implement` is in the default shipped set; `worker.execution_skill` binding is exact |
| #4 "`.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline (ADR 0013)." | DROP | KEEP | `security-review` is not in the default shipped set; ships in `all` mode |

**Implementation alignment with T005b** — `runner/tools/scaffold_sandbox.py`
already implements `extract_curated_subset`, `format_sandbox_agents_md`, and
`parse_sandbox_agents_md` against a placeholder `INCLUDED_HEADINGS` and
`DEFAULT_PREAMBLE`. This resolution closes the gap:

- `INCLUDED_HEADINGS` becomes `("## Invariants", "## Environment", "## Agent skills")`
  (drops `## Development workflow`, adds `## Environment`).
- `DEFAULT_PREAMBLE` becomes the 5-line "Welcome..." block above (drops the
  `# Ticket Runner Onboarding Sandbox` heading).
- `extract_curated_subset` is extended to apply the bullet-level trim tables
  above. The `all` mode is plumbed through a `skills_mode: Literal["default", "all"]`
  parameter (default `"default"`); T005d's `--skills` CLI flag and
  `ticket-runner.yaml: sandbox.skills` reader wire the mode into the call site.
- The fallback curated-subset literal in the `else` branch (used when no upstream
  `AGENTS.md` is found) is updated to match the default-mode trim.

### Requirements

- T005c's resolution comment captures the full preamble text, the
  included/excluded section list, the bullet-trim tables, and the sync stamp
  format. ✓ (above)
- `D:\Sandbox\ticket-runner-live-target\AGENTS.md` (after T006 lands) is byte-
  identical to the curated-subset definition plus the preamble and stamp (modulo
  the sync-stamp date).
- `runner/tools/scaffold_sandbox.py` implements the diff against the locked
  subset. ✓ (this commit)
- T005b and T006 may proceed.

### Acceptance Criteria

- T005c's resolution comment captures the full preamble text, the
  included/excluded section list, and the sync stamp format. ✓
- `D:\Sandbox\ticket-runner-live-target\AGENTS.md` (after T006 lands) is byte-
  identical to the curated-subset definition plus the preamble and stamp.
- `scripts/sync_agents_md.py` (T005b) implements the diff against the locked
  subset. ✓
- T005b and T006 may proceed.

### Smoke Scenarios

**Scenario: Curated subset is internally self-consistent**

- Setup: T005c has resolved.
- Why: Verify the locked subset matches what T006 scaffolds.
- Steps:
  1. Run T005b's scaffold_sandbox to create the sandbox.
  2. Open `D:\Sandbox\ticket-runner-live-target\AGENTS.md`.
  3. Compare it byte-for-byte against T005c's locked resolution.
- Expected: Step 3 confirms identity (modulo the sync-stamp date).

**Scenario: Bullet-trimmed sections match the rubric tables**

- Setup: T005c has resolved.
- Why: Verify the implementation in `runner/tools/scaffold_sandbox.py` honors
  the per-bullet keep/drop rules for `## Environment` and `## Agent skills`.
- Steps:
  1. Run `pytest tests/unit/tools/test_scaffold_sandbox.py -v`.
  2. Confirm `test_extract_curated_subset` and `test_scaffold_happy_path` pass
     with the new `INCLUDED_HEADINGS`, `DEFAULT_PREAMBLE`, and bullet trim.
- Expected: All tests pass.

### Gotchas

- Sections of `D:\Projects/AGENTS.md` are matched by their canonical heading
  text (e.g. `## Token budget`), not by line numbers — heading text is more
  resilient to upstream edits.
- The preamble lives **above** the sync stamp and **above** the curated content;
  the sync stamp lives **above** the curated content but **below** the preamble.
  This three-layer structure (preamble → stamp → content) keeps the "what is
  this" / "when was it synced" / "the actual invariants" separation clean.
- The excluded-section rationale must be reviewable later — when upstream
  `D:\Projects/AGENTS.md` changes (e.g. someone adds a new "Discord Bot Setup"
  section), T005c's resolution becomes the rubric for deciding whether the new
  section ships in the sandbox.
- The bullet-trim tables are the rubric for `## Environment` and `## Agent skills`
  specifically; if upstream adds a new bullet to either section, T005c's table
  decides whether it ships. The `all` mode (T005d) flips Agent skills bullets #1
  and #4 to keep.
- `INCLUDED_HEADINGS` no longer contains `## Development workflow`. T005b's
  existing implementation included it as a placeholder; this commit aligns the
  implementation with T005c's resolution.