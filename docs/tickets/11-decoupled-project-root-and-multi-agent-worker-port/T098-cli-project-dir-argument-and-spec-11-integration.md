# T098 — CLI `--project-dir` Argument Plumbing and Spec 11 Integration Suite
Status: pending
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
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
- Setup: A clean external git repository in a temp directory containing sample tickets and `config.yaml`.
- Why: Confirm that the operator can execute `ticket-runner --project-dir <path> doctor` and `start` from any arbitrary directory.
- Steps:
  1. Run PowerShell verification executing `python ticket_runner.py --project-dir <temp_dir> doctor`:
     ```powershell
     python -c @"
     import subprocess, sys, tempfile
     from pathlib import Path
     with tempfile.TemporaryDirectory() as tmp:
         target = Path(tmp).resolve()
         subprocess.run(['git', 'init'], cwd=target, check=True, stdout=subprocess.DEVNULL)
         res = subprocess.run([sys.executable, 'ticket_runner.py', '--project-dir', str(target), 'doctor', '--local-only'], capture_output=True, text=True)
         print(res.stdout)
         print(res.stderr)
         # Should successfully invoke doctor on external target
         assert 'Verifying environment' in res.stdout
     print('PASS: CLI accepts --project-dir and targets external repo.')
     "@
     ```
  2. Run `pytest tests/specs/test_spec_11_decoupled_runner.py`.
- Expected: CLI runs pre-flight checks against the target repository, integration suite passes with exit code 0.

### Gotchas
- Keep backwards compatibility when `--project-dir` is not supplied: default strictly to `Path.cwd().resolve()`.
