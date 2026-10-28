# T010a — Complete the `init` Scaffold (Runnable Artifacts)
**Type:** wayfinder:task (HITL)
Status: completed
Completed: 2026-10-08T23:15:07Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T010
Reasoning: medium

### Question

`ticket-runner init` (used to scaffold the Pure Empty starter) omits the runnable
artifact set that T009/T010 expected to watch appear. Close the gap between
`ProjectScaffolder.scaffold` and the comprehensive `runner.tools.scaffold_sandbox`
output.

### Why this matters

T009 chose **Pure Empty** so the user could run `ticket-runner init` and watch every
artifact scaffold against a fresh slate. Live-QA Scenario B failed because the
scaffold is incomplete — the starter has no runnable app, no welcome ticket, no
AGENTS.md, and no `.agent/logs/` or `.agent/evidence/` runtime dirs.

### Context

Live-QA Scenario B failed (`.agent/live-qa_log_T010.md`). Red-capable loop:
`init --project-dir <pure-empty> --non-interactive --no-skills` left the target
without `AGENTS.md`, `src/sample_app/__init__.py`, `tests/test_smoke.py`,
`docs/tickets/00-welcome/T001-hello-world.md`, `.agent/logs/`, `.agent/evidence/`,
and with a `.gitignore` missing `docs/tickets/.queue.lock`.

Root cause: `run_init` (`ticket_runner.py:973-979`) calls the lightweight
`ProjectScaffolder` (`runner/adapters/cli/scaffolder.py`), whose
`REQUIRED_DIRECTORIES` omitted `logs`/`evidence` and which had no code paths for the
runnable artifacts. `runner/tools/scaffold_sandbox.py` (the comprehensive tool) is
never invoked by `init`.

### In scope (H1 + H3)

- `ProjectScaffolder.scaffold` emits `AGENTS.md`, the welcome ticket,
  `src/sample_app/__init__.py`, and `tests/test_smoke.py`, and creates
  `.agent/logs/` + `.agent/evidence/` — reusing the shared content constants and the
  new `build_agents_md_content` helper from `runner.tools.scaffold_sandbox`.
- `.gitignore` fresh-write uses `scaffold_sandbox.GITIGNORE_CONTENT` (now includes
  `docs/tickets/.queue.lock`); the append branch for an existing `.gitignore` is
  unchanged.
- All artifact writes are idempotent (created only when missing).

### Out of scope (kept as by-design init semantics)

- `worker.provider` stays heuristic (`opencode` default).
- Skills remain full-catalog via the injected `SkillsClient` (not the 4 curated).
- `init` does NOT author a commit (honors T009: "Scaffold output is never committed").

### Acceptance Criteria

- The red loop goes green: after `init --non-interactive --no-skills` on a Pure Empty
  target, `AGENTS.md`, `src/sample_app/__init__.py`, `tests/test_smoke.py`,
  `docs/tickets/00-welcome/T001-hello-world.md`, `.agent/logs/`, `.agent/evidence/`
  all exist, and `.gitignore` contains `docs/tickets/.queue.lock`. ✓
- Existing scaffolder tests stay green. ✓
- Full suite green (`1889 passed, 3 skipped`). ✓

### Gotchas

- `ProjectScaffolder`'s `ticket-runner.yaml` output is pinned by exact-equality tests
  (`test_cli_scaffolder.py`), so `init` was upgraded in place rather than delegating
  to `scaffold_sandbox.scaffold` (which hardcodes the sandbox name/provider and
  git-commits). Recorded in `docs/tickets/gotchas.md`.
