# T133: Doctor Pre-Flight and Skills Publish Gate

**Status:** done (reviewed; pre-flight doctor signal contract check and skills publish gate)
**Completed:** 2026-11-02T10:14:00Z
**Labels:** ready-for-agent
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** Make a provisioned execution skill machine-checked before dispatch. A new Doctor check reads the Target Project's configured execution skill, validates every embedded Signal example through the T132 contract checker, and fails with a remediation naming the skill file and the rule it violates. The skills publish step validates the whole catalog before staging and aborts on any rejected example, so a broken Worker Skill cannot reach other projects through the Skills Catalog.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/application/doctor.py`
  - `scripts/publish_agent_skills.py`
  - `tests/unit/application/test_doctor.py`
  - `tests/unit/scripts/test_publish_agent_skills.py`
- **Seams:** The `Doctor.run` check list after `check_skills`, and `publish_skills` before it stages the catalog or runs the GitHub preflight.
- **Existing-code anchors:** `CHECK_SKILLS`, `check_skills`, and `CheckResult` in `runner/application/doctor.py`; `load_all_skills`, `sanitize_and_copy_skills`, and `_run` in `scripts/publish_agent_skills.py`; `validate_markdown_signal_examples` from T132.
- **Verify:** `py -3 -m pytest tests/unit/application/test_doctor.py tests/unit/scripts/test_publish_agent_skills.py -q`

**Blocked by:** T132

- [x] A new `CHECK_SIGNAL_CONTRACT` check runs after `check_skills` in `Doctor.run`; it resolves the configured `worker.execution_skill` (or an explicit `execution_skill_path`) relative to the Target Project root.
- [x] A skill with no embedded examples passes, a skill with valid examples passes, and a provisioned stale skill fails before dispatch.
- [x] The failure message names the skill file and the violated rule; the remediation names the file and rule first and mentions `ticket-runner skills sync` only as a post-republish step.
- [x] `publish_skills` validates every catalog `SKILL.md` Signal example before staging and aborts on any rejected example; the script puts the repository root on its import path when executed directly, and a dry-run validates the same way.
- [x] Doctor tests cover stale, clean, and example-free skills; publish tests prove an invalid catalog aborts before staging while a valid catalog reaches the staging step.
- [x] Targeted tests pass; Ruff and mypy are clean on every changed file.
