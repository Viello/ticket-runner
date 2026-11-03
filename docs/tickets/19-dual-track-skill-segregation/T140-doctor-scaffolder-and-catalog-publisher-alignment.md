# T140: Doctor Pre-Flight Skills Check, Sandbox Scaffolder, and Catalog Publisher Alignment

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/19-dual-track-skill-segregation.md

**What to build:** Update `Doctor.check_skills`, `scaffold_sandbox.py`, `AGENTS.md` extraction prefixes, and `publish_agent_skills.py` so pre-flight verification, sandbox initialization, `AGENTS.md` drift synchronization, and catalog publication all provision and verify the segregated `-ticket-runner` skill suite.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/application/doctor.py`
  - `runner/tools/scaffold_sandbox.py`
  - `scripts/publish_agent_skills.py`
  - `AGENTS.md` (`## Invariants` handoff bullet and `## Agent skills` bullets)
  - `tests/unit/application/test_doctor.py`
  - `tests/unit/tools/test_scaffold_sandbox.py`
  - `tests/unit/scripts/test_sync_agents_md.py`
  - `tests/unit/scripts/test_publish_agent_skills.py`
- **Seams:** `REQUIRED_SKILL_PATHS` and `Doctor.check_skills` in `runner/application/doctor.py`; `CURATED_SKILLS`, `AGENT_BULLETS_KEEP_PREFIXES_DEFAULT`, `AGENT_BULLETS_KEEP_PREFIXES_ALL`, `FALLBACK_CURATED_SUBSET`, and `DEFAULT_UPSTREAM_AGENTS_MD` in `runner/tools/scaffold_sandbox.py`; `verify_tarball_endpoint` in `scripts/publish_agent_skills.py`.
- **Existing-code anchors:** `REQUIRED_SKILL_PATHS` and `check_skills` in `runner/application/doctor.py`; `extract_curated_subset` and `scaffold` in `runner/tools/scaffold_sandbox.py`; `sync_agents_md` in `scripts/sync_agents_md.py`; `verify_tarball_endpoint` in `scripts/publish_agent_skills.py`.
- **Verify:** `py -3 -m pytest tests/unit/application/test_doctor.py tests/unit/tools/test_scaffold_sandbox.py tests/unit/scripts/test_sync_agents_md.py tests/unit/scripts/test_publish_agent_skills.py -q`

**Blocked by:** T137 (Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract)

- [ ] `REQUIRED_SKILL_PATHS` in `runner/application/doctor.py` requires `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`, `.agents/skills/handoff-ticket-runner/SKILL.md`, and `.agents/skills/security-review-ticket-runner/SKILL.md` alongside the configured `execution_skill` (`.agents/skills/implement-ticket-runner/SKILL.md`).
- [ ] `CURATED_SKILLS` in `runner/tools/scaffold_sandbox.py` provisions the `-ticket-runner` autonomous skill suite (`implement-ticket-runner`, `code-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`, `security-review-ticket-runner`, `to-ticket-runner`) so a freshly scaffolded sandbox passes `Doctor.check_skills` immediately.
- [ ] `AGENTS.md` (`## Invariants` and `## Agent skills`) and `AGENT_BULLETS_KEEP_PREFIXES_DEFAULT`, `AGENT_BULLETS_KEEP_PREFIXES_ALL`, `FALLBACK_CURATED_SUBSET`, and `DEFAULT_UPSTREAM_AGENTS_MD` in `runner/tools/scaffold_sandbox.py` are updated in lockstep so `.agents/skills/handoff-ticket-runner/SKILL.md` and the `-ticket-runner` skill bullets are preserved by `extract_curated_subset` and `scripts/sync_agents_md.py`.
- [ ] `verify_tarball_endpoint` in `scripts/publish_agent_skills.py` verifies the presence of all six `-ticket-runner` skills (`to-ticket-runner`, `implement-ticket-runner`, `code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`) alongside `implement/SKILL.md`.
- [ ] Targeted Doctor, scaffolder, `sync_agents_md`, and publisher tests pass; Ruff and mypy are clean on every changed file.

