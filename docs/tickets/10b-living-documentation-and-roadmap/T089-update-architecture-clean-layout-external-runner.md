# T089 — Update ARCHITECTURE.md Clean Architecture Layout for External Runner
Status: pending
Spec: docs/specs/10b-living-documentation-and-roadmap.md
Blocked by: None
Reasoning: medium

### Requirements
- Update `ARCHITECTURE.md` to reflect Ticket Runner as an external, multi-agent orchestrator targeting `--project-dir`.
- Add the `AgentWorker` port (`runner/ports/agent_worker.py`) and its concrete adapters (`runner/adapters/opencode/` and `runner/adapters/antigravity/`).
- Document the two-tier configuration overlay (`runner/domain/config.py` merging `~/.ticket-runner/config.yaml` and `<project-dir>/ticket-runner.yaml`).
- Document the Verification Subsystem directory layout (`.agents/skills/verify-<app>/`, `harness/`, `features/`, and `.agent/evidence/`).
- Diagram the triad ecosystem: reusable skills repo (`Viello/agent-skills`), runner orchestrator repo (`Viello/ticket-runner`), and target projects.
- Preserve strict Clean Architecture dependency arrows (domain zero dependencies, ports abstract protocols, application orchestrates interactor workflows, adapters implement outward I/O).

### Acceptance Criteria
- `ARCHITECTURE.md` directory tree includes `runner/ports/agent_worker.py` and `runner/adapters/antigravity/`.
- `ARCHITECTURE.md` illustrates the `--project-dir` separation between runner binaries/global config and the target repository.
- `ARCHITECTURE.md` describes the Verification Subsystem and evidence artifact storage.
- All references adhere strictly to the project's Clean Architecture conventions.
### Suggested Skills
- `writing-for-agents`: Guidelines for writing documents an agent consumes (progressive disclosure, high completion bounds, lean hierarchy).
- `clean-architecture`: Layer boundaries, dependency rule, and port/adapter contracts.

### Smoke Scenarios
**Scenario: Verify Architecture Layout and Symbols**
- Setup: None (runs from repo root).
- Why: Ensure the updated architecture document is syntactically valid markdown, includes all new ports and adapters, and maintains Clean Architecture layer integrity.
- Steps:
  1. Open `ARCHITECTURE.md` and verify that `AgentWorker` is listed under `runner/ports/`.
  2. Verify that `runner/adapters/antigravity/` is listed under `runner/adapters/`.
  3. Verify that the ecosystem triad and `--project-dir` boundaries are visually mapped in the text diagram.
- Expected: All sections are present, formatted correctly in markdown, and contain no broken relative links or missing layers.

### Gotchas
- Do not remove existing Spec 01–10 components that remain active (Doctor, Queue, Signal Repository, Discord Gateway, Rich Terminal Display).
