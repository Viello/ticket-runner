# T006 — Ticket domain entity, markdown parser, and atomic serializer
Status: completed
Completed: 2026-09-15T18:03:00Z
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Define `TicketStatus` enumeration with exactly `pending`, `running`, `completed`, `skipped` and a frozen `Ticket` domain dataclass in `runner/domain/ticket.py` carrying `id` (e.g. `T006`), `title`, `status`, `spec_path`, `requirements`, `acceptance_criteria`, `gotchas`, and `path`, with invariant validation raising descriptive errors for malformed identifiers or unknown status values.
- Implement spec linkage resolution: an explicit `Spec: docs/specs/<spec-slug>.md` header wins; when omitted, infer `docs/specs/<parent-directory-slug>.md` from the ticket's parent directory name (ADR 0011).
- Implement `TicketMarkdownParser` in `runner/adapters/markdown/parser.py` parsing the header block (`# T<NNN> — <Title>`, `Status:`, optional `Spec:`, optional `Completed:`) plus the `### Requirements`, `### Acceptance Criteria`, and `### Gotchas` sections into a `Ticket`.
- Implement `TicketMarkdownSerializer` in `runner/adapters/markdown/serializer.py` updating only the header metadata region (`Status:`, `Completed:`) while preserving all remaining markdown formatting, comments, spacing, and line endings exactly as authored (user story 6).
- Use atomic writes for every file mutation: write a sibling `.tmp` file then `os.replace` onto the target (spec "Atomic File Writes"); never leave stray temp files behind, and ensure a leftover temp file can never be staged by the Gatekeeper's `git add .`.
- Raise `TicketFormatError` (inheriting `TicketRunnerError`) from `runner/domain/exceptions.py` for unparseable headers, invalid statuses, or malformed identifiers.
- Jump-start:
  - Files to touch: `runner/domain/ticket.py`, `runner/domain/exceptions.py`, `runner/adapters/markdown/__init__.py`, `runner/adapters/markdown/parser.py`, `runner/adapters/markdown/serializer.py`, `.gitignore`, `tests/unit/domain/test_ticket.py`, `tests/unit/adapters/test_ticket_parser.py`, `tests/unit/adapters/test_ticket_serializer.py`.
  - Seams: `runner/adapters/markdown/parser.py:TicketMarkdownParser.parse` and `runner/adapters/markdown/serializer.py:TicketMarkdownSerializer.update_header`.
  - Anchor patterns: frozen dataclass validation in `runner/domain/config.py`; exception hierarchy in `runner/domain/exceptions.py`; ticket format in `ticket-runner-plan.md` §3 and the completed files under `docs/tickets/01-doctor-and-git-ops/completed/`.
  - Verification: `pytest tests/unit/domain/test_ticket.py tests/unit/adapters/test_ticket_parser.py tests/unit/adapters/test_ticket_serializer.py`.

### Acceptance Criteria
- Parsing a well-formed ticket file yields a `Ticket` with id, title, status, resolved spec path, and section contents.
- An omitted `Spec:` header resolves to `docs/specs/<spec-slug>.md` based on the parent directory; an explicit header wins.
- Status/header updates preserve all custom formatting, comments, and spacing elsewhere byte-for-byte, including the original newline style.
- Atomic replacement is used for writes and no `.tmp` artifact remains after success or failure.
- Invalid `Status:` values and malformed ticket ids raise descriptive `TicketFormatError`.
- Unit tests cover parsing, spec inference, formatting preservation, and atomic write behavior.

### Gotchas
- Spec 02 text cites "ADR 0011" for the directory queue layout, but the directory-queue ADR is 0010 and ADR 0011 is spec-excerpt injection — cite the correct ADR (0010 for queue layout, 0011 for spec linkage fallback).
- Never record the commit SHA in ticket frontmatter on updates (ADR 0012).
- `Path.read_text()`/`write_text()` normalize newlines; read and write with explicit `newline=""` handling so CRLF-authored tickets round-trip unchanged.
- On Windows, `os.replace` over a file currently open by an external editor raises `PermissionError`; surface a clear error rather than corrupting state.
- Keep repo style: `from __future__ import annotations`, frozen dataclasses, no comments unless asked.
