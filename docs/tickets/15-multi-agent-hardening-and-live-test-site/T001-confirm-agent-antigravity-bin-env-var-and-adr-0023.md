# T001 — Confirm `AGENT_ANTIGRAVITY_BIN` and Write ADR-0023
**Type:** wayfinder:grilling (HITL)
Status: completed
Completed: 2026-10-04T16:54:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

Lock the canonical env-var name and convention for the Antigravity CLI binary path
override. The chosen convention must support a future `AGENT_OPENCODE_BIN`
symmetrically without an awkward second naming scheme.

### Why this matters

`runner/application/doctor.py:225` hardcodes the `agy` binary name as a literal. This
breaks:

- Users with `agy` installed in a non-PATH location (e.g. managed via mise, asdf,
  pipx, or a custom directory).
- CI environments that install the binary to a known path and need a stable override.
- Cross-platform installations where `agy` resolves differently.

A configurable path override closes all three without changing the default behavior for
the common one (`agy` on PATH).

### Resolution (research subagent)

- **Locked name**: `AGENT_ANTIGRAVITY_BIN` (single underscore, not the originally
  proposed double-underscore).
- **Rationale**: the double-underscore delimiter has precedent **only as a
  nested-key separator** (Rails `ActiveSupport::EnvConfiguration`,
  pydantic-settings `env_nested_delimiter='__'`). Our use case is a flat
  `category:provider:field` triple, not a recursive hierarchy, so single
  underscores already disambiguate. Strongest cross-ecosystem precedent is
  `AGENT_*` family + `_BIN` suffix (Kubernetes-sigs devops-bench, image_optim,
  od-cli-scanner, open-design's `CURSOR_AGENT_BIN`).
- **Symmetry decision**: ship `AGENT_OPENCODE_BIN` in T004 alongside
  `AGENT_ANTIGRAVITY_BIN`.
- **Case-sensitivity**: case-sensitive (POSIX/Linux; matches OpenCode, Rustup,
  Cargo).
- **Resolution priority (T004's responsibility)**: env-var first, then
  `shutil.which`. If env-var is set but path is invalid or unexecutable, fail
  loud with the env-var name in the remediation message (per hermes-agent /
  zigbase precedent).
- **Notes**: Google Antigravity itself documents no `agy` binary path override;
  whatever name we adopt is original. The ADR-0023 rationale is the
  documentation, not a citation.
- **Full research file**: branch `research/agent-backend-env-var-convention`
  (commit `652b209`), file `.agents/skills/research/out/agent-backend-env-var-convention.md`.

### Requirements (now satisfied)

- ~~Decide the canonical env-var name~~ → `AGENT_ANTIGRAVITY_BIN`
- ~~Audit prior art for the double-underscore delimiter~~ → research note
  addresses all ecosystems listed in the question.
- ~~Decide whether `AGENT_OPENCODE_BIN` ships symmetrically in T004~~ → yes
- Write ADR-0023 (`docs/adr/0023-agent-backend-binary-env-var-override.md`)
  capturing:
  - The chosen env-var names.
  - Why single underscore (rejection of double).
  - How T004 will resolve the env var (priority order vs `shutil.which`).
  - Symmetry decision for `AGENT_OPENCODE_BIN`.
  - Migration path for any pre-existing users (none expected — this is additive).
- Update `runner/domain/config.py` constants if a new `BINARY_ENV_VAR_OVERRIDES` map
  is the chosen design, or document the per-provider override approach.
- Record any decisions in `CONTEXT.md` under the glossary (if a new term like "binary
  path override" is introduced).

### Acceptance Criteria

- ADR-0023 exists at `docs/adr/0023-agent-backend-binary-env-var-override.md` and
  follows the one-paragraph format defined in
  `.agents/skills/domain-modeling/ADR-FORMAT.md`.
- The ADR explicitly addresses (a) name choice, (b) single-underscore
  justification, (c) `AGENT_OPENCODE_BIN` symmetry decision, (d) resolution priority.
- The chosen env-var names (`AGENT_ANTIGRAVITY_BIN`, `AGENT_OPENCODE_BIN`) are
  referenced consistently across T003, T004, T018, and the live-test-sites.md
  (T011).
- `CONTEXT.md` glossary either references the existing term "Path Resolver" or
  introduces a new term with full definition.

### Gotchas

- The ADR must be reversible-friendly: if the convention is later abandoned, removing
  the env-var override should be a single-line change.
- Do NOT touch the `agy` binary name string in `runner/application/doctor.py:225` —
  that is T004's responsibility. T001 only locks the NAME.