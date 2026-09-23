# T105 — CLI Subcommands (init, skills sync), Two-Tier Config Integration, and Spec 12 Integration Suite
Status: pending
Spec: docs/specs/12-project-scaffolding-and-skills-distribution.md
Blocked by: T104
Security: required
Reasoning: medium

### Requirements
- Update `ticket_runner.py`:
  - Add `init` subcommand:
    - `--project-dir <path>`: Target project directory (defaults to cwd).
    - `--ai-prompt`: Print the generated Markdown prompt for AI assistants to stdout and exit 0 immediately.
    - `--yes` / `--non-interactive`: Automatically accept detected defaults without prompting.
    - `--no-skills`: Bypass skills synchronization during scaffolding.
    - Handler invokes `ProjectScaffolder` or `AIPromptGenerator`.
  - Add `skills` subcommand with nested `sync` action:
    - `skills sync [--project-dir <path>] [--force]`: Synchronizes skills catalog into target project.
  - Realign `run_doctor` and `run_start`:
    - Use `YamlConfigLoader.load_two_tier(project_dir=project_dir)` to load configuration by default, resolving `ticket-runner.yaml` (or fallback `config.yaml`) overlaid on global config.
    - Support explicit `--config <path>` overriding the project overlay path.
- Create end-to-end integration test suite `tests/specs/test_spec_12_scaffolding.py`:
  - Test CLI `init` non-interactive execution on mock Python and Node.js repositories.
  - Test CLI `init --ai-prompt` output structure.
  - Test CLI `skills sync`.
  - Test running `doctor` on an initialized repository verifying that two-tier configuration passes pre-flight checks.
- Jump-start:
  - Files to touch: `ticket_runner.py`, `runner/container.py`, `tests/specs/test_spec_12_scaffolding.py`.
  - Seams: CLI parser subparsers (`init`, `skills`), `main(argv)`.
  - Verification: `pytest tests/specs/test_spec_12_scaffolding.py`.

### Acceptance Criteria
- `ticket_runner.py init --project-dir <dir> --yes --no-skills` executes with exit code 0, creating all directories and valid `ticket-runner.yaml`.
- `ticket_runner.py init --ai-prompt` outputs complete Markdown prompt with exit code 0.
- `ticket_runner.py skills sync --project-dir <dir>` synchronizes skills catalog with exit code 0.
- `doctor` and `start` subcommands seamlessly discover and merge `<project-dir>/ticket-runner.yaml` over global preferences.
- Security verification: CLI argument parsing validates paths, handles invalid/non-existent directory arguments cleanly, and exits with code 1 and descriptive error messages.

### Smoke Scenarios
**Scenario: End-to-End Scaffolding and Doctor Verification**
- Setup: None (runs in empty temporary directory).
- Why: Verify that an operator can scaffold a new project via CLI and immediately pass doctor pre-flight checks using two-tier config resolution.
- Steps:
  1. Run CLI init in temporary directory:
     `python ticket_runner.py init --project-dir <dir> --yes --no-skills`
  2. Run CLI doctor on the initialized directory:
     `python ticket_runner.py doctor --project-dir <dir> --local-only`
- Expected: `init` creates valid configuration and directories; `doctor` pre-flight verification passes with exit code 0.

### Gotchas
- When `--config` is explicitly specified by the user, ensure it overrides the project overlay path while still allowing two-tier merging over the global configuration.
