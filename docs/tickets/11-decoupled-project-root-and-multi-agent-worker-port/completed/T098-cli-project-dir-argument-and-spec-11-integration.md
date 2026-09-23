# T098 — CLI `--project-dir` Argument Plumbing and Spec 11 Integration Suite
Status: completed
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
Completed: 2026-09-23T13:50:00Z
Blocked by: T096, T097
Security: required
Reasoning: medium

### Requirements
- Update `create_parser()` in `ticket_runner.py` to add `--project-dir <path>` across the top-level parser and subcommands (`doctor`, `start`), defaulting to `Path.cwd().resolve()`.
- Plumb `project_dir` through `run_doctor` and `run_start` into `build_container` and `Doctor`.
- Validate that `--project-dir` exists and is a directory before running commands, raising a clear error if invalid.
- Implement integration test `tests/specs/test_spec_11_decoupled_runner.py` simulating running the CLI against a separate external target repository with isolated queue execution.
- Update `README.md` CLI Reference and Quickstart with `--project-dir` syntax, usage examples, and default directory behaviors.
- Jump-start:
  - Files to touch: `ticket_runner.py`, `README.md`, `tests/specs/test_spec_11_decoupled_runner.py`.
  - Seams: `create_parser()`, `main()`, `run_start(project_dir=...)`, `run_doctor(project_dir=...)`.
  - Verification: `pytest tests/specs/test_spec_11_decoupled_runner.py`.

### Acceptance Criteria
- `ticket_runner.py` accepts `--project-dir <path>` and validates directory existence.
- Running `ticket_runner.py doctor` or `start` against an external repository operates entirely within that target directory.
- `README.md` documents `--project-dir` argument, default fallback, and examples.
- Security verification: Path arguments are validated and resolved; non-existent or invalid paths exit cleanly with an informative error.

### Smoke Scenarios
**Scenario: CLI Doctor and Start with --project-dir**
- Setup: None (runs directly using Python and temporary directories).
- Why: Confirm that an operator can execute `ticket-runner` against any external repository from any working directory, with defensive validation catching non-existent paths before executing.
- Steps:
  1. Open PowerShell and run the copy-pasteable verification snippet:
     ```powershell
     python -c @"
     import subprocess, sys, tempfile
     from pathlib import Path
     with tempfile.TemporaryDirectory() as tmp:
         target = Path(tmp).resolve()
         subprocess.run(['git', 'init'], cwd=target, check=True, stdout=subprocess.DEVNULL)
         res = subprocess.run([sys.executable, 'ticket_runner.py', '--project-dir', str(target), 'doctor', '--local-only'], capture_output=True, text=True)
         print(res.stdout)
         assert 'Verifying environment' in res.stdout
     print('PASS: CLI accepts --project-dir and targets external repo.')
     "@
     ```
  2. Run the automated Spec 11 integration test suite:
     ```powershell
     python -m pytest tests/specs/test_spec_11_decoupled_runner.py
     ```
- Expected: Pre-flight checks execute against the target repository, and the Spec 11 integration test suite passes 100% with exit code 0.

### Gotchas
- On subparsers in `argparse`, declare arguments with `default=argparse.SUPPRESS` to prevent subparser evaluation from overwriting top-level flags.
- Keep backwards compatibility when `--project-dir` is not supplied: default strictly to `Path.cwd().resolve()`.
- Validate path existence and directory type immediately at CLI boundaries (`project_dir.exists()` and `project_dir.is_dir()`), exiting with code 1 and a descriptive message.
