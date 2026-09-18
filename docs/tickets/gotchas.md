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

### Gotchas Store Skeleton Reset Line Ending and Directory Creation
- **Problem**: In isolated test workspaces where `docs/tickets/gotchas.md` parent directories do not yet exist, atomic writes raise `FileNotFoundError`, and stripping line endings with `splitlines()` truncates the final trailing newline of `DEFAULT_SKELETON`, causing byte-for-byte mismatches against the canonical markdown skeleton.
- **Solution**: Explicitly create parent directories with `self._path.parent.mkdir(parents=True, exist_ok=True)` prior to atomic writes, and append a trailing `newline` delimiter to the relined skeleton.

### Non-Interactive Terminal Prompt Fallback Safety
- **Problem**: Calling standard `input()` for clean-slate interactive confirmation during test suite runs, headless pipelines, or non-interactive environments raises `OSError: reading from stdin while output is captured`.
- **Solution**: Catch `OSError` alongside `EOFError` and `KeyboardInterrupt` in `default_terminal_confirmation`, safely defaulting to `False` (preserving the working tree) whenever interactive stdin is unavailable.

### Clean-Slate Scope Protection During Empty Queue Runs
- **Problem**: Scanning all directory entries under `docs/tickets/` upon queue exhaustion when no tickets were processed in the active session risks prompting or executing accidental cleanup of unworked or unrelated spec directories.
- **Solution**: Restrict clean-slate targets strictly to an explicitly configured `spec_slug` or spec directories that had tickets actively processed in the running session (`_processed_spec_slugs`).

### Parser Metadata Tolerance for Unknown Security Values
- **Problem**: Rejecting or raising format errors on non-standard `Security:` metadata values (such as `Security: optional`, `Security: none`, or omitted lines) breaks backward compatibility with existing tickets and tightly couples queue scanning to rigid review configurations.
- **Solution**: Follow repo metadata tolerance conventions by only resolving exact case-insensitive matches for `Security: required` (with whitespace stripping) to `True`, safely defaulting missing lines and all alternative values to `False` without raising.

### Safe Parent Directory Creation for Relative Paths
- **Problem**: Calling `Path(path).parent.mkdir(parents=True, exist_ok=True)` on a filename in the current working directory (where `Path("file.txt").parent == Path("")`) raises `FileNotFoundError: [WinError 3] The system cannot find the path specified: ''` on Windows.
- **Solution**: Guard parent directory creation in `RuntimePaths.ensure_parent_dir` by checking `if str(parent) not in ("", ".")` before dispatching to `mkdir()`.

### Pure Path Object Instantiation Without Disk Side-Effects
- **Problem**: Initializing path configuration value objects that eagerly invoke directory creation (`mkdir`) causes import-time and test-time side-effects, polluting clean worktrees or tripping git cleanliness checks.
- **Solution**: Keep `RuntimePaths` as a pure value object computing immutable `Path` representations, exposing explicit `ensure_*` helper methods that callers invoke only on demand when ready to write.

### Windows Process Tree Termination via Taskkill
- **Problem**: Calling standard `proc.terminate()` on Windows only terminates the root wrapper process (such as `cmd.exe` executing an `opencode.cmd` npm shim), leaving descendant runtime child processes (such as `node.exe`) running as orphaned background processes holding open network ports and file locks.
- **Solution**: Execute process tree termination via `taskkill /PID <pid> /T /F` on Windows when terminating spawned subprocesses, falling back to direct `proc.terminate()` only if `taskkill` fails or process lookup raises.

### Concurrent Stderr Draining to Prevent Subprocess Pipe Deadlocks
- **Problem**: Reading standard output incrementally with `readline()` while a child process emits high volumes of stderr causes the OS pipe buffer (4KB–64KB) to fill up, deadlocking the child process and stalling stream consumption indefinitely.
- **Solution**: Launch a concurrent asynchronous background task (`_drain_stderr`) immediately upon process spawn that continuously drains `proc.stderr` in non-blocking chunks into an in-memory buffer until EOF.

### Stripping CRLF Line Delimiters in JSON Streaming
- **Problem**: CLI tools like OpenCode running on Windows emit JSONL streaming events ending with CRLF (`\r\n`), causing naive `\n` line stripping or strict line parsing assertions to preserve trailing `\r` carriage returns.
- **Solution**: Always strip trailing CRLF explicitly using `.rstrip("\r\n")` on decoded stream lines before yielding to callers.

### Dual Class and Instance Builder Method Dispatch
- **Problem**: Decorating builder entrypoints with `@classmethod` prevents access to instance attributes when called on configured instances, while regular methods require instantiation and fail when called directly on the class.
- **Solution**: Implement a lightweight descriptor (`_BuildDispatcher`) that inspects whether the method was accessed on an instance or owner class, routing to the appropriate bound or unbound builder callable.

### Verbatim Markdown Passthrough in Pure Prompt Composition
- **Problem**: Attempting to sanitize, escape, or reformat pre-authored ticket requirements and acceptance criteria in prompt templates corrupts verbatim code snippets, regular expressions, and markdown syntax.
- **Solution**: Pass ticket content strings through verbatim into the prompt template without escaping, while deterministically normalizing bullet points and section headers.

### Provider Token Context-Occupancy Under-Counting
- **Problem**: In LLM JSON streams (such as OpenCode per-step provider events), `tokens.input` represents only non-cached input tokens and excludes `cache_read` and `cache_write`. Summing only `input + output` severely underestimates context window occupancy and causes the orchestrator to miss warning and handoff thresholds.
- **Solution**: Calculate context occupancy using `total` when present, otherwise compute the complete sum of `input + output + reasoning + cache_read + cache_write` per ADR 0015 to ensure cache creation and reads are properly budgeted.

### Multi-Threshold Priority and Reminders Suppression
- **Problem**: When a single token update or resumed session jumps across multiple budget thresholds at once (such as leaping from below 120k directly past 135k or 150k), independent threshold conditions can emit lower-priority actions or leave lower thresholds armed to trigger redundant warnings later.
- **Solution**: Evaluate thresholds in descending priority order (`CEILING` > `HANDOFF` > `WARN`) and immediately mark lower-level reminders as already sent (`_warn_sent = True`, `_handoff_sent = True`) when a higher threshold is crossed, preserving monotonic single-fire semantics.

### OpenCode Live Event Stream Token Structure and Cache Metrics
- **Problem**: In OpenCode v1.18.x `--format json` streaming events, `step_finish` encapsulates token metrics within a nested `part.tokens` dictionary where cache metrics are nested further as `tokens.cache.read` and `tokens.cache.write` rather than flat fields, while older or alternate formats emit flat `tokens` dictionaries.
- **Solution**: Extract token telemetry flexibly by checking `part.tokens` before falling back to top-level `tokens`, and unpack `cache.read`/`cache.write` from nested dictionaries to guarantee accurate `TokenUsage` and context occupancy calculations.

### Untrusted Session ID Path Containment and Allowlist Guardrails
- **Problem**: Session IDs learned directly from untrusted streaming subprocess output can contain directory traversal sequences (`../../`) or invalid filesystem characters, risking arbitrary file creation or log clobbering outside `.agent/logs/`.
- **Solution**: Strictly sanitize session IDs against `^ses_[A-Za-z0-9]+$` before constructing any filesystem path, verify that resolved log paths are strictly contained within `logs_dir` via `Path.is_relative_to()`, and drop log creation while emitting a diagnostic if validation fails.

### Session Stream Line Buffering Preceding Session ID Discovery
- **Problem**: In newly spawned OpenCode sessions, the session identifier is unknown prior to execution and only learned from the first streamed event's `sessionID` field; attempting immediate log file creation before receiving the first event causes missing or misplaced log streams.
- **Solution**: Buffer initial stdout lines in memory until the first valid session ID is decoded and validated, then atomically open the session log in append mode (`open(..., "a", newline="")`) and flush the buffered lines before proceeding with streaming writes.

### Async Stream Cancellation and Drain Race Invariants
- **Problem**: When waiting concurrently on the next stdout stream line and external kill events with `asyncio.wait(..., return_when=FIRST_COMPLETED)`, abandoning the stream reader task without cancellation or proper draining leaves unconsumed or pending tasks running in the event loop background, and can miss writing the final buffered output line that completed concurrently with the interrupt.
- **Solution**: Explicitly cancel and suppress exceptions on pending tasks upon `FIRST_COMPLETED`, inspect whether the line read task completed simultaneously before termination ladder execution, and persist any retrieved line to the active session log before exiting.

### Injected Time Delta Evaluation vs Clock Sampling Latency
- **Problem**: Evaluating stall and wall-clock timeouts solely prior to initiating `asyncio.wait()` causes elapsed silence or deadline violations that occur during chunk generation to be masked if the stream producer advances an injected clock immediately prior to yielding a line, updating `last_line_time` without ever evaluating the duration of the preceding silent gap.
- **Solution**: Compute and evaluate elapsed silence `arrival_time - last_line_time` and wall-clock duration `arrival_time - start_time` both before initiating the bounded wait and immediately upon receipt of the next completed line, triggering `RunTerminationReason.STALLED` if the silence window was exceeded.

### Dual Sync and Async Callable Protocol for External Interrupt APIs
- **Problem**: Implementing external interrupt APIs (like `request_kill`) as native coroutines (`async def`) causes unawaited invocations from synchronous callbacks (such as budget monitors or telemetry hooks) to fail silently with unhandled `RuntimeWarning: coroutine was never awaited`, while defining them as pure synchronous methods raises `TypeError` when callers in async contexts invoke `await supervisor.request_kill(...)`.
- **Solution**: Implement interrupt methods as synchronous operations setting internal atomic state and an `asyncio.Event`, returning a lightweight custom awaitable object implementing `__await__` that yields immediately to `None`, supporting both synchronous and awaited call sites without warnings or runtime errors.



### Checkpoint Validation After Process Termination
- **Problem**: The worker process may write or flush the checkpoint document only as the instruction run terminates; inspecting the file while the process is still running risks validating partial writes or triggering false missing/stale failures.
- **Solution**: Await full process exit via supervisor.run() before checking checkpoint existence or testing filesystem timestamps.

### Filesystem Timestamp Resolution Slack for Context Handoff
- **Problem**: Filesystem mtime precision can round to the nearest whole second depending on the underlying OS and volume format, which can cause a checkpoint created in the same second as the handoff request to appear timestamped prior to handoff_requested_at.
- **Solution**: Apply a module-scoped 2.0-second clock slack window (CLOCK_SLACK_SECONDS = 2.0) in freshness checks (mtime >= handoff_requested_at - 2.0) and compare strictly using wall-clock epoch timestamps (time.time()).

### Stream-Learned Session IDs for Resumed Invocations
- **Problem**: Invoking opencode run --session with an unlearned or synthetic session ID immediately exits with code 1 (Session not found); inventing synthetic session IDs for resumed handoff runs causes hard process failures.
- **Solution**: Only pass session IDs that were actively decoded from the preceding stream sessionID events and strictly validated against the ^ses_[A-Za-z0-9]+$ allowlist.

### Checkpoint Preservation During Recovery Escalation
- **Problem**: Synthesizing an emergency fallback checkpoint from `git status` and `git diff` during escalation risks clobbering a rich, valid checkpoint authored by the worker in the current cycle if escalation occurred later on Session B.
- **Solution**: Only synthesize and write the emergency checkpoint when no handoff was requested or when checkpoint freshness validation failed in the current cycle (`not (valid_checkpoint_recorded and checkpoint_path.is_file())`), preserving worker-authored architectural notes.

### Deterministic Checkpoint Generation in Async Subprocess Fakes
- **Problem**: Using `asyncio.sleep(0.01)` to pause execution between concurrent tasks to allow mock checkpoint authoring causes test suite race conditions and flaky failures under high CPU load.
- **Solution**: Hook process completion deterministically in `FakeProcessHandle.wait()`, authoring test artifacts synchronously upon process exit before returning the mock exit code.

### Supervisor Budget Monitor State Across Chained Sessions
- **Problem**: In multi-session handoff chains, reusing a `WorkerSupervisor` without resetting its internal `BudgetMonitor` leaves internal latch flags (`_handoff_sent = True`) active from the first session, preventing budget threshold crossings and handoff requests from triggering in subsequent chained sessions.
- **Solution**: Explicitly reset the supervisor's budget monitor (`supervisor.reset_budget_monitor()`) between chained sessions while preserving its configured thresholds and model limits.

### Sequential Process Handle Registration in Subprocess Fakes
- **Problem**: In multi-cycle test suites where consecutive sessions execute the exact same command line (e.g. `opencode run --format json --auto <resume_prompt>`), registering mock spawn handles in a standard dictionary keys by command arguments, causing later cycles to overwrite earlier cycle handles or re-execute the same exhausted handle.
- **Solution**: Enhance command runner test fakes to support sequential queue registration (`register_spawn_sequence`), popping and yielding distinct process handles for each successive spawn matching the command.

### Stderr Sidecar Newline Translation on Windows
- **Problem**: The supervisor writes the stderr sidecar log through `open("a", encoding="utf-8")` without `newline=""`, so Windows text mode translates LF to CRLF; behavioral suites asserting raw stderr bytes against LF-authored fixtures fail with `\r` mismatch even though the JSONL stream log is LF-normalized.
- **Solution**: Normalize stderr sidecar bytes in tests with `.read_bytes().replace(b"\r\n", b"\n")`, and keep `newline=""` on the JSONL stream log so it remains byte-faithful to the stripped stream lines.

### Synthetic Checkpoint Whitespace Stripping
- **Problem**: `format_synthetic_checkpoint` calls `.strip()` on `git status --porcelain` and `git diff --stat` output, silently removing the leading space of the first porcelain entry (e.g. ` M file` becomes `M file`) and the trailing newline, so test oracles reconstructed from raw git stdout never match the written file bytes.
- **Solution**: Build byte-level oracles from the stripped form, or hardcode the fully rendered synthetic checkpoint document in the test instead of reconstructing it from raw command output.

### Self-Referential Test Oracles for Rendered Artifacts
- **Problem**: A behavioral test that compares a written artifact against a string generated by the very same production formatter under test cannot detect formatting regressions; it only proves argument plumbing reached the formatter.
- **Solution**: For byte-for-byte artifact acceptance criteria, hardcode the expected document in the test and compare the file bytes directly against that independent oracle.

### Stale Real-File Test References After Spec Archival
- **Problem**: Clean-slate archival removes completed specs (e.g. `docs/specs/03-worker-orchestration-and-handoff.md`), but unit tests that hard-code a real spec path (`test_extract_excerpt_from_real_spec_03`) then fail `assert SPEC_03_PATH.is_file()`, leaving the full suite red on an otherwise untouched branch and blocking tickets whose acceptance criteria require a green suite.
- **Solution**: Repoint such tests at the active spec under `docs/specs/` and assert only on stable opening sentences of its `## Problem Statement` / `## Solution` sections so prose rewrites do not break the oracle.

### Trailing Z Timestamp Normalization
- **Problem**: `datetime.fromisoformat` rejects trailing `Z` UTC timestamps before Python 3.11 and accepts them natively from 3.11 onward, so whether `value.replace("Z", "+00:00")` is required depends on the interpreter and tests can silently pass on either side of the floor.
- **Solution**: Normalize `Z` to `+00:00` before `fromisoformat` in signal parsing as the version-independent idiom, and pin the UTC offset with an explicit test assertion.

### RecursionError from Deeply Nested Untrusted JSON
- **Problem**: `json.loads` raises `RecursionError`, not `JSONDecodeError`, when untrusted payloads nest arrays or objects beyond the interpreter recursion limit (verified at 20,000 levels on Python 3.14, while 5,000 parsed fine), so a strict parser catching only `JSONDecodeError` leaks a non-domain exception from Worker-authored input.
- **Solution**: Catch `RecursionError` alongside `json.JSONDecodeError` in the signal decoder and re-raise it as `SignalFormatError` with a bounded "payload nesting is too deep" diagnostic.

### Verbatim Question Rewrites Preserve Audit Fields
- **Problem**: Rewriting an answered question Signal by re-serializing the parsed `QuestionSignal` entity drops unknown extra fields and normalizes the original timestamp text (e.g. a trailing `Z` becomes `+00:00`), silently changing audit data beyond the single `status`/`answer` flip.
- **Solution**: Validate the payload through `QuestionSignal.parse` first, then patch `status` and `answer` into the raw JSON mapping loaded from disk and write that through the atomic helper; validating before the write also guarantees a blank answer can never reach disk.

### Temp Sidecar Cleanup in Signal Artifacts
- **Problem**: The atomic writer cleans up its own failures, but a hard process kill mid-write can leave `{ticket_id}_ready.json.tmp` or `{ticket_id}.json.tmp` sidecars that violate the "never leaves partial files" purge contract if only the artifact files are deleted.
- **Solution**: Delete each Signal artifact together with its sibling carrying `TEMP_SUFFIX` (imported from `runner.adapters.markdown.atomic_write`) in both `purge` and `consume_ready`, tolerating `FileNotFoundError` so absent files or directories remain no-ops.

### Bounding Subprocess Deadlines Across Output and Exit
- **Problem**: Wrapping only stdout consumption in `asyncio.wait_for` bounds the drain but leaves `handle.wait()` unbounded, so a command that closes stdout while its process lingers can stall verification past `timeout_seconds`; `wait_for` also cancels the drain task on expiry, discarding output already buffered in the pipe before termination. The fake test double models runtime as stdout delay, so a wait-only bound never trips it.
- **Solution**: Await the drain task and `handle.wait()` together under one `asyncio.wait(..., timeout=..., return_when=ALL_COMPLETED)`, terminate the handle when any task is still pending, then give the drain a short bounded grace before cancelling; report `timed_out=True` with `exit_code=None` once the deadline fires regardless of post-termination task outcomes.

### Cwd-Preferring Executable Resolution on Windows
- **Problem**: `shutil.which("cmd.exe")` prepends the process current directory on Windows unless `NoDefaultCurrentDirectoryInExePath` is set, and `CreateProcess` likewise searches the current directory before System32, so a `cmd.exe` (or `taskkill.exe`) dropped into the supervised repository root shadows the real shell when verification commands run or timed-out process trees are killed.
- **Solution**: Resolve the Gatekeeper's shell to an absolute trusted path (`%COMSPEC%`, then `%SystemRoot%\System32\cmd.exe`) with a bare-name fallback, and assert absolute resolution in a Windows-only test; the same cwd precedence still applies to bare `taskkill` termination inside `SubprocessProcessHandle` and remains a known residual.

### Bounded Tail Retention for Combined Stdout and Stderr
- **Problem**: Building the "last 100 lines of stdout then drained stderr" diagnostics by concatenating full streams buffers unbounded output, so a runaway command can exhaust memory before its timeout even fires.
- **Solution**: Retain stdout lines in a `deque(maxlen=tail_line_limit)` and slice drained stderr to its last `tail_line_limit` lines before concatenating; per-source N-line retention preserves the combined last-N window exactly while capping memory.

### Redirected Stdin Fails with EOFError, Not a Quiet EOF
- **Problem**: `input()` on redirected or closed stdin raises `EOFError` (and can raise `OSError` on Windows when the handle is invalid), so a terminal prompt loop can spin or crash instead of degrading gracefully when the Runner runs without a console.
- **Solution**: Catch `OSError` and `EOFError` around every prompt read: question prompts re-raise as `NonInteractiveError`, and the intervention menu maps the failure to an `abort` decision so the Runner never silently continues.

### Builtin Input Defaults Bind at Class Definition Time
- **Problem**: Using `input` (or `print`) as a default argument value in a class `__init__` binds the builtin at import time, so monkeypatching `builtins.input` in tests has no effect on instances created afterward and "defaults to the builtin" is untestable.
- **Solution**: Give injectable seam parameters `None` defaults and resolve the builtin inside `__init__` (`self._input_fn = input_fn if input_fn is not None else input`) so the default resolves at instantiation time and remains swappable via monkeypatch.

### Signal-Armed Termination Grace Clock Sampling in Streaming Test Doubles
- **Problem**: In mock streaming process handles where stdout lines are yielded sequentially, authoring the Signal file and advancing the injected clock in the same yield block causes the supervisor to observe the Signal for the first time *after* the clock has already advanced, setting `signal_first_seen_at` to the advanced timestamp (`now`) and masking the elapsed grace duration before the handle generator closes cleanly with `StopAsyncIteration` (`EXITED`).
- **Solution**: Emit an intermediate progress line at `t=0` after authoring the Signal file so the supervisor registers the initial file presence timestamp before the mock stream advances the clock past the 10-second grace threshold.

### Signal-Killed Process Exit Code Non-Zero Classification
- **Problem**: Force-killing a lingering subprocess via `taskkill /T /F` or OS process ladder returns non-zero termination exit codes (e.g. -15, 1, or 128+9), which causes naive crash detection (`exit_code != 0`) to falsely classify an intentional signal-armed kill as an unexpected process crash and trigger unwanted crash retries.
- **Solution**: Classify crashes strictly by termination reason: explicitly exempt `RunTerminationReason.KILLED_SIGNAL` from `SessionRunResult.is_crash` (`False`), allowing downstream verification to proceed directly with ready signal inspection.

### Untouched Question File Preservation Across Handoff Cycles
- **Problem**: When a Worker emits a clarification question and exits cleanly or is signal-killed, downstream handoff recovery paths (exit-0 nudge or crash retry) re-invoke the session with nudge/retry prompts, clobbering the question workflow or advancing attempt budgets prematurely.
- **Solution**: In `HandoffCoordinator.run_cycle`, evaluate pending question Signals before crash or nudge recovery branches; if `read_pending_question` returns non-None, immediately yield `SingleCycleStatus.QUESTION_PENDING` with the active session ID populated, leaving the on-disk question artifact untouched for human/gateway interaction.

### Python Special Method Lookup Bypasses Instance Attributes in Test Doubles
- **Problem**: Overriding special methods like `__call__` on an existing instance (`cr.__call__ = wrapped`) does not intercept invocations because Python resolves dunder methods exclusively on the class/type, not the instance dictionary (`type(cr).__call__(cr, ...)`).
- **Solution**: Design test doubles with explicit hook callbacks (e.g. `on_call: Callable[[Ticket, int], None] | None = None`) or provide a lightweight wrapper class delegating `__call__` dynamically so test scenarios can intercept cycle runs without mutating class types.

### Single-Use Signal Lifecycle and Stale Artifact Prevention
- **Problem**: If a Worker emits a ready signal but fails downstream verification or signal validation, leaving the ready signal on disk allows subsequent cycles or retry runs to re-consume stale ready signals without the Worker actively signaling readiness again.
- **Solution**: Treat ready signals as single-use consumables: delete the signal artifact immediately upon consumption or verification failure before feeding diagnostics into the worker resume prompt.

### Diagnostic Resume Prompt Tail Bounding
- **Problem**: In verification loops where test failure tails or escalation traces feed back to the worker session as resume prompts, unbounded failure logs can exhaust model context budgets across successive verification attempts.
- **Solution**: Enforce a strict line ceiling (`MAX_DIAGNOSTIC_LINES = 100`) on diagnostics injected into resume prompts, truncating to the most recent log tail while clearly indicating line counts in the resume instruction.

### Per-Ticket Verification Budget Survival Across Question Interleaves
- **Problem**: When a worker asks a clarifying question mid-attempt, returning to the runner/gateway could inadvertently reset or advance the verification attempt counter if attempt tracking is stored per invocation rather than per Ticket.
- **Solution**: Maintain the verification attempt counter on the stateful `VerificationLoop` instance per Ticket; return `QUESTION_PENDING` immediately without incrementing the budget counter, ensuring re-entry resumes with the exact remaining attempts intact.

### Atomic Question Answering and Audit Retention
- **Problem**: When rewriting question signals from `pending` to `answered`, non-atomic writes or naive deletion would either lose original question metadata (type, options, timestamps) or destroy the audit trail needed for post-run verification.
- **Solution**: Rewrite the question file atomically via `atomic_write_text` preserving all payload fields (`ticket_id`, `type`, `options`, `created_at`) while updating only `status: answered` and `answer`; retain the answered question file on disk for audit (single-use deletion applies only to ready signals).

### Ready-Wins Signal Precedence Over Stale Questions
- **Problem**: If both a pending question and a valid ready signal exist on disk simultaneously (e.g. from an earlier interrupted run or concurrent writes), prompting for the question halts autonomous execution unnecessarily.
- **Solution**: Enforce ready-wins precedence: validate the ready signal first; if valid, clean the stale question signal immediately so it cannot re-trigger, bypass human questioning, and proceed directly to Gatekeeper verification.

### Session ID Continuity Across Question Resume
- **Problem**: Resuming an answered question in OpenCode with a fresh session ID breaks conversational context, forcing the model to re-analyze the codebase from scratch.
- **Solution**: Preserve `active_session_id` on the `VerificationLoop` across question interruptions and resume the Worker with the identical session identifier carrying `"User answered: <answer>. Proceed with implementation."`.

### Composition Root Overrides for In-Process Test Isolation
- **Problem**: When `build_container` initializes real adapters by default, behavioral tests running in-process can inadvertently trigger real subprocess executions, scan production ticket queues, or attempt live git commits against the host working tree.
- **Solution**: Provide keyword-only optional overrides on `build_container` for all I/O adapters and interactors (`command_runner`, `intervention_gateway`, `ticket_store`, `gotchas_store`, `lock`, `git_operations`, `runtime_paths`), allowing tests to inject in-memory doubles in one call.

### Sentinel Lock Release Before Idle Standby and on Abort Paths
- **Problem**: Holding an OS file lock across idle standby sleep loops or during operator abort exits creates persistent Windows file-sharing locks (`PermissionError` / `[WinError 32]`) that block subsequent test fixtures or CLI instances from modifying or acquiring the queue.
- **Solution**: Explicitly release the sentinel lock immediately prior to entering standby idle watch loops, and guarantee lock release across all termination and error pathways (including `UserAbortError`) inside a `finally` block before returning exit code 2.

### Scoped File Pointer for Global Gotchas Prompt Overhead
- **Problem**: Inlining the entire `docs/tickets/gotchas.md` document verbatim into worker prompts causes prompt sizes to grow past the Windows 32,767 character command-line ceiling (`WinError 206`) and consumes thousands of redundant startup tokens on every session.
- **Solution**: Replace verbatim document inlining with a scoped markdown file pointer (`## Global Gotchas & Lessons Learned\nReview and adhere to all project-wide pitfalls recorded at `docs/tickets/gotchas.md` before implementing.`), normalizing the path to POSIX forward slashes across platforms while retaining ticket-specific gotchas inlined under `### Ticket Gotchas`.


### Queue Orchestrator Unit Tests Must Inject an Isolated Lock Path
- **Problem**: Constructing `QueueOrchestrator` without `lock_path` falls back to the live `docs/tickets/.queue.lock`, so unit tests raise `QueueLockError` whenever a real `ticket_runner.py` instance holds the sentinel, turning the full suite red on any actively running queue.
- **Solution**: Inject `lock_path=tmp_path / ".queue.lock"` into `QueueOrchestrator` in unit tests so lock acquisition stays confined to the pytest `tmp_path`, mirroring the keyword-only adapter overrides on `build_container`.

### Local Config Smoke Test Should Compare Against the Example, Not Hardcode
- **Problem**: `test_load_root_config_yaml` hardcoded `verification.test_cmd == "pytest"` and other example values, but the untracked local `config.yaml` intentionally uses `python -m pytest` (bare `pytest` is not on PATH on Windows), so the test failed whenever a local config existed even though the loader behaved correctly.
- **Solution**: Assert the untracked root config against `config.example.yaml` for the invariant fields (project identity, worker execution skill, token budget) and drop the environment-specific `test_cmd` assertion, keeping the smoke test meaningful without coupling it to a platform's PATH.

### cmd.exe Shell Wrapping Inherits the Runner PATH
- **Problem**: Gatekeeper verification commands run via `cmd.exe /d /s /c` and inherit the Runner's PATH, which may not include the Python `Scripts` directory, so bare console-script names like `pytest` report "command not found" and get mistaken for plain test failures (exit code 1).
- **Solution**: Author verification commands with portable invocation forms (`python -m <tool>` over bare script names). The Runner resolves each command's leading token via `shutil.which` before wrapping it in the shell and reports unresolvable commands as a distinct command-not-found diagnostic at both Gatekeeper and Doctor time.

### Resilient Markdown Header Extraction and Fallback Invariants
- **Problem**: Extracting specific sections (such as `## Invariants`) from markdown files like `AGENTS.md` can fail if the file is missing, permission-locked, or reworded without standard headings, causing unhandled exceptions during worker prompt generation.
- **Solution**: Wrap filesystem reads in defensive error handling and fall back to hardcoded canonical core invariants whenever the heading or file is absent, guaranteeing resilient prompt rendering.

### Token Budgeting for Inlined Markdown Guardrails
- **Problem**: Inlining operational guardrails into prompt strings risks ballooning command-line argument lengths past the Windows 32,767 character ceiling if entire documents are embedded verbatim.
- **Solution**: Restrict inlining strictly to targeted high-impact sections (`## Invariants`, ~250 tokens), pair with explicit file-reading directives (`read`) for broader documentation, and verify total command length in automated tests.

### Mixed Path Separator Normalization for OpenCode Stream Telemetry
- **Problem**: On Windows, OpenCode emits absolute and relative file paths in tool calls with mixed separators (e.g. `D:\Projects\.agents\skills\implement\SKILL.md`, `D:/Projects/...`, or escaped JSON backslashes `\\\\`), causing naive substring or POSIX-only regex matching to fail silently during tool use and resource access detection.
- **Solution**: Normalize all file paths and raw stream text with `.replace("\\", "/").lower()` before applying skill folder extraction or `AGENTS.md` regex matching, guaranteeing cross-platform telemetry detection across Windows and POSIX environments.

### Non-Blocking Resource Telemetry Extraction Isolation
- **Problem**: Unexpected payload schemas or regex backtracking anomalies during stream decoding of `tool_use` events could raise unhandled exceptions in the telemetry extraction loop, crashing the supervisor and killing active worker sessions.
- **Solution**: Wrap `extract_resource_access` calls defensively inside a `try...except Exception` block in the supervisor streaming loop, logging warnings for extraction failures while permitting session execution and watchdog monitoring to proceed uninterrupted.

### Non-Blocking Soft Warnings and Multi-Cycle Resource Accumulation
- **Problem**: Failing verification attempts or tripping the circuit breaker when review skills or `AGENTS.md` are not read prematurely aborts viable solutions and violates Gatekeeper independence. Conversely, discarding accessed resources between retries causes repetitive warnings on subsequent cycles even when the agent has already consulted the required skill.
- **Solution**: Emit soft warnings strictly via `_notify` and `logger.warning` without modifying attempt budgets or blocking Gatekeeper test execution, and accumulate accessed resources across cycles within the verification loop so earlier consultations satisfy compliance on retry.

### Doctor Pre-Flight Checks Must Respect Injected Workspace Paths
- **Problem**: Resolving workspace-root files (such as `AGENTS.md` and `.agents/skills/...`) using unanchored relative paths (`Path("AGENTS.md")`) or paths relative to `Path.cwd()` causes Doctor pre-flight checks in integration tests or isolated workspace runs to probe the host repository rather than the injected test workspace (`tmp_path`), triggering false passes on missing files or false failures on foreign environments.
- **Solution**: Resolve `AGENTS.md` and skill paths relative to `self._cwd` when provided, permit optional explicit path overrides in the `Doctor` constructor, and ensure all pre-flight inspections remain strictly read-only (`is_file()` and `open(..., "r")`).

### Standby Entry Banner Emission and Re-entry Timing
- **Problem**: In standby queue execution, printing entry banners inside polling sleep loops causes repetitive heartbeat spam, while emitting only once on startup skips announcing re-entry when newly arrived tickets drain and the runner returns to idle standby.
- **Solution**: Emit the standby banner strictly upon initial queue exhaustion and after processing standby-discovered tickets once the queue is redrained, ensuring the sentinel lock is released prior to each banner emission and omitting periodic output during idle watch intervals.

### TerminateJobObject Non-Zero Exit Code vs CloseHandle
- **Problem**: Closing a Windows Job Object handle (`CloseHandle`) with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` terminates processes with exit code 0 by default, causing test assertions and supervisory checks expecting non-zero termination exit codes to fail.
- **Solution**: In explicit process termination routines, invoke `kernel32.TerminateJobObject(hJob, 1)` prior to closing the job handle, ensuring active child and descendant processes exit with a non-zero status, while allowing normal lifecycle completion to reap residual orphans via `CloseHandle`.

### asyncio.CancelledError Is a BaseException Bypassing Exception Handlers
- **Problem**: In Python 3.8+, `asyncio.CancelledError` inherits from `BaseException` rather than `Exception`. Supervisor error handlers using `except Exception:` completely bypass the process termination ladder during task cancellation or graceful shutdown, leaving background subprocesses running.
- **Solution**: Explicitly catch `asyncio.CancelledError` in supervisor streaming loops, wrap the cleanup routine in `await asyncio.shield(...)` to protect the termination ladder against repeated cancellation, and re-raise.

### Windows Job Object Handle Lifetime and Immediate Assignment
- **Problem**: Windows Job Objects automatically close and reap processes if the last handle is closed. Storing the job handle in a local variable or temporary scope causes garbage collection to prematurely kill active processes mid-run. Conversely, a child process spawned before job assignment can escape into an unmanaged process group.
- **Solution**: Create and configure the Job Object immediately upon `spawn()`, assign the child process synchronously before any asynchronous yield without `CREATE_BREAKAWAY_FROM_JOB`, and attach the Job Object handle directly to the `SubprocessProcessHandle` instance for its entire lifetime.

### Windows Main-Thread SIGINT Handler and Event Loop Marshalling
- **Problem**: Python's `asyncio` loop on Windows does not support signal handlers (`loop.add_signal_handler` raises `NotImplementedError`). Catching SIGINT via standard `signal.signal(signal.SIGINT, handler)` executes on the main thread outside the event loop, where directly modifying async state or setting uncoordinated primitives can cause race conditions or miss active awaits.
- **Solution**: Install a main-thread handler via `signal.signal(signal.SIGINT, ...)` that marshals cooperative shutdown calls (`stop_event.set()`, `supervisor.request_kill(...)`) into the running event loop using `loop.call_soon_threadsafe`.

### Cooperative SIGINT Idempotency and Second Ctrl+C Force-Kill
- **Problem**: When a process is undergoing cooperative graceful shutdown (terminating worker subprocesses and releasing sentinels), subsequent SIGINT interrupts can restart or re-enter the graceful shutdown path, creating a trap where an operator cannot force-exit a wedged shutdown.
- **Solution**: Maintain an atomic `shutting_down` latch: the first interrupt begins cooperative shutdown and marshals stop events, while any subsequent interrupt observed while `shutting_down` is active immediately triggers an ungraceful hard exit via `sys.exit(130)`.

### Preserving Ticket Outcomes Across Multi-Cycle Standby Runs
- **Problem**: In multi-phase lifecycle executions where `QueueOrchestrator.run_lifecycle` drains the initial queue and settles into standby mode, discarding the return value of `run_next` causes completion summaries to report incomplete ticket counts and drop authored commit SHAs when new tickets arrive and get processed during subsequent standby cycles.
- **Solution**: Accumulate all `TicketOutcome` instances into a persistent lifecycle list across both the initial drain loop and all standby resumption cycles, ensuring graceful exit completion summaries accurately aggregate total processed tickets (approved, skipped, aborted), all authored commit SHAs, current branch, and elapsed time measured via an injectable clock.

### Non-Blocking Standby Watch Loop and Deferred Clean-Slate Archival
- **Problem**: Prompting for interactive clean-slate archival (`[CleanSlate] Wipe completed tickets and spec for a clean slate? [Y/n]: `) at queue drain under `queue_completion="standby"` blocks the orchestrator on terminal input, stalling the watch loop from polling for incoming tickets while an operator is away.
- **Solution**: Defer interactive clean-slate archival under standby mode past queue drain until runner exit (graceful SIGINT or shutdown), while allowing `always` and `never` policies to retain their drain-time behaviors and preserving `terminate` policy's drain-time prompt per ADR 0012.

### Clean-Slate Execution Must Release Sentinel Lock Before Archival
- **Problem**: Executing interactive archival prompts or running git removal/chore commits while holding the sentinel queue file lock causes Windows file-sharing violations if user input blocks lock release or git operations attempt modifications overlapping the lock directory.
- **Solution**: Release the sentinel lock (`self.release_lock()`) explicitly prior to invoking `_handle_clean_slate` on both drain-time and exit-time execution paths.

### Standby Resume Cycles Must Suppress Mid-Watch Archival Prompts
- **Problem**: When standby resume cycles process newly detected tickets and drain again, re-triggering clean-slate prompts mid-watch re-introduces terminal blocking during active polling.
- **Solution**: Track deferred clean-slate status and already cleaned spec slugs without prompting during standby re-drain; fire the interactive prompt exactly once upon final lifecycle exit.

### Bounded State Reads with Fast-Path Stat Size Check
- **Problem**: Reading unvalidated on-disk state documents into memory using standard `read_text()` or `json.load()` can cause memory exhaustion or hang the process when encountering corrupted or hostile multi-gigabyte files. Relying solely on `stat().st_size` can be inaccurate or bypassed on special filesystems or streaming descriptors.
- **Solution**: Pair a pre-flight `stat().st_size > max_bytes` check with a bounded binary read (`handle.read(max_bytes + 1)`). If the returned chunk exceeds `max_bytes`, immediately raise `StateFormatError` before decoding UTF-8 or parsing JSON, capping memory usage deterministically.

### State Adapter Caller-Owned Exact Document Writes
- **Problem**: Attempting automatic read-modify-write merges inside low-level state persistence adapters tightly couples the storage layer to specific document schemas and can silently mask key deletion or clobber concurrent updates.
- **Solution**: Keep the `StateStore` port protocol strictly as an exact-document writer (`write(document)` writes exactly the supplied mapping atomically without reading), requiring high-level application interactors to own schema evolution and explicit read-modify-write merge semantics.

### Tolerant Configuration Loader with Doctor Model Guard
- **Problem**: Requiring the new `model:` configuration block in `YamlConfigLoader` or `REQUIRED_SECTIONS` causes smoke tests loading untracked live local `config.yaml` files to fail before developers have updated their local workspace configuration.
- **Solution**: Keep `model:` optional in `YamlConfigLoader` (defaulting absent or null blocks to `ModelConfig()`), append `model: ModelConfig = field(default_factory=ModelConfig)` as the final field of `RunnerConfig` to maintain positional compatibility, treat empty YAML `default_reasoning:` (which parses as `None`) as `""`, and let the Doctor's pre-flight check own the non-empty `model.models` validation guard with an actionable remediation block.

### Subprocess Argument Positioning and Untrusted Variant Handling
- **Problem**: Passing untrusted ticket frontmatter such as `Reasoning:` directly into subprocess CLI arguments risks token misalignment or injection if shell-quoted or split. Additionally, appending CLI flags in the wrong position can break existing downstream tests or CLI parsers expecting `--auto <prompt>` as the terminal arguments, or tests indexing fixed token positions (`cmd[4]`, `cmd[5]`, `cmd[7]`).
- **Solution**: Insert `--variant <variant>` strictly after `--session <id>` and before `--auto <prompt>`, only when variant is non-empty after stripping whitespace. Pass the value as a single argv token without shell quoting or word-splitting. In test doubles (`FakeCommandRunner`), verify spawned subprocesses via `fake_runner.spawns` rather than `fake_runner.commands` (which only captures `run()` calls).





