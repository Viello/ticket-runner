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

