# T104 — Project Scaffolding Engine and Interactive CLI Adapter
Status: pending
Spec: docs/specs/12-project-scaffolding-and-skills-distribution.md
Blocked by: T101, T102, T103
Security: required
Reasoning: medium

### Requirements
- Implement project scaffolding coordinator and CLI adapter in `runner/adapters/cli/scaffolder.py`:
  - Interactor `ProjectScaffolder` accepting `ProjectSniffer`, `SkillsClient`, and console prompt interfaces:
    - Scaffolds target directory structure:
      - `docs/specs/.gitkeep`
      - `docs/tickets/.gitkeep`
      - `docs/tickets/gotchas.md` (initial template if missing)
      - `.agent/.gitkeep`
      - `.agent/archive/completed/.gitkeep`
      - `.agent/signals/.gitkeep`
      - `.agent/questions/.gitkeep`
      - `.agent/checkpoints/.gitkeep`
    - Checks `<project_dir>/.gitignore`; if missing, creates it; ensures `.agent/` is in `.gitignore`.
    - Detects project defaults via `ProjectSniffer`.
    - In interactive mode: uses `rich.prompt.Prompt` and `rich.prompt.Confirm` to present detected defaults (`project.name`, `base_branch`, `branch`, `verification.test_cmd`, `verification.build_cmd`, `worker.provider`) allowing inline editing or confirmation.
    - In non-interactive mode (`yes=True` / `--non-interactive`): automatically accepts all detected defaults without prompting.
    - Generates minimal `<project_dir>/ticket-runner.yaml` with confirmed settings.
    - Offers/triggers skills synchronization via `SkillsClient` (skip if `sync_skills=False`).
- Unit tests in `tests/unit/adapters/test_cli_scaffolder.py` with mock inputs, non-interactive flags, directory structure assertions, and `.gitignore` verification.
- Jump-start:
  - Files to touch: `runner/adapters/cli/scaffolder.py`, `tests/unit/adapters/test_cli_scaffolder.py`.
  - Seams: `ProjectScaffolder.scaffold(project_dir: Path, interactive: bool = True, sync_skills: bool = True) -> ScaffoldReport`.
  - Verification: `pytest tests/unit/adapters/test_cli_scaffolder.py`.

### Acceptance Criteria
- `ProjectScaffolder` creates the complete required directory tree with `.gitkeep` markers.
- `docs/tickets/gotchas.md` is initialized with standard gotchas template if not already present.
- `<project_dir>/.gitignore` is updated to include `.agent/` without duplicating entries.
- In non-interactive mode (`interactive=False`), scaffolding completes without blocking on user input and produces a valid `ticket-runner.yaml`.
- In interactive mode, prompts display detected defaults and allow user overrides.
- Security verification: Directory and file creation strictly adheres to the target `project_dir` boundaries and rejects symlink traversal.

### Smoke Scenarios
**Scenario: Non-Interactive Project Scaffolding**
- Setup: None (runs in empty temporary directory).
- Why: Verify that `ProjectScaffolder` sets up the complete directory tree, `.gitignore`, and `ticket-runner.yaml` without human prompting.
- Steps:
  1. Run Python one-liner scaffolding a temporary directory with `interactive=False`:
     `python -c "import tempfile, pathlib; from runner.adapters.cli.scaffolder import ProjectScaffolder; from tests.fakes.fake_skills_client import FakeSkillsClient; td = pathlib.Path(tempfile.mkdtemp()); scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient()); scaffolder.scaffold(project_dir=td, interactive=False, sync_skills=False); assert (td / 'ticket-runner.yaml').is_file(); assert (td / 'docs' / 'tickets' / 'gotchas.md').is_file(); assert (td / '.agent').is_dir(); assert '.agent/' in (td / '.gitignore').read_text(encoding='utf-8'); print('PASS: Directory tree and configuration scaffolded successfully')"`
- Expected: Output displays `PASS: Directory tree and configuration scaffolded successfully`.

### Gotchas
- When reading or appending to `.gitignore`, ensure proper newline separation so that `.agent/` is added on a new line and does not corrupt existing entries.
