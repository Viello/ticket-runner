# T127: Default `implement-ticket-runner` Execution Skill Plumbing and Canonical Prompt Builder

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/17-human-first-ticket-document-format.md

**What to build:** Switch Ticket Runner's default `worker.execution_skill` to `.agents/skills/implement-ticket-runner/SKILL.md` across configuration, container, Doctor, HandoffCoordinator, TicketProcessor, and sandbox scaffolding, and update `PromptBuilder` to render the canonical `to-ticket-runner` sections (`What to build`, `Jump-start`, `Acceptance criteria`, `Ticket Gotchas`), the checkbox tick permission boundary, and the severity-gated 3-axis security escalation rule.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/application/prompt_builder.py`
  - `runner/application/doctor.py`
  - `runner/application/ticket_processor.py`
  - `runner/application/handoff_coordinator.py`
  - `runner/adapters/config/yaml_config_loader.py`
  - `runner/container.py`
  - `runner/tools/scaffold_sandbox.py`
  - `config.yaml`
  - `config.example.yaml`
  - `.agents/skills/implement-ticket-runner/SKILL.md` (initial vendored skill file so Doctor/scaffold tests resolve it on disk)
  - `tests/unit/application/test_prompt_builder.py`
  - `tests/unit/application/test_doctor.py`
  - `tests/unit/tools/test_scaffold_sandbox.py`
- **Seams:** `build_prompt` in `runner/application/prompt_builder.py` and default `execution_skill` constants across config, container, interactors, and sandbox scaffolder.
- **Existing-code anchors:** `DEFAULT_INVARIANTS` and `build_prompt` in `runner/application/prompt_builder.py`; `DEFAULT_EXECUTION_SKILL` in `runner/application/doctor.py`; `DEFAULT_MACHINE_CONFIG` in `runner/adapters/config/yaml_config_loader.py`; `build_container` in `runner/container.py`; `scaffold_sandbox.py` in `runner/tools/scaffold_sandbox.py`.
- **Verify:** `py -3 -m pytest tests/unit/application/test_prompt_builder.py tests/unit/application/test_doctor.py tests/unit/tools/test_scaffold_sandbox.py -x`

**Blocked by:** T124 (Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer), T125 (Gatekeeper Dispatch-Baseline Tick Boundary and Evidence Card Unticked Criteria)

- [ ] Default `worker.execution_skill` resolves to `.agents/skills/implement-ticket-runner/SKILL.md` across `runner/container.py`, `runner/adapters/config/yaml_config_loader.py`, `runner/application/doctor.py`, `runner/application/handoff_coordinator.py`, `runner/application/prompt_builder.py`, `runner/application/ticket_processor.py`, `runner/tools/scaffold_sandbox.py`, `config.yaml`, and `config.example.yaml` (amending ADR 0008).
- [ ] `PromptBuilder.build` renders the active ticket's canonical sections (`### What to build`, `### Jump-start`, `### Acceptance criteria`, and `### Ticket Gotchas`) and formats `ticket.jump_start` bullets cleanly when present.
- [ ] `PromptBuilder.build` states the exact Spec 17 tick-permission boundary: the Worker must flip satisfied criteria from `- [ ]` to `- [x]` under `## Acceptance criteria` in the active ticket file before emitting `.agent/signals/<ticket_id>_ready.json`, and is strictly forbidden from modifying any other line or section of the active ticket file, editing `docs/tickets/gotchas.md`, or touching any other file under `docs/tickets/`.
- [ ] `PromptBuilder.build` instructs the Worker on 3-axis `/code-review` (`Standards`, `Spec`, and `Security` referencing `.agents/skills/security-review/SKILL.md`) with severity-gated escalation: Low/Medium findings never interrupt the human; Critical/High findings must be remediated in-pass, and **only if remediation is blocked** by an architectural decision or missing secret does the Worker emit `.agent/questions/<ticket_id>.json` and stop.
