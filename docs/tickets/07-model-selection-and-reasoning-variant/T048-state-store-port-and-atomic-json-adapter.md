# T048 — State store port and atomic JSON adapter
Status: pending
Spec: docs/specs/07-model-selection-and-reasoning-variant.md
Blocked by: None
Security: required
Reasoning: medium

### Requirements
- Introduce the minimal persistence seam for `.agent/state.json` so later Spec 07 tickets (and eventually Spec 06's `RunnerState`) can durably store Runner-owned JSON documents.
- Add a `StateStore` port (Protocol) with `read() -> dict[str, Any] | None` (returns `None` when the file is absent) and `write(document: Mapping[str, Any]) -> None` (writes exactly the supplied document; callers own merge semantics).
- Add a `JsonStateStore` adapter implementing the port over a `RuntimePaths`-resolved path: UTF-8 JSON, sibling `.tmp` file plus `os.replace`, temp cleanup on every failure path, and a bounded read (payloads above a fixed byte cap, e.g. 1 MiB, raise `StateFormatError`).
- Add `StateFormatError(TicketRunnerError)` to `runner/domain/exceptions.py` for malformed or unreadable state content; an absent file is not an error.
- Add `RuntimePaths.state_path` (`.agent/state.json`) as a pure path computation with no disk side effects.
- Add `tests/fakes/fake_state_store.py` as an in-memory port double for later tickets.
- Jump-start:
  - Files to touch: `runner/ports/state_store.py`, `runner/adapters/filesystem/json_state_store.py`, `runner/domain/exceptions.py`, `runner/domain/runtime_paths.py`, `tests/fakes/fake_state_store.py`, `tests/unit/adapters/test_json_state_store.py`.
  - Seams: model the protocol on `runner/ports/signal_repository.py`; reuse the atomic-write discipline from `runner/adapters/markdown/atomic_write.py`.
  - Verification: `python -m pytest tests/unit/adapters/test_json_state_store.py tests/unit/domain/test_runtime_paths.py`.

### Acceptance Criteria
- `read()` returns `None` for a missing file and never raises for absence.
- A valid JSON object round-trips exactly (values and types preserved), the file is UTF-8, and no `.tmp` sibling remains after a successful write.
- Malformed JSON, a non-object root (list, string, number), and a payload nested past the interpreter recursion limit raise `StateFormatError` — never a leaked `JSONDecodeError` or `RecursionError`.
- Payloads exceeding the byte cap raise `StateFormatError` without exhausting memory.
- A simulated write failure propagates the error and leaves no `.tmp` sibling behind.
- `FakeStateStore` satisfies the port and is exercised by at least one test.
- `RuntimePaths.state_path` resolves to `root_dir / "state.json"`, and constructing `RuntimePaths` creates nothing on disk.
- Full suite green: `python -m pytest`.

### Gotchas
- The adapter must delete its `.tmp` sidecar on every failure path, not just `OSError` (see gotchas: Atomic Writes Must Clean Up on Every Failure Path); `*.tmp` is already git-ignored.
- Open with `encoding="utf-8", newline=""` to avoid Windows CRLF translation.
- `json.loads` raises `RecursionError` (not `JSONDecodeError`) on deeply nested untrusted payloads — catch it explicitly (see gotchas: RecursionError from Deeply Nested Untrusted JSON).
- Do not read-merge inside the adapter: exact-document writes are what let Spec 06 extend the schema safely; merging is a caller concern (T052).
- `os.replace` can raise `PermissionError` on Windows when an editor holds the target open; do not swallow write failures — T052 maps them to exit 1.
