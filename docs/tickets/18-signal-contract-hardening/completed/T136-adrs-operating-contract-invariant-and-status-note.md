# T136: ADRs, Operating-Contract Invariant, Gotcha, and Status Note

**Status:** done (reviewed; recorded ADR 0024 and 0025, amended ADR 0017, updated AGENTS.md invariant, added gotcha, updated STATUS.md with pending catalog publish step)
**Labels:** ready-for-agent
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** Close Spec 18 by recording its binding decisions and carrying the ownership rule into the operating contract. ADR 0024 records domain Signal-schema ownership and the three contract-check consumers; ADR 0025 records malformed-Signal retention, the one-shot self-correctable exemption, and the accepted residue. ADR 0017 is amended to point at the exemption. `AGENTS.md` gains one Signal-schema-ownership invariant, `docs/tickets/gotchas.md` records the incident lesson, and `STATUS.md` records completion plus catalog publishing as an explicit pending operator step.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `docs/adr/0024-signal-schema-ownership-and-contract-checks.md` (new)
  - `docs/adr/0025-malformed-signal-retention-and-retry.md` (new)
  - `docs/adr/0017-invalid-signal-consumes-verification-attempt.md`
  - `AGENTS.md` (`## Invariants`)
  - `docs/tickets/gotchas.md`
  - `STATUS.md`
- **Seams:** Documentation only. The `## Invariants` heading and its bullet prefix must stay intact for `prompt_builder.extract_invariants`, `runner/tools/scaffold_sandbox.py`, and `scripts/sync_agents_md.py`.
- **Existing-code anchors:** The existing one-paragraph ADR format (for example `docs/adr/0023-wayfinder-ticket-type-label-convention.md`); the chronological `Problem:` / `Solution:` gotcha format; the current `STATUS.md` structure.
- **Verify:** `py -3 -m pytest -q`

**Blocked by:** T130, T131, T132, T133, T134, T135

- [x] ADR 0024 records that the domain owns the Signal field inventory, the prompt renders it, the execution skill defers to it, and contract checks run at the Doctor pre-flight, skills publish gate, and repository test.
- [x] ADR 0025 records archive-before-consume, diagnostic-on-every-escalation, the one-shot self-correctable exemption, the `SIGNAL_FORMAT` versus `PROTOCOL` split, and the three accepted residues: a format error after an operator RETRY prompts, the processor-side malformed-question catch is a best-effort race guard that consumes no attempt, and a hand-repaired Target Project is overwritten on the next catalog sync.
- [x] ADR 0017 is amended to reference the one-shot exemption and ADRs 0024 and 0025.
- [x] `AGENTS.md` `## Invariants` gains one invariant stating that Signal payload schemas live in the domain, the prompt renders them, and the execution skill defers to them; the heading and bullet prefixes runtime readers depend on remain unchanged.
- [x] `docs/tickets/gotchas.md` records the incident lesson: the execution skill and parser disagreed on the Gotcha shape, and malformed Signals are now archived and retried once.
- [x] `STATUS.md` records Spec 18 completion, the pending catalog publish as an explicit operator step, and the verification evidence.
- [x] The full pytest suite passes with no unrelated failures; Ruff and mypy are clean on every changed file.

**Verified:** 2026-11-02 — Full pytest suite green, ruff and mypy clean, ADRs and operating contract invariants recorded.
