# T120 — Preserve Windows Shell Quoting in Gatekeeper Verification Commands
Status: completed
Completed: 2026-10-27T12:44:30Z
Spec: docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md
Blocked by: None
Security: required
Reasoning: medium

### Requirements
- Ensure Gatekeeper verification commands (`verification.test_cmd` and `verification.build_cmd`) containing embedded double-quoted arguments (such as `python -c "import glob,yaml; ..."`) execute through `cmd.exe /d /s /c` on Windows without Python's `subprocess.list2cmdline` serializer corrupting internal double quotes (`"` -> `\"`).
- Preserve ADR 0016 shell execution semantics: verification commands remain operator-authored shell strings executed via `cmd.exe /d /s /c` on Windows and `/bin/sh -c` on POSIX, with `WindowsJobObject` process-tree assignment and termination, `DEFAULT_STREAM_LIMIT` pipe flow control, concurrent `stderr` draining, and timeout/silence enforcement intact.
- Jump-start orientation: inspect `runner/adapters/cli/subprocess_runner.py` (`SubprocessRunner._prepare_command`, `SubprocessRunner.run`, `SubprocessRunner.spawn`, `SubprocessProcessHandle`), `runner/application/gatekeeper.py` (`resolve_shell`, `build_shell_argv`, `GatekeeperCommandExecutor`), `tests/unit/adapters/test_subprocess_runner.py`, and `tests/unit/application/test_gatekeeper.py`. Verify with `python -m pytest tests/unit/adapters/test_subprocess_runner.py tests/unit/application/test_gatekeeper.py -x`.

### Acceptance Criteria
- When `GatekeeperCommandExecutor.verify` executes on Windows with a real `SubprocessRunner` and a `VerificationConfig` whose `test_cmd` is `python -c "import glob,yaml; fs=glob.glob('*/agents/openai.yaml'); [yaml.safe_load(open(f,encoding='utf-8')) for f in fs]; print('validated %d openai.yaml files' % len(fs))"`, the command exits with code `0`, `report.passed` is `True`, and `stdout` contains `validated` instead of crashing with `SyntaxError: unterminated string literal`.
- Commands containing nested double quotes, single quotes, semicolons, and spaces execute identically on Windows via `SubprocessRunner` to running them in a standard Windows console.
- Windows Job Object assignment (`WindowsJobObject.create()` and `job.assign_process(proc.pid)`), descendant process-tree termination on timeout or silence-window expiry, `DEFAULT_STREAM_LIMIT`, and concurrent `stderr` draining remain functional and covered by tests.
- Security verification: `resolve_shell` continues to resolve `cmd.exe` from `COMSPEC` / `SystemRoot\System32` (never an untrusted workspace binary), non-shell `SubprocessRunner` invocations (`opencode`, `agy`, `git`) continue to use direct `create_subprocess_exec` token lists without shell interpolation, and shell execution is restricted to the explicit platform shell wrapper (`cmd.exe /d /s /c`).

### Gotchas
- On Windows, `asyncio.create_subprocess_exec("cmd.exe", "/d", "/s", "/c", command)` passes the argument list through `subprocess.list2cmdline`, which wraps `command` in outer quotes and turns every internal `"` into `\"`. Because `cmd.exe` does not treat `\"` as an escape sequence, child binaries receive literal `\"` characters and split arguments on internal whitespace.
- If routing `cmd.exe /d /s /c` invocations through `asyncio.create_subprocess_shell` (or passing a raw command line on Windows), ensure `cmd.exe /d /s /c "<command>"` outer-quote stripping rules (`/s /c` strips the first and last quote character while preserving inner quotes) are respected when `command` starts or ends with quotes.
