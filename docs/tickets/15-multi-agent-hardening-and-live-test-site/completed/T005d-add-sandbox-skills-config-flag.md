# T005d — Add `sandbox.skills` Config Flag for Skill Catalog Mode
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-04T23:10:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T005c (the AGENTS.md curated-subset lock; resolved)
Blocks: T005b follow-up (scaffold_sandbox reads the flag), T006 (scaffold output respects the flag)
Reasoning: medium

### Question

T005c locks the curated `AGENTS.md` subset with two mode-conditional behaviors
for `## Agent skills` bullet trim. Today, `runner.tools.scaffold_sandbox` only
ships the 4-skill curated set; users who want a 1:1 demo of the full skill
catalog cannot get it. This ticket locks the YAML key, the CLI surface, and the
mode resolution so `scaffold_sandbox` and `scripts/sync_agents_md.py` can
honor both modes end-to-end.

### Why this matters

- A first-time Ticket Runner user running `docs/tickets/00-welcome/T001-hello-world.md`
  exercises `/implement`, `/code-review`, `/diagnosing-bugs`, `/handoff` — those
  four ship in the curated default. They never touch `/grill-me`,
  `/to-tickets`, `/security-review`, `/claude-handoff`, etc. Default mode is the
  right onboarding shape.
- A power user evaluating Ticket Runner against the full skills catalog wants
  every skill shipped so they can exercise every command against a real
  sandbox. Without the flag, they have to manually copy each `SKILL.md` into
  `.agents/skills/` post-scaffold.
- The sync detector must apply the same bullet-trim mode as the scaffold, or
  drift detection will flag the sandbox as out-of-sync when the user opted into
  the all-skills mode.

### Requirements (proposed from grilling session — pending confirmation)

- New YAML key path: `ticket-runner.yaml: sandbox.skills: default|all`. Default
  value: `default` (matches current T005 layout). Allowed values: `"default"`,
  `"all"`. Future values (e.g. `"minimal"`) require an ADR.
- `runner.tools.scaffold_sandbox` reads the flag in this order:
  1. CLI `--skills {default,all}` flag (if passed, override).
  2. `ticket-runner.yaml: sandbox.skills` (read after writing the YAML, since
     scaffold is the canonical writer — but the flag value defaults to
     `default` if the file is absent or the key is missing).
  3. Hardcoded fallback: `default`.
- Skill-source resolution:
  - `default`: ship the 4 curated skills (`implement`, `code-review`,
    `diagnosing-bugs`, `handoff`) from `D:\Projects\.agents\skills/`. This
    matches T005's locked tree.
  - `all`: enumerate every `*/SKILL.md` under the user's global catalog
    (`~/.agents/skills/` per AGENTS.md `## Agent skills` #1) and ship each
    one. Source path is configurable via a new
    `runner.tools.scaffold_sandbox` `--source-skills-dir` flag (already exists
    per T005b's `source_skills_dir` parameter; just plumbed through to the
    catalog enumeration).
- `scripts/sync_agents_md.py` accepts a `--skills {default,all}` CLI flag
  (already implemented in this session's T005c commit) and applies the matching
  bullet-trim mode when computing the curated subset for diff/write.
- `ticket-runner.yaml` written by `scaffold_sandbox` includes the
  `sandbox.skills: default` line in the `default` mode scaffold, and
  `sandbox.skills: all` in the `all` mode scaffold, so the file is
  self-documenting.
- The trivial welcome ticket `T001-hello-world.md` is unaffected — it only
  exercises skills in the curated default set, so it works under either mode.

### Acceptance Criteria

- `ticket-runner.yaml: sandbox.skills: default` → scaffold_sandbox ships 4
  skills and AGENTS.md `## Agent skills` has 2 bullets.
- `ticket-runner.yaml: sandbox.skills: all` → scaffold_sandbox ships the full
  catalog and AGENTS.md `## Agent skills` has 4 bullets.
- `python scripts/sync_agents_md.py --skills all` matches a sandbox scaffolded
  in `all` mode (exit 0); `--skills default` matches a sandbox scaffolded in
  `default` mode.
- A cross-mode scaffold is detected as drift (the `sync` script exits 1) when
  the user's YAML says `all` and the script is run with `--skills default`
  (or vice versa).
- The flag does NOT affect any other section of AGENTS.md (`## Invariants`,
  `## Environment`) — those are content-controlled by T005c's bullet-trim
  tables only.
- Tests cover all four cross-mode combinations (2 scaffold modes × 2 sync
  modes → 4 cases, including drift detection).

### Smoke Scenarios

**Scenario: Default-mode scaffold + default-mode sync → in sync**

- Setup: Scaffold a fresh sandbox with default mode.
- Steps:
  1. Run `python -m runner.tools.scaffold_sandbox --non-interactive --force`.
  2. Run `python scripts/sync_agents_md.py` (no `--skills` flag).
- Expected: Both succeed; sync exits 0.

**Scenario: All-mode scaffold + all-mode sync → in sync**

- Setup: Scaffold a fresh sandbox with `--skills all`.
- Steps:
  1. Run
     `python -m runner.tools.scaffold_sandbox --non-interactive --force --skills all`.
  2. Run `python scripts/sync_agents_md.py --skills all`.
- Expected: Both succeed; sync exits 0.

**Scenario: Cross-mode drift detected**

- Setup: Scaffold with default mode.
- Steps:
  1. Run `python -m runner.tools.scaffold_sandbox --non-interactive --force`.
  2. Run `python scripts/sync_agents_md.py --skills all` (mismatched mode).
- Expected: Sync exits 1 with drift output listing the `## Agent skills`
  bullet count mismatch.

### Gotchas

- The CLI flag and the YAML key are both named `sandbox.skills` (CLI:
  `--skills`). No `sandbox_skills` underscore variant — the YAML key uses
  dotted notation per ticket-runner.yaml conventions.
- `scaffold_sandbox` writes `ticket-runner.yaml` BEFORE writing `AGENTS.md`
  (per current order in the implementation), so re-ordering is required if
  the YAML is to be read back during the same scaffold pass. Alternative:
  have the scaffold decide the mode upfront (CLI flag or default) and write
  the YAML with the same mode it used for AGENTS.md. The latter is simpler —
  T005d's implementation should pick whichever is least invasive.
- A user who edits `ticket-runner.yaml` post-scaffold to flip the mode will
  NOT have their AGENTS.md automatically rewritten — the sync script must be
  re-run with `--write --skills {all}` to apply. Document this in the welcome
  preamble or a follow-up ticket.
- The `all` mode's skill catalog enumeration assumes `~/.agents/skills/` is
  the user's global catalog. If the user has a different layout, they pass
  `--source-skills-dir` explicitly. This matches AGENTS.md `## Agent skills`
  #1 framing of "the user's global skill catalog".
- This ticket does NOT implement the all-mode skill enumeration — it only
  locks the contract. Implementation goes in a follow-up task ticket (e.g.
  T005d-impl) once the contract is approved.

### Resolution (grilling session, 2026-10-04)

Rounds answered Q1-Q6:

- **Q1 = a — YAML schema placement.** New nested `sandbox:` top-level key with
  `sandbox.skills: default|all` beneath it. Matches the existing namespace
  convention (`worker:`, `verification:`, `tokens:`, `presence:`, `discord:`,
  `lifecycle:`, `git:`, `ui:`) and scopes the knob to scaffold/sync time only.
- **Q2 = a — Mode-resolution priority in both binaries.** `--skills` CLI (when
  provided) > `ticket-runner.yaml: sandbox.skills` (when the file exists and
  holds a valid value) > hardcoded `"default"`. Implemented as
  `_resolve_skills_mode` in `runner/tools/scaffold_sandbox.py` and reused by
  `scripts/sync_agents_md.py`.
- **Q3 = a — Self-documenting YAML.** Scaffold emits `sandbox.skills:
  "<mode>"` matching the mode used. The `TICKET_RUNNER_YAML` constant became
  `TICKET_RUNNER_YAML_TEMPLATE` plus a `build_ticket_runner_yaml(skills_mode)`
  builder.
- **Q4 = c — Contract-only scope with an explicit log line.** The `all` mode
  flips the `## Agent skills` bullet trim today; the `~/.agents/skills/` catalog
  enumeration is deferred to a follow-up (`T005d-impl`, not filed here). To keep
  the gap honest, scaffold prints
  `[scaffold] all mode: 4 skills shipped (catalog enumeration deferred to T005d-impl)`
  when invoked in `all` mode.
- **Q5 = b — YAML footnote for the post-scaffold flip.** The `sandbox.skills`
  line carries the comment
  `# Flip + re-run sync_agents_md.py --write --skills <default|all> to apply.`
  The user discovers the re-apply procedure at the moment they edit the knob.
- **Q6 = b — `--apply` opt-in flag.** `scripts/sync_agents_md.py` gains
  `--apply`: the script resolves the mode (CLI > YAML > `"default"`), and
  auto-rewrites `AGENTS.md` when the resolved mode's curated subset disagrees
  with the sandbox copy. Without `--apply`, the script stays in pure-detect mode.
  `--apply` and `--write` are independent; `--write` always rewrites.

**YAML schema (sandbox template):**

```yaml
worker:
  provider: "antigravity"
  execution_skill: ".agents/skills/implement/SKILL.md"

sandbox:
  # Flip + re-run sync_agents_md.py --write --skills <default|all> to apply.
  skills: "default"
```

**Mode-resolution diagram (both binaries):**

```
--skills CLI flag  ──── provided ───▶ use it
       │ absent
       ▼
ticket-runner.yaml: sandbox.skills ── valid ──▶ use it
       │ absent/invalid
       ▼
"default" (hardcoded fallback)
```

**Implementation alignment:**

- `runner/tools/scaffold_sandbox.py` — `TICKET_RUNNER_YAML_TEMPLATE`,
  `build_ticket_runner_yaml`, `_read_yaml_sandbox_skills`, `_resolve_skills_mode`;
  `scaffold()` writes the template and prints the `all`-mode deferred line.
- `scripts/sync_agents_md.py` — mode resolution via `_resolve_skills_mode`;
  new `--apply` flag; `--write` semantics unchanged.
- Tests: YAML round-trip + reader edge cases + `all`-mode log line in
  `tests/unit/tools/test_scaffold_sandbox.py`; the 4-case cross-mode matrix
  (default/all scaffold × default/all sync), YAML-driven resolution when the
  CLI is absent, and `--apply` rewrite/no-op semantics in
  `tests/unit/scripts/test_sync_agents_md.py`.

`worker.execution_skill` is unaffected by `sandbox.skills` — the flag governs
the scaffold-time and sync-time bullet trim only, never runtime worker wiring.

The welcome ticket `T001-hello-world.md` exercises only curated-default skills,
so it behaves identically under either mode.