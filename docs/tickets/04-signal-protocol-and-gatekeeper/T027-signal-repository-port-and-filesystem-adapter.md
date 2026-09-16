# T027 — Signal repository port and filesystem adapter
Status: pending
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: T026

### Requirements
- Define a `SignalRepository` port covering: read ready Signal (`ReadySignal | None`, raising `SignalFormatError` when present but malformed), read pending question (`QuestionSignal | None`, `None` when absent or already answered), consume ready Signal (single-use delete, idempotent), write answer (atomically flip the question to `answered` with the answer, preserving every other field), and purge (delete both artifacts for the Ticket; idempotent; creates directories as needed).
- Filesystem adapter binds the port to `RuntimePaths` and writes through the existing atomic-write helper with a stable JSON format and trailing newline.
- In-memory fake for application tests: seed signals, record `write_answer` calls, and raise on demand for malformed fixtures.
- Jump-start:
  - Files to touch: `runner/ports/signal_repository.py` (new), `runner/adapters/filesystem/__init__.py` and `runner/adapters/filesystem/signal_watcher.py` (new package), `tests/fakes/fake_signal_repository.py` (new), `tests/unit/adapters/test_signal_watcher.py` (new).
  - Seams: `RuntimePaths.ready_signal_path`, `question_path`, `ensure_signals_dir`, `ensure_questions_dir`.
  - Anchor patterns: protocol style in `runner/ports/ticket_repository.py`; `atomic_write_text` in `runner/adapters/markdown/atomic_write.py`; fake conventions in `tests/fakes/fake_ticket_repository.py`.
  - Verification: `pytest tests/unit/adapters/test_signal_watcher.py`.

### Acceptance Criteria
- Round trip: hand-written ready JSON reads back as `ReadySignal`; a malformed file raises `SignalFormatError`; a missing file returns `None`.
- `consume_ready` deletes the file and is a no-op when absent; `read_pending_question` hides `answered` files.
- `write_answer` preserves `ticket_id`, `question`, `type`, `options`, and `created_at`, flips only `status` and `answer`, leaves no `.tmp` siblings, and raises `SignalFormatError` when no question file exists.
- `purge` removes both artifacts, works when paths or directories are absent, creates parent directories for writes, and never leaves partial files.
- The fake and the adapter agree on the operations above.

### Gotchas
- Reuse the atomic-write helper rather than `Path.write_text` (Windows `PermissionError` and cleanup gotchas are already solved there).
- Never `mkdir` in constructors; only the explicit `ensure_*` helpers create directories.
- Treat mid-operation file disappearance as absence on reads and purge.
