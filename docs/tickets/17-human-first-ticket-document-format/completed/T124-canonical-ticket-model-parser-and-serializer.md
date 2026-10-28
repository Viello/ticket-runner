# T124: Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer

**Status:** done (reviewed; Security PASSED)
**Completed:** 2026-10-28T05:39:00Z
**Labels:** ready-for-agent, security
**Security:** required (trust boundaries: untrusted markdown parsing, dialect detection, and atomic header serialization)
**Parent:** docs/specs/17-human-first-ticket-document-format.md

**What to build:** Enable `TicketMarkdownParser`, `TicketMarkdownSerializer`, `DirectoryTicketStore`, and `Doctor.check_queue` to natively read and patch Specimen A (`to-ticket-runner` canonical bold-label headers and 5 top-level `##` sections with `- [ ]` / `- [x]` checkboxes), populate `Ticket.mode`, `Ticket.status_note`, `Ticket.jump_start`, and `Ticket.checked_criteria`, and emit a clear remediation error when pointed at an interactive-only `to-tickets` (Human+AI Specimen B) queue.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/ticket.py`
  - `runner/adapters/markdown/parser.py`
  - `runner/adapters/markdown/serializer.py`
  - `runner/adapters/markdown/ticket_store.py`
  - `runner/application/doctor.py`
  - `tests/unit/domain/test_ticket.py`
  - `tests/unit/adapters/test_ticket_parser.py`
  - `tests/unit/adapters/test_ticket_serializer.py`
  - `tests/unit/adapters/test_ticket_store.py`
- **Seams:** Document I/O boundary (`TicketMarkdownParser.parse`, `TicketMarkdownSerializer.update_header`, `DirectoryTicketStore.finalize_completed` / `finalize_skipped`) and domain entity construction (`Ticket`, `TicketStatus`).
- **Existing-code anchors:** `Ticket` dataclass and `parse_ticket_status` in `runner/domain/ticket.py`; `METADATA_PATTERN` and `_parse_sections` in `runner/adapters/markdown/parser.py`; `METADATA_KEY_ORDER` and `_apply_metadata` in `runner/adapters/markdown/serializer.py`; `check_queue` in `runner/application/doctor.py`.
- **Verify:** `py -3 -m pytest tests/unit/domain/test_ticket.py tests/unit/adapters/test_ticket_parser.py tests/unit/adapters/test_ticket_serializer.py tests/unit/adapters/test_ticket_store.py -x`

**Blocked by:** None (can start immediately)

- [x] `TicketStatus` supports `pending`, `running`, `in_progress`, `completed`, `failed`, `blocked`, and `skipped`, and `Ticket` carries `mode: str = "AFK"` (`"AFK"` or `"HITL"`, validated case-insensitively), `status_note: str | None = None`, `jump_start: tuple[str, ...] = ()`, and `checked_criteria: frozenset[str] = frozenset()`.
- [x] `TicketMarkdownParser` parses Specimen A bold-label headers (`**Mode:**`, `**Status:**`, `**Status note:**`, `**Completed:**`, `**Spec:**` with directory fallback, `**Blocked by:**`, first-token case-insensitive `**Security:**` tolerating inline rationale such as `required (trust boundaries: ...)`, and `**Reasoning:**`) while keeping legacy flat `Key: value` test fixtures passing.
- [x] `TicketMarkdownParser` parses the five recognised `##` sections (`What to build` into `requirements` supporting both bullets and contiguous prose paragraphs, `Jump-start` into `jump_start`, `Acceptance criteria` stripping `- [ ] ` / `- [x] ` markers into `acceptance_criteria` and recording ticked items in `checked_criteria`, inert `Smoke scenarios`, and `Gotchas` into `gotchas`), while keeping legacy `###` test fixtures passing.
- [x] Security & dialect verification: When `TicketMarkdownParser` (or `Doctor.check_queue`) encounters an interactive-only `to-tickets` (Human+AI Specimen B) file (e.g., `**Status:** ready-for-agent` / `done` / `ready-for-human`, `**Labels:**`, `**Parent:**`, or inline `**What to build:**` without `##` sections), it raises a descriptive `TicketFormatError` explaining that the ticket uses the interactive `to-tickets` (Human+AI) format and pointing the operator to `/implement` or `/to-ticket-runner`.
- [x] `TicketMarkdownSerializer` and `DirectoryTicketStore` patch bold-label headers in-place in canonical order (`Mode`, `Status`, `Status note`, `Completed`, `Spec`, `Blocked by`, `Security`, `Reasoning`), preserving all body bytes after the header region, `- [x]` checkboxes, CRLF/LF line endings, and trailing newline state untouched.

**Verified:** 2026-10-28 — All 5 criteria verified test-first across 167 targeted unit tests and 1,199 domain/adapter suite tests; Security Review PASSED; dialect guard verified.

