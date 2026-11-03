# T139: Worker Telemetry Parity and Gatekeeper / TicketProcessor `-ticket-runner` Auditing

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/19-dual-track-skill-segregation.md

**What to build:** Update Gatekeeper and TicketProcessor resource-access telemetry checks and retry failure diagnostics to enforce the `-ticket-runner` review and debugging skills across both `OpenCodeWorker` and `AntigravityWorker`. When a Worker emits a ready Signal, the Runner audits `resources_accessed` for `"code-review-ticket-runner"` and (when `ticket.security_required` is true) `"security-review-ticket-runner"`, emitting soft warnings naming `.agents/skills/code-review-ticket-runner/SKILL.md` and `.agents/skills/security-review-ticket-runner/SKILL.md` when omitted, and directs attempt $\ge 2$ verification failure prompts to `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/application/gatekeeper.py`
  - `runner/application/ticket_processor.py`
  - `tests/unit/application/test_gatekeeper.py`
  - `tests/unit/application/test_ticket_processor.py`
  - `tests/unit/adapters/test_opencode_worker.py`
  - `tests/unit/adapters/test_antigravity_worker_adapter.py`
- **Seams:** `VerificationLoop._check_ready_warnings` and `build_verification_failure_prompt` in `runner/application/gatekeeper.py`; `GatekeeperTicketProcessor.evaluate_ready_warnings` in `runner/application/ticket_processor.py`; `extract_resource_access` in `runner/adapters/opencode/opencode_worker.py` and `runner/adapters/antigravity/antigravity_worker.py`.
- **Existing-code anchors:** `_check_ready_warnings` and `build_verification_failure_prompt` in `runner/application/gatekeeper.py`; `evaluate_ready_warnings` in `runner/application/ticket_processor.py`; resource-access extraction tests in `tests/unit/adapters/test_opencode_worker.py` and `tests/unit/adapters/test_antigravity_worker_adapter.py`.
- **Verify:** `py -3 -m pytest tests/unit/application/test_gatekeeper.py tests/unit/application/test_ticket_processor.py tests/unit/adapters/test_opencode_worker.py tests/unit/adapters/test_antigravity_worker_adapter.py -q`

**Blocked by:** T137 (Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract)

- [ ] `VerificationLoop._check_ready_warnings` in `runner/application/gatekeeper.py` and `GatekeeperTicketProcessor.evaluate_ready_warnings` in `runner/application/ticket_processor.py` check `resources_accessed` for `"code-review-ticket-runner"` and (when `ticket.security_required` is true) `"security-review-ticket-runner"`, emitting soft warnings naming `.agents/skills/code-review-ticket-runner/SKILL.md` and `.agents/skills/security-review-ticket-runner/SKILL.md` when unread and emitting no skill warnings when read.
- [ ] `build_verification_failure_prompt` in `runner/application/gatekeeper.py` prepends the directive to read and follow `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md` when `attempt >= 2`.
- [ ] Unit tests for both `OpenCodeWorker` and `AntigravityWorker` prove that file-read tool events targeting `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/security-review-ticket-runner/SKILL.md`, `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`, and `.agents/skills/handoff-ticket-runner/SKILL.md` decode the exact `<name>-ticket-runner` identifier into `resources_accessed`.
- [ ] Targeted adapter and application tests pass; Ruff and mypy are clean on every changed file.

