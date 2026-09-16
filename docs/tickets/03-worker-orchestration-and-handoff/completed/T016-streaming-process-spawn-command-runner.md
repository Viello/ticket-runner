# T016 — Streaming process spawn on the CommandRunner seam
Status: completed
Completed: 2026-09-16T10:00:24Z
Security: required
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Extend `runner/ports/command_runner.py` with a `spawn()` method returning a running-process handle that supports async line iteration over stdout, concurrent stderr draining, `terminate()`, and `wait()` returning the exit code. Keep the existing buffered `run()` untouched for git/doctor/gatekeeper callers.
- Implement the spawn path in `runner/adapters/cli/subprocess_runner.py`: resolve the binary via `shutil.which` (Windows executable-resolution gotcha), pass `stdin=DEVNULL` (opencode blocks at startup when stdin is a non-TTY pipe — see gotchas.md), separate stdout/stderr pipes, and terminate via `taskkill /PID <pid> /T /F` on Windows (descendant cleanup) with `terminate()` fallback, SIGTERM on POSIX.
- Teach `tests/fakes/fake_command_runner.py` to serve scripted stdout lines, scripted stderr, exit codes, and to record spawns with their argv — the deterministic substitute for every later Spec 03 ticket.
- Add an opt-in live smoke test (skipped unless `TICKET_RUNNER_LIVE=1`) that runs a trivial `opencode run --format json "<prompt>"` through the real adapter, asserts every stdout line parses as JSON and carries a `sessionID`, and consumes the process to a clean exit.
- Security: required — this ticket opens the process-spawning boundary and the kill path. Explicitly verify: argv passed as a list (never a shell string), stdin closed, kill targets only the spawned PID tree, no user-controlled value influences binary resolution, and stderr draining cannot deadlock on a flooding child.
- Jump-start:
  - Files to touch: `runner/ports/command_runner.py`, `runner/adapters/cli/subprocess_runner.py`, `tests/fakes/fake_command_runner.py`, `tests/unit/adapters/test_subprocess_runner.py`, new `tests/unit/adapters/test_live_opencode_smoke.py`.
  - Seams: `CommandRunner` protocol (ADR 0006); `SubprocessRunner.run` lines 17–77 show resolution/env/decoding conventions to mirror.
  - Anchor patterns: `tests/unit/adapters/test_subprocess_runner.py` protocol-conformance assertions and `asyncio.run` usage (no pytest-asyncio in this repo).
  - Verification: `pytest tests/unit/adapters/test_subprocess_runner.py`; live smoke: `TICKET_RUNNER_LIVE=1 pytest tests/unit/adapters/test_live_opencode_smoke.py`.

### Acceptance Criteria
- `isinstance(SubprocessRunner(), CommandRunner)` still holds and both fake and real adapter satisfy the extended protocol (runtime-checkable assertion in tests).
- Fake-driven tests prove: lines arrive in order with line endings stripped, exit codes propagate through `wait()`, `terminate()` ends the process within a bounded wait, and a child flooding stderr while stdout is read slowly does not deadlock.
- The live smoke test skips cleanly without the env var and, when enabled, passes against the installed OpenCode CLI (v1.18.x at time of writing) without hanging.
- Security verification: recorded spawn argv is a list; stdin is `DEVNULL` or closed; termination targets the child PID tree only.

### Gotchas
- OpenCode emits JSONL with `\r\n` line endings on Windows — the handle must strip them.
- The npm shim resolves to `opencode.CMD`; mirror however `Doctor.check_opencode` successfully runs `opencode --version` rather than inventing a new resolution path.
- `asyncio.create_subprocess_exec` needs the Proactor event loop on Windows; tests drive coroutines with `asyncio.run`.
- Do not decode OpenCode events here beyond the smoke assertion — event decoding lands in T019.
