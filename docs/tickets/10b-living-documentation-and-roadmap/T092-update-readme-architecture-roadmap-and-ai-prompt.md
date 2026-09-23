# T092 — Update README.md with Ecosystem Architecture, Roadmap & AI Setup Prompt
Status: pending
Spec: docs/specs/10b-living-documentation-and-roadmap.md
Blocked by: T091
Reasoning: medium

### Requirements
- Update `README.md` to serve as the comprehensive entry point for the external, multi-agent development system:
  1. **Ecosystem Overview**: Explain the three decoupled pillars: Reusable Skills (`Viello/agent-skills`), Standalone Orchestrator (`Viello/ticket-runner`), and Target Projects.
  2. **8-Stage Development Workflow**: Diagram the end-to-end loop (Planning $\rightarrow$ Specs $\rightarrow$ Tickets $\rightarrow$ Implementation $\rightarrow$ Reviews $\rightarrow$ Security $\rightarrow$ Verification $\rightarrow$ Completion).
  3. **Architectural Roadmap**: Document the planned sequence of specifications:
     - Spec 10b: Living Documentation, Domain Model & Architecture Roadmap (Active)
     - Spec 11: Decoupled Project Root & Multi-Agent Worker Port
     - Spec 12: Project Scaffolding, LLM-Friendly Config & Skills Distribution
     - Spec 13: Token-Guarded Verification Subsystem & Human-in-the-Loop Gate
  4. **Standalone LLM-Friendly Project Setup Prompt**: Provide a copy-pasteable Markdown template that developers can feed to an AI agent to auto-configure `ticket-runner.yaml` for any repository (Node, Python, Go, Rust, Monorepo).

### Acceptance Criteria
- `README.md` contains the ecosystem architecture diagram and workflow description.
- `README.md` contains the Roadmap section detailing Specs 10b, 11, 12, and 13.
- `README.md` contains the standalone LLM configuration prompt with schema and examples.
### Suggested Skills
- `writing-for-agents`: Progressive disclosure, clear cognitive hierarchy, and authoritative reference design.

### Smoke Scenarios
**Scenario: Verify README Documentation and AI Setup Prompt**
- Setup: None (runs from repo root).
- Why: Ensure prospective developers and AI assistants reading `README.md` have an immediate, actionable guide to setup and architecture.
- Steps:
  1. Inspect `README.md` and check that the roadmap for Specs 11–13 is clearly formatted.
  2. Verify that the AI Setup Prompt section includes copyable instructions and a complete `ticket-runner.yaml` schema.
- Expected: All sections render cleanly on GitHub markdown preview without missing code block tags.

### Gotchas
- Ensure all command-line examples match the planned CLI syntax (`ticket-runner --project-dir <path> start`, `ticket-runner init`).
