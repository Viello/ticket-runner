# T020 — Scaffold Output Sanitization Engine
**Type:** wayfinder:task (HITL)
Status: pending
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: T005b, T005c, T005d
Reasoning: medium

### Question

Make every file the sandbox scaffold writes project-agnostic by routing its content
through a single sanitization engine before it lands on disk. The engine strips
project-local references that dangle or collide in a vendored target project —
primarily `(ADR NNNN)` parentheticals in `AGENTS.md` and the built-in welcome
ticket's `docs/specs/<name>.md` spec reference. Simultaneously update the root
`AGENTS.md`'s subprocess invariant to name both agent backends (OpenCode and
Antigravity CLI), drop its ADR reference, and restate `## Implementation status` to
reflect Spec 15 as in flight.

### Why this matters

The external sandbox (`D:\Sandbox\ticket-runner-live-target\`, locked by T005) is
the first surface a prospective Ticket Runner user sees. Today its curated
`AGENTS.md` carries five `(ADR NNNN)` parentheticals (`ADR 0001`, `0002`, `0004`,
`0005`, `0012`) that reference documents co-located only in the Runner source repo;
in a vendored copy they dangle, and if the host project has its own ADR series they
can actively collide. The welcome ticket ships `Spec: docs/specs/00-welcome.md`, a
path the scaffold never creates.

T005c curates *which* upstream content ships; T005d curates *how much* of
`## Agent skills` ships. Neither transforms content for cross-project safety. A
sanitization layer closes that gap, and its `file_kind` keying makes it extensible
to future scaffold output (`CONTEXT.md`, `README.md`, …) without an engine rewrite.

The current root invariant is also OpenCode-only and cites `(ADR 0001)`, which the
sandbox copy then surfaces. Antigravity is a first-class backend (T001/T002/T018);
the invariant should name both.

### Requirements

- New module `runner/tools/sanitize.py` with public surface:
  - `SanitizeRule` — a `NamedTuple` of `(file_kind: str, pattern: re.Pattern[str],
    replacement: str, rationale: str)`.
  - `SANITIZE_RULES: list[SanitizeRule]`.
  - `FILE_KINDS: tuple[str, ...]` — the seven wired kinds.
  - `apply_sanitization(text: str, file_kind: str) -> str` — pure; applies only
    rules whose `file_kind` matches; an unknown kind passes the input through
    unchanged; idempotent (`apply(apply(x)) == apply(x)`).
- Seed two rules today:
  - `agents_md`: `re.compile(r"\s*\(ADR\s*\d{4}\)")` → `""` (strip ADR
    parentheticals; the sentence-terminating period survives).
  - `welcome_ticket`: `re.compile(r"docs/specs/[\w.-]+\.md")` → a non-empty
    placeholder (e.g. `N/A (sandbox demo)`), because `runner/domain/ticket.py:68`
    requires a non-empty `spec_path` and the parser infers
    `docs/specs/<dir>.md` when `Spec:` is absent
    (`runner/adapters/markdown/parser.py:116-123`).
- Full sweep: call `apply_sanitization` at every scaffold write site across seven
  kinds — `agents_md` (`AGENTS.md`), `welcome_ticket`
  (`docs/tickets/00-welcome/T001-hello-world.md`), `ticket_runner_yaml`
  (`ticket-runner.yaml`), `gitignore` (`.gitignore`), `skill_md`
  (`.agents/skills/*/SKILL.md`), `python_src` (`src/sample_app/__init__.py`),
  `python_test` (`tests/test_smoke.py`). Five are no-op rules today; the wiring is
  the point.
- Plumb `scripts/sync_agents_md.py`:
  - Sanitize `upstream_curated` (`agents_md`) **before** the in-sync comparison,
    so a sanitized sandbox copy does not read as permanent drift.
  - Sanitize the formatted output before writing under `--write`/`--apply`.
- Root `AGENTS.md` edits (user approved during the chart session):
  - Replace Invariant bullet #1 with a single abstracted, ADR-free bullet naming
    both backends:
    `- Agent backends (OpenCode, Antigravity CLI) are invoked as subprocesses, never daemons, each with its own structured streaming envelope (OpenCode: \`opencode run --format json --session <id> --auto "<prompt>"\`; Antigravity: \`agy -p "<prompt>" --output-format stream-json [--conversation <uuid>]\`). Resumption uses the session id each backend emits (\`ses_…\` for OpenCode, \`conversation_id\` UUID for Antigravity).`
  - Replace the `## Implementation status` body with:
    `Specs 01–14 are implemented and tested; Spec 15 (Multi-Agent Hardening & Live-Test Site) is in flight under docs/tickets/15-multi-agent-hardening-and-live-test-site/.`
  - Do **not** strip `(ADR NNNN)` from the root file — root owns its ADRs; only the
    sandbox copy is sanitized.
- Tests:
  - New `tests/unit/tools/test_sanitize.py`: both rules; file-kind dispatch
    isolation (an `agents_md` rule does not fire for `welcome_ticket`, and vice
    versa); idempotence; unknown-kind passthrough; `FILE_KINDS` registry.
  - One scaffold-level test asserting the generated `AGENTS.md` contains no `(ADR`
    and the welcome ticket carries a non-empty `Spec:` with no
    `docs/specs/<name>.md`.
  - Existing scaffold/sync tests remain green.
- Two-commit landing (chart-session order):
  1. `chore(tools): add scaffold sanitize engine and multibackend invariant` —
     module, tests, plumbing, root `AGENTS.md` edits.
  2. `chore(sandbox): re-derive sandbox output through sanitize engine` —
     regenerate the external sandbox via
     `python -m runner.tools.scaffold_sandbox --non-interactive --force`
     (the sandbox is its own repo and re-commits itself).

### Acceptance Criteria

- `runner/tools/sanitize.py` exists with the public surface above;
  `apply_sanitization` is pure and idempotent.
- `pytest tests/unit/tools/test_sanitize.py -v` passes.
- `python -m runner.tools.scaffold_sandbox --non-interactive --force` produces:
  - `AGENTS.md` containing zero `(ADR NNNN)` parentheticals.
  - `docs/tickets/00-welcome/T001-hello-world.md` with a non-empty `Spec:` value
    and zero `docs/specs/<name>.md` references.
- `python scripts/sync_agents_md.py --apply` exits 0 against the regenerated
  sandbox.
- Root `AGENTS.md` Invariant #1 names both backends and contains no ADR reference;
  `## Implementation status` reflects Spec 15 in flight.
- Existing scaffold and sync test suites remain green.

### Smoke Scenarios

**Scenario: Sandbox output is cross-project clean**

- Setup: Root `AGENTS.md` edited; engine and plumbing merged.
- Why: Confirm the vendor surface carries no dangling project-local references.
- Steps:
  1. Run `python -m runner.tools.scaffold_sandbox --non-interactive --force`.
  2. Inspect `D:\Sandbox\ticket-runner-live-target\AGENTS.md`; assert no `(ADR`.
  3. Inspect
     `D:\Sandbox\ticket-runner-live-target\docs\tickets\00-welcome\T001-hello-world.md`;
     assert no `docs/specs/<name>.md` and a non-empty `Spec:`.
  4. Run `python scripts/sync_agents_md.py --apply`; assert exit 0.
- Expected: Steps 2-4 all pass; the sandbox re-derives clean and stays in sync.

**Scenario: Engine is idempotent**

- Setup: None.
- Why: Confirm sanitization is safe to re-run (scaffold and sync both apply it).
- Steps:
  1. Run `pytest tests/unit/tools/test_sanitize.py -v`.
- Expected: The idempotence and dispatch tests pass.

### Gotchas

- `Spec:` must remain non-empty (`runner/domain/ticket.py:68`); the welcome-ticket
  rule replaces the path rather than deleting the line.
- The `welcome_ticket` kind is not synced by `scripts/sync_agents_md.py` (that
  script handles `AGENTS.md` only) — welcome-ticket sync would be a separate
  ticket.
- Root `AGENTS.md` keeps its `(ADR NNNN)` references on purpose; only the sandbox
  copy is sanitized. `sync_agents_md` must sanitize `upstream_curated` before
  comparing, or the sanitized copy reads as drift forever.
- The `agents_md` pattern `\s*\(ADR\s*\d{4}\)` matches four-digit ADR numbers only;
  audit upstream prose for false positives whenever an invariant is added.
- T021 (all-mode skill enumeration) is orthogonal; do not couple the sanitization
  engine to the catalog enumeration.
