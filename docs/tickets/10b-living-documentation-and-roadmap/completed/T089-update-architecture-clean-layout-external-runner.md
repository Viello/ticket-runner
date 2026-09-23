# T089 — Update ARCHITECTURE.md Clean Architecture Layout for External Runner
Status: completed
Completed: 2026-09-23T07:45:00Z
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
- Why: We need to make sure that the architecture documentation correctly shows our external runner layout, includes all required ports, adapters, and ecosystem boundaries, and doesn't miss any critical design components.
- Steps:
  1. Run the Python verification script in PowerShell to assert that all required architecture symbols exist:
     ```powershell
     python -c @"
     with open('ARCHITECTURE.md', 'r', encoding='utf-8') as f:
         content = f.read()
     required = [
         'AgentWorker',
         'runner/ports/agent_worker.py',
         'runner/adapters/antigravity/',
         'runner/adapters/opencode/',
         '--project-dir',
         '~/.ticket-runner/config.yaml',
         'ticket-runner.yaml',
         'Viello/agent-skills',
         'verify-<app>',
         '.agent/evidence/',
         'ADRs 0001 to 0022',
     ]
     missing = [t for t in required if t not in content]
     if missing:
         print('MISSING SYMBOLS:', missing)
         exit(1)
     print('PASS: All required architecture symbols present.')
     "@
     ```
  2. Inspect `ARCHITECTURE.md` lines 1 to 45 to confirm the Triad Ecosystem diagram and `--project-dir` boundaries are visually formatted.
- Expected: Terminal prints `PASS: All required architecture symbols present.` with exit code 0, and the document renders Clean Architecture layers without broken structure.

### Gotchas
- Do not remove existing Spec 01–10 components that remain active (Doctor, Queue, Signal Repository, Discord Gateway, Rich Terminal Display).
