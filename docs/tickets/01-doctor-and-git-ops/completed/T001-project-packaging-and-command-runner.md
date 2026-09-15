# T001 — Project packaging, domain exceptions, and CommandRunner seam
Status: completed
Completed: 2026-09-15T07:38:11Z
Commit: 41c2d23748562a0b26cef051f347c1d52a4c33da
Spec: docs/specs/01-doctor-and-git-ops.md

### Requirements
- Set up Python packaging and dependency configuration in `pyproject.toml` and `requirements.txt` targeting Python 3.11+, declaring dependencies (`pytest`, `pyyaml`, `rich`, `discord.py`).
- Create root `.gitignore` ignoring `.agent/`, `__pycache__/`, `.pytest_cache/`, and Python virtual environments.
- Implement the root domain exception hierarchy in `runner/domain/exceptions.py` with `TicketRunnerError` as base, and derived errors `DoctorError`, `GitError`, `ConfigError`, and `CommandNotFoundError`.
- Define the `CommandRunner` abstract protocol in `runner/ports/command_runner.py` specifying `CommandResult` dataclass (`exit_code`, `stdout`, `stderr`) and async execution method `run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult`.
- Implement `SubprocessRunner` adapter in `runner/adapters/cli/subprocess_runner.py` wrapping `asyncio.create_subprocess_exec`, resolving executable paths using `shutil.which(cmd[0])` to safely handle Windows `.cmd`/`.bat`/`.exe` binaries, and raising `CommandNotFoundError` if unresolved.
- Implement `FakeCommandRunner` test double in `tests/fakes/fake_command_runner.py` supporting deterministic exit code/stdout/stderr registrations and recording executed command invocations.
- Jump-start:
  - Files to touch: `.gitignore`, `pyproject.toml`, `requirements.txt`, `runner/domain/__init__.py`, `runner/domain/exceptions.py`, `runner/ports/__init__.py`, `runner/ports/command_runner.py`, `runner/adapters/__init__.py`, `runner/adapters/cli/__init__.py`, `runner/adapters/cli/subprocess_runner.py`, `tests/__init__.py`, `tests/conftest.py`, `tests/fakes/__init__.py`, `tests/fakes/fake_command_runner.py`, `tests/unit/adapters/test_subprocess_runner.py`.
  - Seams: `runner/ports/command_runner.py:CommandRunner`.
  - Anchor patterns: ADR 0006 (`CommandRunner` protocol) and ADR 0009 (Clean Architecture directory layout).
  - Verification: `pytest tests/unit/adapters/test_subprocess_runner.py`.

### Acceptance Criteria
- `pyproject.toml` and `requirements.txt` are valid and specify all core dependencies and pytest configuration.
- `TicketRunnerError` is the root exception class; `DoctorError`, `GitError`, `ConfigError`, `CommandNotFoundError` inherit from it.
- `CommandRunner` protocol provides a clear, typed async interface for executing CLI commands.
- `SubprocessRunner` correctly captures stdout, stderr, and return codes from external commands, resolving executables on Windows.
- `FakeCommandRunner` enables deterministic testing by mapping commands to scripted outputs without OS calls.
- Unit tests verify both `SubprocessRunner` and `FakeCommandRunner`.

### Gotchas
- On Windows, `asyncio.create_subprocess_exec` requires `asyncio.ProactorEventLoop` (default in Python 3.8+). Running scripts or non-executable binaries directly without resolving `.exe` or calling via shell can raise `FileNotFoundError`.
