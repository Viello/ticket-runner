# T021 — All-Mode Skill Catalog Enumeration from the Public Catalog
**Type:** wayfinder:task (HITL)
Status: completed
Completed: 2026-10-04T16:23:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T005d
Reasoning: medium

### Question

Implement the catalog enumeration that T005d explicitly deferred to `T005d-impl`:
when `--skills all` (or `ticket-runner.yaml: sandbox.skills: all`) is resolved,
ship the full skill catalog into the sandbox's `.agents/skills/` tree instead of
only the four curated skills. The source of truth is the public catalog
`https://github.com/Viello/agent-skills`, fetched over the network at scaffold
time (chart-session decision, Q2 = c), not the host's `~/.agents/skills/` nor the
Runner's vendored copy.

### Why this matters

T005d locked the `sandbox.skills: default|all` contract and wired mode resolution
through `runner/tools/scaffold_sandbox.py` and `scripts/sync_agents_md.py`, but
explicitly shipped only the contract: `all` mode flips the `## Agent skills` bullet
trim while the scaffold still copies just four skills and logs
`[scaffold] all mode: 4 skills shipped (catalog enumeration deferred to T005d-impl)`.
A user who opts into `all` expecting the catalog gets four skills and a dangling
promise — the onboarding promise ("the sandbox mirrors the real catalog") is not
met.

Note the upstream repository layout: skills live at the repository root
(`<skill>/SKILL.md`), **not** under `.agents/skills/`. The fetch must translate the
root layout into the sandbox's `.agents/skills/<skill>/SKILL.md` shape.

### Requirements

- Source resolution (Q2 = c): fetch `https://github.com/Viello/agent-skills` at
  scaffold time — the published tarball
  (`archive/refs/heads/main.tar.gz`) or `git clone --depth 1` — enumerate every
  `<skill>/SKILL.md`, and write each to
  `<target>/.agents/skills/<skill>/SKILL.md`.
- Preserve the T005c default set on fetch failure: on any network/extract error,
  warn and fall back to the four curated skills (`implement`, `code-review`,
  `diagnosing-bugs`, `handoff`) so scaffolding never hard-fails offline.
- Honor the existing `--source-skills-dir` override to bypass the network supply
  the catalog locally (required for hermetic tests and offline use).
- Remove the `catalog enumeration deferred to T005d-impl` log line; emit a count
  instead — e.g. `[scaffold] all mode: N skills shipped from Viello/agent-skills`.
- `scripts/sync_agents_md.py --skills all` continues to validate the all-mode
  bullet trim (T005d); the two concerns stay decoupled.
- Tests:
  - `all` mode ships more than the four curated skills when a fake catalog
    directory is supplied via `--source-skills-dir`.
  - Network-failure fallback ships the four curated skills and warns.
  - Existing default-mode and T005d mode-resolution tests remain green.

### Acceptance Criteria

- With the network available,
  `python -m runner.tools.scaffold_sandbox --non-interactive --force --skills all`
  writes every catalog skill under `.agents/skills/` (more than four).
- With the network unreachable (or the fetch disabled), the same command ships the
  four curated skills and prints a warning.
- `--skills all` with a local `--source-skills-dir` copies exactly that directory's
  catalog (hermetic).
- The `catalog enumeration deferred to T005d-impl` log line no longer appears.
- Existing T005d mode-resolution and sync tests remain green.

### Smoke Scenarios

**Scenario: All mode ships the full catalog**

- Setup: Network available.
- Why: Confirm `all` mode fulfills its onboarding promise.
- Steps:
  1. Run `python -m runner.tools.scaffold_sandbox --non-interactive --force --skills all`.
  2. Count directories under
     `D:\Sandbox\ticket-runner-live-target\.agents\skills\`; expect the full
     catalog (> 4).
  3. Inspect `AGENTS.md` `## Agent skills`; expect all four bullets (T005d
     all-mode trim).
- Expected: Steps 2-3 pass.

**Scenario: Offline fallback is graceful**

- Setup: Simulate a fetch failure.
- Steps:
  1. Run all-mode scaffold with the fetch forced to fail.
  2. Expect four curated skills plus a warning; no hard crash.
- Expected: Scaffold completes with the default set and a warning.

### Gotchas

- Upstream puts skills at the repository root, not `.agents/skills/` — path
  translation is required.
- The fetch is a network dependency at scaffold time; keep it skippable and
  testable through the local `--source-skills-dir` override.
- This ticket is the deferred `T005d-impl`; the name does not match the
  `T<NNN>` parser shape, hence a real ticket id.
- Do **not** regenerate the curated `AGENTS.md` bullet trim from the enumeration —
  T005d owns the trim, T021 owns the file copy. Coupling them re-opens T005d.
- Fixture/demo tickets for the driver remain T016/T017's separate decision; do not
  add them here.
