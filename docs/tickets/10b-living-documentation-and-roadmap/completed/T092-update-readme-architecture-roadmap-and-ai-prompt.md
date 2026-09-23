# T092 — Update README.md with Ecosystem Architecture, Roadmap & AI Setup Prompt
Status: completed
Completed: 2026-09-23T08:08:00Z
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
- `writing-shape`: Shape raw material into structured documentation, paragraph by paragraph with deliberate grounding.

### Smoke Scenarios
**Scenario: Verify README Documentation and AI Setup Prompt**
- Setup: None (runs from repo root).
- Why: Ensure prospective developers and AI assistants reading `README.md` have an immediate, actionable guide to setup, architecture, and project configuration.
- Steps:
  1. Run the Python verification script in PowerShell to assert that all ecosystem diagrams, workflow stages, roadmap specifications, AI setup prompts, CLI command forms, and balanced code fences are present in `README.md`:
     ```powershell
     python -c @"
     with open('README.md', 'r', encoding='utf-8') as f:
         content = f.read()

     checks = {
         'Triad ecosystem diagram': 'Viello/agent-skills' in content and 'Viello/ticket-runner' in content and 'Target Project' in content,
         '8-stage development workflow': '1. Planning & Alignment' in content and '8. Human Gate & Completion' in content,
         'Roadmap Specs 10b through 13': 'Spec 10b' in content and 'Spec 11' in content and 'Spec 12' in content and 'Spec 13' in content,
         'LLM setup prompt schema': 'ticket-runner.yaml' in content and 'base_branch:' in content,
         'Multi-stack prompt examples': 'pnpm' in content and 'pytest' in content and 'cargo' in content and 'go test' in content,
         'CLI command syntax': 'ticket-runner --project-dir' in content and 'ticket-runner init' in content and 'ticket-runner skills sync' in content,
         'Two-tier config reference': '~/.ticket-runner/config.yaml' in content and 'ticket-runner.yaml' in content,
     }

     missing = [k for k, v in checks.items() if not v]
     if missing:
         print('FAILED CHECKS:', missing)
         exit(1)

     lines = content.splitlines()
     fence_count_3 = sum(1 for l in lines if l.strip().startswith('```') and not l.strip().startswith('````'))
     fence_count_4 = sum(1 for l in lines if l.strip().startswith('````'))

     if fence_count_3 % 2 != 0:
         print(f'ERROR: Unbalanced 3-backtick fences ({fence_count_3})')
         exit(1)

     if fence_count_4 % 2 != 0:
         print(f'ERROR: Unbalanced 4-backtick fences ({fence_count_4})')
         exit(1)

     print('PASS: README.md fully verified for ecosystem architecture, 8-stage workflow, roadmap, and AI setup prompt.')
     "@
     ```
  2. Inspect the terminal output for the `PASS` confirmation message and exit code 0.
- Expected: Script prints `PASS: README.md fully verified for ecosystem architecture, 8-stage workflow, roadmap, and AI setup prompt.` with exit code 0.

### Gotchas
- Ensure all command-line examples match the planned CLI syntax (`ticket-runner --project-dir <path> start`, `ticket-runner init`, `ticket-runner skills sync`).
- Enclose standalone markdown prompts containing internal fenced code blocks in 4-backtick (` ````markdown ` ... ` ```` `) boundaries to prevent outer fence termination.
