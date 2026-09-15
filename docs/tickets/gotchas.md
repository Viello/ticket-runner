# Global Gotchas & Lessons Learned

A chronological record of runtime quirks, platform pitfalls, and architectural lessons discovered during ticket implementations. Subsequent ticket sessions ingest these lessons to prevent recurring mistakes.

---

### Windows Subprocess Executable Resolution
- **Problem**: Calling `asyncio.create_subprocess_exec` on Windows fails with `FileNotFoundError` when executing scripts or binary names without explicit file extensions (`.exe`, `.cmd`, `.bat`).
- **Solution**: Resolve the binary path beforehand using `shutil.which(cmd[0])` before dispatching to `create_subprocess_exec`, and ensure the process runs on `asyncio.ProactorEventLoop`.

### Windows Subprocess Standard Handle Duplication
- **Problem**: Running `subprocess.run(..., capture_output=True)` inside background tasks or PowerShell subshells on Windows can raise `OSError: [WinError 6] The handle is invalid` when Python attempts to duplicate an unassigned `stdin` handle.
- **Solution**: Always pass `stdin=subprocess.DEVNULL` explicitly to `subprocess.run` or `subprocess.Popen` whenever standard input is not actively consumed.

### POSIX Shell Hook Newlines on Windows
- **Problem**: Git for Windows bundled `sh.exe` fails with syntax parsing errors or `/bin/sh^M: bad interpreter` when executing shell scripts that contain Windows CRLF (`\r\n`) line endings.
- **Solution**: Author and write all shell scripts and git hook templates with explicit POSIX LF (`\n`) line endings via `write_text(..., encoding="utf-8", newline="\n")`.

### Non-Destructive Git Hook Preservation
- **Problem**: Overwriting existing hook files in `.git/hooks/` destroys pre-existing developer or repository hook logic.
- **Solution**: Check for unique signature delimiters (`# BEGIN TICKET RUNNER GUARDRAIL` and `# END TICKET RUNNER GUARDRAIL`) before writing; if missing, non-destructively append the guardrail block to the end of the existing file and ensure executable permissions (`0o755`).

### Git Status Porcelain Untracked Files and Runtime Isolation
- **Problem**: `git status --porcelain` includes untracked files with prefix `??`, causing runtime directories (such as `.agent/signals/` or temporary test artifacts) to trigger false dirty-tree failures.
- **Solution**: Explicitly add `.agent/` and all ephemeral runtime directories to `.gitignore` at repository root so working tree cleanliness checks only track meaningful workspace modifications.

### Asyncio Unit Testing Without Pytest-Asyncio Plugin
- **Problem**: Marking unit test functions with `@pytest.mark.asyncio` when `pytest-asyncio` is not installed causes tests to fail with `async def functions are not natively supported`.
- **Solution**: Define test functions as synchronous `def test_...()` and invoke asynchronous coroutines directly with `asyncio.run(...)` for deterministic, zero-dependency test execution.

### Bot Secret Credential Isolation in Configuration
- **Problem**: Embedding raw API keys or bot tokens directly inside `config.yaml` risks accidental commits of credentials into git history.
- **Solution**: Restrict configuration files to specify the environment variable name (`token_env: "DISCORD_BOT_TOKEN"`), validate that the value is an environment variable identifier, and strictly reject raw tokens or forbidden secret keys (`token`, `bot_token`, `secret`, `api_key`).

### Windows Console Unicode Output Encoding (cp1252)
- **Problem**: Printing Unicode status symbols such as `✓` (`\u2713`) or `✗` (`\u2717`) on Windows default consoles (`cp1252`) raises `UnicodeEncodeError: 'charmap' codec can't encode character`.
- **Solution**: Reconfigure `sys.stdout` and `sys.stderr` via `reconfigure(encoding="utf-8", errors="replace")` where available, verify encoding support dynamically, and provide safe plain-text fallback markers (`[PASS]` / `[FAIL]`) when Unicode encoding is unavailable.

### Strictly Read-Only Pre-Flight Verification
- **Problem**: Automated pre-flight health checks that attempt auto-remediation (such as auto-stashing, auto-committing, or modifying files) risk destroying uncommitted developer work or violating user trust.
- **Solution**: Enforce strict read-only execution in pre-flight checks: inspect prerequisites, halt immediately on failure, and output actionable remediation instructions without altering workspace state.

