# T105 — CLI Subcommands (init, skills sync), Two-Tier Config Integration, and Spec 12 Integration Suite
Status: completed
Completed: 2026-09-24T00:03:00Z
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
**Scenario: End-to-End Scaffolding and Doctor Verification** [also auto-covered]
- Setup: None (runs in an isolated temporary directory from repo root).
- Why: Verify that an operator can scaffold a new project via CLI in non-interactive mode and immediately pass doctor pre-flight checks using two-tier config resolution.
- Steps:
  1. Execute self-contained verification snippet in PowerShell:
     ```powershell
     python -c @"
     import tempfile, pathlib, subprocess, sys
     from runner.adapters.git.pre_push_hook import PrePushHookInstaller

     with tempfile.TemporaryDirectory() as td_str:
         td = pathlib.Path(td_str)
         res_init = subprocess.run([sys.executable, 'ticket_runner.py', 'init', '--project-dir', str(td), '--yes', '--no-skills'], capture_output=True, text=True)
         assert res_init.returncode == 0, f'init failed: {res_init.stderr}'
         assert (td / 'ticket-runner.yaml').is_file()

         subprocess.run(['git', 'init', '-b', 'agent/ticket-runner', str(td)], check=True, capture_output=True)
         subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=td, check=True)
         subprocess.run(['git', 'config', 'user.name', 'Tester'], cwd=td, check=True)

         (td / 'AGENTS.md').write_text('# Operating Rules\n', encoding='utf-8')
         t_dir = td / 'docs' / 'tickets' / '01-smoke'
         t_dir.mkdir(parents=True, exist_ok=True)
         (t_dir / 'T001-smoke.md').write_text('# T001 — Smoke Ticket\nStatus: pending\n\n### Requirements\n- Smoke.\n\n### Acceptance Criteria\n- Pass.\n\n### Smoke Scenarios\n- Smoke.\n', encoding='utf-8')

         skills_dir = td / '.agents' / 'skills'
         for sk in ['implement', 'code-review', 'diagnosing-bugs']:
             sd = skills_dir / sk
             sd.mkdir(parents=True, exist_ok=True)
             (sd / 'SKILL.md').write_text('# Skill\n', encoding='utf-8')

         PrePushHookInstaller.install(git_dir=td / '.git')
         subprocess.run(['git', 'add', '.'], cwd=td, check=True)
         subprocess.run(['git', 'commit', '-m', 'chore: initial commit'], cwd=td, check=True)

         res_doc = subprocess.run([sys.executable, 'ticket_runner.py', 'doctor', '--project-dir', str(td), '--local-only'], capture_output=True, text=True)
         assert res_doc.returncode == 0, f'doctor failed: {res_doc.stderr}'
         print('SUCCESS: Scaffolding and doctor pre-flight verified.')
     "@
     ```
- Expected: Prints `SUCCESS: Scaffolding and doctor pre-flight verified.` with exit code 0.

### Gotchas
- When `--config` is explicitly specified by the user, ensure it overrides the project overlay path while still allowing two-tier merging over the global configuration.
