# T037 — CMD PATH resolution defense-in-depth
Status: completed
Completed: 2026-09-17T12:37:25Z
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T036

### Requirements
- Resolve the leading token of each non-empty operator-authored verification command (`verification.test_cmd`, `verification.build_cmd`) via `shutil.which` in `GatekeeperCommandExecutor._execute()` (runner/application/gatekeeper.py) before `build_shell_argv()` wraps it in `cmd.exe /d /s /c`. Only the leading token (before the first space) is resolved, never the full wrapped command string. Known `cmd.exe` builtins are skipped so the check never false-positives on shell control words.
- On resolution failure, surface the failure as a command-not-found diagnostic in Gatekeeper output — distinguishable from an exit-code-1 test failure — so "binary missing" is never mistaken for "tests failed".
- Add a Doctor check (`check_verification_commands`) wired into `Doctor.run()` (runner/application/doctor.py): once config loads, resolve the leading token of non-empty `test_cmd` and `build_cmd`; on failure report an actionable remediation (e.g. "pytest not found on PATH — use `python -m pytest` instead").
- Update the tracked template `config.example.yaml` to `test_cmd: "python -m pytest"`. The local, gitignored `config.yaml` is already fixed; bare `pytest` is not on this machine's PATH and made the Gatekeeper fail.
- Record ADR-0019 (`docs/adr/0019-portable-verification-command-forms.md`): verification commands use portable invocation forms (`python -m <tool>` over bare script names).
- Append a gotcha to `docs/tickets/gotchas.md`: Gatekeeper commands run via `cmd.exe /d /s /c` and inherit the runner's PATH, which may not include the Python Scripts directory — use `python -m <tool>` forms for portability.

### Acceptance Criteria
- Doctor fails with an actionable remediation message when `test_cmd`'s leading token is unresolvable, and passes when it resolves (e.g. `python -m pytest`).
- Gatekeeper reports an unresolvable verification command as a command-not-found diagnostic distinct from a plain exit-code-1 failure.
- `config.example.yaml` uses `python -m pytest`.
- Full pytest suite is green.

### Gotchas
- Resolve only the leading token of the user-configured command, never the whole string `build_shell_argv` wraps in `cmd.exe /c`.
- `shutil.which` on Windows respects `PATHEXT`, trying `.exe`, `.cmd`, and `.bat` automatically.
- `config.yaml` is gitignored (local runtime file); `config.example.yaml` is the tracked template.
- `SubprocessRunner._prepare_command` (runner/adapters/cli/subprocess_runner.py) already resolves its argv with `shutil.which` and raises `CommandNotFoundError`; that path needs no further work. This ticket targets the shell-wrapped Gatekeeper command string and Doctor startup validation.