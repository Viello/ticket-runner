# T102 — Project Heuristics Sniffer and AI Prompt Generator
Status: completed
Completed: 2026-09-23T15:08:00Z
Spec: docs/specs/12-project-scaffolding-and-skills-distribution.md
Blocked by: None
Security: required
Reasoning: medium

### Requirements
- Create `ProjectSniffer` pure application service in `runner/application/scaffolding.py`:
  - Inspects target project directory for project metadata and manifests:
    - Python: checks `pyproject.toml`, `setup.py`, `requirements.txt` $\rightarrow$ proposes `test_cmd = "python -m pytest"`.
    - Node.js: checks `package.json` $\rightarrow$ detects package manager lockfiles (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `bun.lockb`) $\rightarrow$ parses `scripts.test` and `scripts.build` $\rightarrow$ proposes appropriate test/build commands (e.g. `pnpm test`, `npm test`, `yarn test`, `bun test`).
    - Rust: checks `Cargo.toml` $\rightarrow$ proposes `test_cmd = "cargo test"`, `build_cmd = "cargo build"`.
    - Go: checks `go.mod` $\rightarrow$ proposes `test_cmd = "go test ./..."`.
    - Git: detects base branch (`main` vs `master`) via local git branches or git origin HEAD $\rightarrow$ defaults `base_branch` (fallback `main`), `branch = "agent/ticket-runner"`.
    - Project name: defaults to target directory name or git repository name.
  - Returns strongly-typed `ProjectHeuristics` domain dataclass containing detected fields (`name`, `detected_stack`, `test_cmd`, `build_cmd`, `base_branch`, `branch`, `provider`).
- Create `AIPromptGenerator` in `runner/application/prompt_generator.py`:
  - Formats an exhaustive, self-contained Markdown prompt for `ticket-runner init --ai-prompt`:
    - Context: Explains Ticket Runner's decoupled orchestrator model and expectations.
    - Schema: Exact YAML specification for minimal `ticket-runner.yaml` (<15 lines).
    - Guidelines: Instructions for the AI agent to inspect the target project's build files, Makefile, or CI workflows to pick the fastest and most reliable test and build commands.
    - Output format: Requires clean fenced YAML code block ready to be written to disk.
- Unit tests in `tests/unit/application/test_project_sniffer.py` and `tests/unit/application/test_prompt_generator.py`.
- Jump-start:
  - Files to touch: `runner/application/scaffolding.py`, `runner/application/prompt_generator.py`, `tests/unit/application/test_project_sniffer.py`, `tests/unit/application/test_prompt_generator.py`.
  - Seams: `ProjectSniffer.sniff(project_dir: Path) -> ProjectHeuristics`, `AIPromptGenerator.generate(heuristics: ProjectHeuristics | None = None) -> str`.
  - Verification: `pytest tests/unit/application/test_project_sniffer.py tests/unit/application/test_prompt_generator.py`.

### Acceptance Criteria
- `ProjectSniffer` accurately detects Python, Node.js (with npm, pnpm, yarn, bun), Rust, and Go project configurations from mock directories.
- `ProjectSniffer` detects git default branch (`main` or `master`) when git metadata is present, with safe fallback to `main`.
- `AIPromptGenerator.generate()` produces valid Markdown with complete schema documentation, stack examples, and strict formatting rules.
- Security verification: File inspection enforces bounded directory reads, avoids following symlinks pointing outside `project_dir`, and never executes untrusted project scripts during sniffing.

### Smoke Scenarios
**Scenario: Project Heuristics Sniffing and Prompt Generation**
- Setup: None (runs from repo root with synthetic directories).
- Why: Ensure `ProjectSniffer` correctly inspects project files without executing code, and `AIPromptGenerator` outputs the expected Markdown structure.
- Steps:
  1. Run Python one-liner in PowerShell sniffing a temporary Python project directory and generating the AI prompt:
     ```powershell
     python -c @"
     import tempfile, pathlib
     from runner.application.scaffolding import ProjectSniffer
     from runner.application.prompt_generator import AIPromptGenerator
     td = pathlib.Path(tempfile.mkdtemp())
     (td / 'pyproject.toml').write_text('[project]\nname="demo"\n', encoding='utf-8')
     sniffer = ProjectSniffer()
     h = sniffer.sniff(td)
     assert h.test_cmd == 'python -m pytest'
     assert h.detected_stack == 'python'
     p = AIPromptGenerator.generate(h)
     assert 'ticket-runner.yaml' in p
     print('PASS: ProjectSniffer and AIPromptGenerator verified')
     "@
     ```
- Expected: Output displays `PASS: ProjectSniffer and AIPromptGenerator verified`.

### Gotchas
- When parsing `package.json`, handle malformed JSON gracefully without crashing the sniffer.
- When inspecting Git branches, handle repositories with no commits or detached HEAD cleanly.
