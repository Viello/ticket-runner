# T047 — Doctor preflight checks for AGENTS.md and skills
Status: completed
Completed: 2026-09-18T03:19:00Z
Spec: docs/specs/08-worker-skill-protocol-and-telemetry.md
Blocked by: T046

### Requirements
- Extend `runner/application/doctor.py` to add dedicated pre-flight health checks for repository operating rules and required skills before queue processing begins:
  - `CHECK_AGENTS_MD`: verifies that `AGENTS.md` exists and is readable at the workspace root, reporting a failure with actionable remediation if missing.
  - `CHECK_SKILLS`: verifies that the configured `worker.execution_skill`, `.agents/skills/code-review/SKILL.md`, and `.agents/skills/diagnosing-bugs/SKILL.md` exist and are readable files on disk, reporting a failure with specific remediation naming the missing files.
- Wire both checks into `Doctor.run()` as strictly read-only pre-flight verifications.
- Jump-start:
  - Files to touch: `runner/application/doctor.py`, `tests/unit/application/test_doctor.py`.
  - Seams: `Doctor.check_agents_md()`, `Doctor.check_skills()`, `Doctor.run()`.
  - Anchor patterns: `check_config()`, `check_hook()`, and `check_verification_commands()` in `doctor.py`.
  - Verification: `python -m pytest tests/unit/application/test_doctor.py`.

### Acceptance Criteria
- `check_agents_md` passes when `AGENTS.md` exists and is readable at workspace root.
- `check_agents_md` fails with actionable remediation when `AGENTS.md` is missing.
- `check_skills` passes when the configured execution skill, `code-review`, and `diagnosing-bugs` skills exist on disk.
- `check_skills` fails with actionable remediation naming all missing skill files if any are absent.
- `Doctor.run()` includes both checks in the returned `DoctorReport`.
- All checks remain strictly read-only without modifying the filesystem.
- Full `test_doctor.py` suite passes and full repository test suite (`python -m pytest`) remains green.

### Gotchas
- Pre-flight checks must respect injected workspace paths and never hardcode paths relative to the current working directory.
