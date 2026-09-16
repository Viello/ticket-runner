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

### Preserving Ticket Line Endings During Rewrites
- **Problem**: `Path.read_text()` and `Path.write_text()` normalize CRLF to LF, silently rewriting CRLF-authored ticket files; the `newline` parameter only exists on `Path.read_text()` from Python 3.13 while the project targets 3.11+.
- **Solution**: Read and write ticket markdown through `path.open(..., encoding="utf-8", newline="")` and rebuild files from `splitlines(keepends=True)` so only the targeted header metadata lines change and every other byte round-trips unchanged.

### Atomic Writes Must Clean Up on Every Failure Path
- **Problem**: The sibling `.tmp` + `os.replace` pattern fails on Windows with `PermissionError` when an editor holds the target open; narrowing cleanup to `OSError` leaves stray `.tmp` files behind on encoding or programming failures.
- **Solution**: In `atomic_write_text`, catch any exception, delete the sibling `.tmp` best-effort, then re-raise; the ticket serializer wraps the failure in `TicketFormatError` with editor-closed guidance, and `*.tmp` is git-ignored so `git add .` can never stage a leftover.

### Spec Linkage Inference for Archived Tickets
- **Problem**: Inferring `docs/specs/<parent-directory-slug>.md` breaks for relocated tickets under `completed/`, resolving to the nonsensical `docs/specs/completed.md`.
- **Solution**: When the `Spec:` header is omitted and the parent directory is the archive folder (`completed/`), infer the spec slug from the grandparent directory instead.

### Numeric Sorting of Ticket Identifiers
- **Problem**: Lexicographical string sorting of ticket identifiers causes higher-numbered tickets like `T010` to order before `T002` or `T009` when padding or digit counts vary, violating queue sequentiality.
- **Solution**: Extract the numeric sequence from the ticket identifier (`int(re.search(r"\d+", id).group())`) and sort numerically so that `T009` strictly precedes `T010`.

### Archive Folder Pruning During Queue Scans
- **Problem**: Recursive scans (`rglob`) inadvertently traverse into `completed/` subfolders and resurrect archived tickets as pending.
- **Solution**: Restrict scans to direct children of spec directories (`f.is_file()`), prune any folder named `completed` or starting with `.`, and skip runtime artifacts (`.queue.lock`, `*.tmp`, `gotchas.md`).

### Ticket Header Tolerance for Concise Format
- **Problem**: Minimal ticket headers such as `# T001` authored during pre-flight checks fail strict `# T<NNN> — <Title>` regex patterns.
- **Solution**: Make the title separator and text optional in the header pattern (`HEADER_PATTERN`), falling back to the ticket ID as the title when omitted.

### Windows File Locking Byte Range and File Mode
- **Problem**: `msvcrt.locking` locks bytes starting from the current file position; unpositioned locks or improper file opening modes fail to lock empty sentinel files or raise sharing errors.
- **Solution**: Open the sentinel in binary append-update mode (`a+b`) to guarantee creation without truncation, seek explicitly to byte offset 0, and lock a fixed 1-byte length non-blocking (`msvcrt.LK_NBLCK`).

### Immediate Handle Cleanup on Lock Conflict
- **Problem**: When a second process or instance fails to acquire an OS file lock on Windows, leaving the opened file handle unclosed blocks subsequent file deletion or replacement.
- **Solution**: Wrap lock acquisition in a `try...except` block that immediately closes the opened file handle and resets references if OS locking raises `PermissionError`, `BlockingIOError`, or `OSError`.

### Platform-Branching for POSIX and Windows Locking Primitives
- **Problem**: Unconditional imports of `fcntl` crash on Windows with `ModuleNotFoundError`, while POSIX systems lack `msvcrt`.
- **Solution**: Branch at import and execution time: use `msvcrt.locking` when `sys.platform == "win32"` and lazily import `fcntl` on POSIX systems, ensuring universal cross-platform compatibility.

### Gitignoring Sentinel Lock Files
- **Problem**: Sentinel lock files created during orchestrator runs dirty the git tree and cause pre-flight cleanliness checks or Gatekeeper `git add .` operations to stage runtime artifacts.
- **Solution**: Add `docs/tickets/.queue.lock` and `.queue.lock` directly to root `.gitignore` so OS lock sentinels never appear in `git status --porcelain`.

### Non-Destructive Gotchas Normalization
- **Problem**: Normalizing freeform gotchas into structured markdown risks corrupting entries that already contain markdown or rewriting worker-authored nuance.
- **Solution**: Detect existing markdown headings and bullet formats before applying transformations, preserving pre-existing markdown intact and deriving concise titles without modifying worker detail.

### Scoped Read-Modify-Write Window
- **Problem**: In-memory caching of gotchas or long-lived store instances can clobber external developer edits made to `docs/tickets/gotchas.md` while the runner is paused.
- **Solution**: Scope the read-modify-write cycle strictly to the invocation of `append()`, loading fresh content from disk immediately prior to deduplicating and atomic writing.

### Windows Path.write_text CRLF Auto-Conversion
- **Problem**: In test suites on Windows, `Path.write_text()` automatically translates `\n` to `\r\n`, causing test assertions checking exact byte equality or LF line endings against raw file handles to fail unexpectedly.
- **Solution**: In tests verifying raw file contents and line endings, write fixture content using `path.open("w", encoding="utf-8", newline="")` to disable automatic platform CRLF translation.

### Volume-Atomic Relocation with Cross-Volume Fallback
- **Problem**: Naive `shutil.move` or copy-then-delete patterns during ticket finalization leave orphaned `.tmp` or partial file copies behind if interrupted, polluting active queue scans.
- **Solution**: Execute ticket file moves via atomic `os.replace` within the same volume, wrapping with a `shutil.move` fallback only if cross-volume `OSError` arises, ensuring immediate clean removal from active directory scans.

### Collision Safety for Ticket Archival
- **Problem**: Moving a completed or skipped ticket into `completed/` when an archived file of the same name already exists silently overwrites historical records with `os.replace`.
- **Solution**: Explicitly check destination existence before modifying source files and raise `TicketFormatError` without altering source or destination files, protecting completion history from data loss.

### Single-Commit Ordering Pipeline
- **Problem**: `GitOperations.commit_ticket` stages all modifications across the repository via `git add .`; relocating tickets or appending gotchas out of order or after committing either leaves working tree changes unstaged or causes broken commits.
- **Solution**: Strictly sequence finalization steps in the orchestrator before calling `commit_ticket`: first relocate the ticket markdown file with updated completion metadata into `completed/`, then append newly emitted gotchas to `gotchas.md`, and finally stage and author the atomic commit.

### Working Tree Reset Preceding Skipped Ticket Archival
- **Problem**: Calling `GitOperations.reset_working_tree()` (`git reset --hard HEAD` and `git clean -fd`) after relocating a skipped ticket into `completed/` deletes or reverts the newly archived ticket file, losing the recorded failure reason.
- **Solution**: Execute `reset_working_tree()` first to discard uncommitted worker trial edits, and only then relocate the ticket to `completed/` with `Status: skipped` and failure details.

### Sentinel Lock Handle Closure on Pause
- **Problem**: Merely toggling a boolean pause flag without closing the OS file handle on `docs/tickets/.queue.lock` prevents external text editors on Windows from opening or modifying queue files due to file sharing violations (`ERROR_SHARING_VIOLATION`).
- **Solution**: Explicitly release the OS file lock and close the underlying file handle inside `pause()`, and re-open and re-acquire the non-blocking sentinel lock inside `resume()`.

### Doctor Queue Validation vs Runner Standby Lifecycle
- **Problem**: Doctor pre-flight validation treats zero pending tickets as a failure (Spec 01 US 03), preventing `ticket_runner.py start` on an empty directory from proceeding directly to the standby watch loop. Weakening Doctor to allow an empty queue undermines early sanity checking.
- **Solution**: Maintain strict separation of concerns: Doctor pre-flight checks are read-only sanity checks that require pending tickets to catch configuration errors before dispatching work, while the standby lifecycle handles queue exhaustion that occurs *during* an active run as tickets drain.

### Standby Polling Event Loop Yielding and Lock Invariants
- **Problem**: Long polling sleep in standby can block asynchronous event loops or leave the sentinel file lock acquired while waiting, which causes external editors to hit `ERROR_SHARING_VIOLATION` on Windows when trying to add new ticket files.
- **Solution**: Always release the sentinel file lock upon queue exhaustion before entering standby mode, yield execution between polls with `await asyncio.sleep(poll_interval)`, and wrap lifecycle loops in `try...finally: self.release_lock()` to ensure handles are freed on task cancellation.
