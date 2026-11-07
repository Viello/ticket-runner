# T141: ADR 0026, Operating Contract & README Alignment, and `ticket-runner-site` Synchronization

**Status:** done (reviewed; ADR 0026 recorded, living docs & README aligned, site synced and verified)
**Labels:** completed
**Parent:** docs/specs/19-dual-track-skill-segregation.md

**What to build:** Close Spec 19 by recording its binding architectural decisions in ADR 0026 (and amending ADRs 0008, 0013, 0014, and 0020), codifying the Dual-Track Skill Segregation Rule in `AGENTS.md` and `docs/ai/workflow.md`, updating the 8-stage pipeline documentation in `D:\Projects\README.md`, synchronizing `D:\Repos\ticket-runner-site` (`scripts/sync-runner.mjs`, vendored `.agents/skills/`, and `content/snapshot.json`), and updating `docs/tickets/gotchas.md` and `STATUS.md`.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `docs/adr/0026-dual-track-skill-segregation-and-human-control-routing.md` (new)
  - `docs/adr/0008-configurable-worker-execution-skill.md`
  - `docs/adr/0013-ticket-driven-security-review.md`
  - `docs/adr/0014-interrupt-and-resume-context-handoff.md`
  - `docs/adr/0020-direct-file-read-skill-protocol-and-telemetry.md`
  - `AGENTS.md`
  - `docs/ai/workflow.md`
  - `README.md`
  - `docs/tickets/gotchas.md`
  - `STATUS.md`
  - `D:\Repos\ticket-runner-site\scripts\sync-runner.mjs`
  - `D:\Repos\ticket-runner-site\.agents\skills\`
  - `D:\Repos\ticket-runner-site\content\snapshot.json`
- **Seams:** Existing one-paragraph ADR format in `docs/adr/`; `## Invariants`, `## Environment`, and `## Agent skills` headings and bullet prefixes in `AGENTS.md`; 8-stage pipeline diagram and Stage Details in `README.md`; `pipelineDefinitions` in `D:\Repos\ticket-runner-site\scripts\sync-runner.mjs`.
- **Existing-code anchors:** `docs/adr/0024-signal-schema-ownership-and-contract-checks.md`; `README.md` (`## 8-Stage Development Workflow` and `### Stage Details`); `pipelineDefinitions` in `D:\Repos\ticket-runner-site\scripts\sync-runner.mjs`.
- **Verify:** `py -3 -m pytest -q` and `npm --prefix D:\Repos\ticket-runner-site run verify`

**Blocked by:** T137, T138, T139, T140

- [x] `docs/adr/0026-dual-track-skill-segregation-and-human-control-routing.md` records the Dual-Track Skill Segregation Rule, the 6-pair skill matrix, and Question Signal (`WAITING_FOR_USER`) human control routing; ADRs 0008, 0013, 0014, and 0020 are amended to reference the `-ticket-runner` skill family and ADR 0026.
- [x] `AGENTS.md` and `docs/ai/workflow.md` state the Dual-Track Skill Segregation Rule (interactive Human + AI skills never carry autonomous Runner instructions or `.agent/` Signal paths; `/handoff` in `docs/ai/workflow.md` describes interactive handoff and `STATUS.md` synchronization), while preserving the `## Invariants`, `## Environment`, and `## Agent skills` headings and prefixes required by runtime readers.
- [x] `D:\Projects\README.md` updates the 8-stage pipeline diagram, Stage Details, and config examples so Stage 3 names `/to-ticket-runner`, Stage 4 names `.agents/skills/implement-ticket-runner/SKILL.md`, Stage 5 names `code-review-ticket-runner`, and Stage 6 names `security-review-ticket-runner`.
- [x] `D:\Repos\ticket-runner-site` updates `scripts/sync-runner.mjs` (`pipelineDefinitions`), synchronizes vendored `.agents/skills/`, regenerates `content/snapshot.json` via `npm run sync`, and passes `npm run verify`.
- [x] `docs/tickets/gotchas.md` records the cross-contamination lesson and `STATUS.md` records Spec 19 completion and the pending `py -3 scripts/publish_agent_skills.py` operator step.
- [x] Full pytest suite (`py -3 -m pytest -q`) passes with 0 failures.

**Verified:** 2026-11-03 — Targeted tests (85 passed), full pytest suite (2,208 passed, 0 failures), site test suite (88 passed, 0 failures), and site verification (`npm --prefix D:\Repos\ticket-runner-site run verify`) clean.
