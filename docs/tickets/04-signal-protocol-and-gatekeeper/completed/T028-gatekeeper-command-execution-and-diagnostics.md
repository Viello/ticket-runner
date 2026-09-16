# T028 — Gatekeeper command execution and diagnostics capture
Status: completed
Completed: 2026-09-16T16:29:27Z
Security: required
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: none

### Requirements
- Add the Gatekeeper's command executor: given `VerificationConfig`, run `build_cmd` then `test_cmd` sequentially, each as a shell command string through the platform shell (`cmd.exe /d /s /c` on Windows, `/bin/sh -c` on POSIX), each bounded by its own `timeout_seconds`.
- Pass/fail contract: a command passes only on exit code 0; a failing or timed-out non-empty `build_cmd` skips `test_cmd`; an empty `build_cmd` is skipped silently and is never a failure.
- Timeout contract: spawn via `CommandRunner.spawn` and wait under a timeout; on expiry terminate the process tree through the handle and mark the command timed out.
- Diagnostics contract: failed and timed-out commands contribute `$ <command>`, a status line (exit code or timeout), and the final 100 lines of that command's stdout followed by its drained stderr, shaped for injection into the Worker session.
- Pin the public result shape consumed by T031: `VerificationReport(passed, results, diagnostics, skipped_commands)` and per-command `CommandOutcome(label, command, exit_code | None, timed_out, tail)`.
- Jump-start:
  - Files to touch: `runner/application/gatekeeper.py` (new), `tests/unit/application/test_gatekeeper.py` (new).
  - Seams: `CommandRunner.spawn` and `ProcessHandle`, `VerificationConfig.timeout_seconds`, platform shell selection.
  - Anchor patterns: stream reading, termination ladder, and concurrent stderr draining in `runner/application/worker_supervisor.py`; fake sequencing via `register_spawn` in `tests/fakes/fake_command_runner.py`.
  - Verification: `pytest tests/unit/application/test_gatekeeper.py`.

### Acceptance Criteria
- Fake-driven tests prove build-then-test order, per-command timeout application, platform-correct shell argv, and `passed` semantics: build failure skips tests with `skipped_commands` populated; test failure reports both command tails.
- A fake handle registered with a delay longer than the timeout is terminated (the fake records `terminated`) and reported `timed_out=True` with a timeout status line.
- Diagnostics contain the command header plus exactly the trailing 100 lines across stdout then stderr when output exceeds 100 lines.
- At least one test dispatches through the real `SubprocessRunner` on the host platform (skipped elsewhere) proving the shell wrapper executes a trivial exit-code command.
- Passing reports carry empty `diagnostics`; the report always lists per-command outcomes.

### Gotchas
- `CommandRunner.run` has no timeout — use `spawn`; pass `stdin=DEVNULL` (Windows handle-duplication gotcha) and strip CRLF from streamed lines.
- On Windows, `cmd.exe` resolution and process-tree termination follow the existing adapter gotchas.
- Precise stdout/stderr interleaving is not available on the port; document the stdout-tail-then-stderr ordering in the result.
- Security: the command string comes only from `config.yaml` (trusted operator); no Ticket or Worker data interpolates into commands; no extra `shell=True`; cwd and environment pass through unchanged.
