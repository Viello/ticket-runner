# T005c — Lock the Curated `AGENTS.md` Subset and Preamble
**Type:** wayfinder:grilling (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
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

### Requirements

After T005c closes, the resolution must enumerate:

- **Preamble** — exact 5-line block that appears before any curated content. Lifts
  together: a 1-line description of what `D:\Sandbox\ticket-runner-live-target\`
  is, a 1-line "what to do first" pointer to the doctor command, and 3 lines of
  helpful operator pointers (where tickets live, where the scaffold entry point
  lives, how to reset).
- **Included sections** — section-by-section list of which sections of
  `D:\Projects/AGENTS.md` are copied verbatim into the sandbox copy, with the
  canonical heading text used as the matching key. Each inclusion cites the
  rationale (e.g. "Invariant §18: invariant applies to every Target Project,
  including a sandbox").
- **Excluded sections** — section-by-section list of which sections of
  `D:\Projects/AGENTS.md` are NOT copied, with the rationale (e.g. "Environment:
  Supabase/MCP — sandbox is not connected to any Supabase project"; "Tailwind
  CDN config — sandbox ships no UI").
- **Sync stamp format** — the exact comment line that
  `scripts/sync_agents_md.py` writes at the top of the curated-subset section
  when it runs. Suggested:
  `<!-- mirrored from D:\Projects/AGENTS.md on YYYY-MM-DD -->` (date only, no
  time, no commit SHA).

### Acceptance Criteria

- T005c's resolution comment captures the full preamble text, the
  included/excluded section list, and the sync stamp format.
- `D:\Sandbox\ticket-runner-live-target\AGENTS.md` (after T006 lands) is byte-
  identical to the curated-subset definition plus the preamble and stamp.
- `scripts/sync_agents_md.py` (T005b) implements the diff against the locked
  subset.
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