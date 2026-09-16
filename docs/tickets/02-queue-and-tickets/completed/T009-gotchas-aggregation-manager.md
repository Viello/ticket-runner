# T009 — Gotchas aggregation manager
Status: completed
Completed: 2026-09-16T06:17:00Z
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Implement `GotchasStore` in `runner/adapters/markdown/gotchas_store.py` that loads `docs/tickets/gotchas.md`, appends `new_gotchas` entries emitted by completion signals, and writes atomically (user story 9).
- Preserve all existing content and section structure; only append. Create the file with the standard header skeleton when missing.
- Normalize incoming entries into the established `### <Title>` + `- **Problem**` / `- **Solution**` section format used by the existing file, without corrupting entries that already carry markdown formatting.
- Accept `new_gotchas` as a list of strings from the caller; signal file parsing and extraction remain in Spec 04 (the queue orchestrator passes the list after Gatekeeper approval).
- Skip exact duplicate entries so repeated runs do not bloat the file.
- Use the same atomic `.tmp` + `os.replace` write discipline as ticket updates.
- Jump-start:
  - Files to touch: `runner/adapters/markdown/gotchas_store.py`, `tests/unit/adapters/test_gotchas_store.py`.
  - Seams: `runner/adapters/markdown/gotchas_store.py:GotchasStore.append` and `load`.
  - Anchor patterns: section format in `docs/tickets/gotchas.md`; atomic-write helper introduced by T006.
  - Verification: `pytest tests/unit/adapters/test_gotchas_store.py`.

### Acceptance Criteria
- Appending entries preserves the file header and every pre-existing section unchanged, with new sections appended at the end.
- A missing `gotchas.md` is created with the standard skeleton before the first entry is appended.
- Exact duplicate entries are not written twice.
- Writes are atomic; failures leave the original file intact and no `.tmp` residue.
- Tests run against temporary directory trees and cover append, skeleton creation, and dedupe.

### Gotchas
- New gotchas strings arrive as free text from Worker signals; keep normalization minimal and deterministic so worker-authored detail is not silently rewritten.
- Always write UTF-8; gotchas may contain Unicode symbols from previous runs.
- The file may be edited by the developer while the Runner is paused; keep the read-modify-write window scoped to the append moment to minimize clobber risk.
