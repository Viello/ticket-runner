# T014 — Parse the `Security: required` ticket flag
Status: completed
Completed: 2026-09-16T09:36:12Z
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Extend the `Ticket` entity with `security_required: bool` (default `False`) and teach the markdown parser to consume the `Security:` metadata line, which is currently discarded, so the prompt builder can conditionally instruct `/security-review` (Spec 03 US5, ADR 0013).
- Treat `Security: required` (value match case-insensitive, surrounding whitespace tolerated) as `True`; a missing line or any other value is `False` — never raise on unknown values.
- Leave section parsing, status handling, and the serializer's header round-trip for existing metadata untouched; `update_header` must preserve the `Security:` line as-is.
- Jump-start:
  - Files to touch: `runner/domain/ticket.py`, `runner/adapters/markdown/parser.py`, `tests/unit/domain/test_ticket.py`, `tests/unit/adapters/test_ticket_parser.py`.
  - Seams: the parser's metadata loop (consumes `status` and `spec` today) and the frozen `Ticket` dataclass invariants.
  - Anchor patterns: `Spec:` metadata handling and its `completed/` inference tests in `tests/unit/adapters/test_ticket_parser.py`; status coercion in `runner/domain/ticket.py`.
  - Verification: `pytest tests/unit/domain/test_ticket.py tests/unit/adapters/test_ticket_parser.py`.

### Acceptance Criteria
- A ticket file with `Security: required` parses to `security_required=True`; without the line → `False`; with `Security: optional` or any other value → `False` without raising.
- `TicketMarkdownSerializer.update_header` round-trips a ticket carrying the `Security:` line without altering it or any other byte pattern (CRLF preservation per existing gotchas).
- Existing domain and parser suites stay green; all pre-existing fixtures remain valid via the default.

### Gotchas
- Default to `False` so tickets authored before this change and in-flight fixtures remain parseable.
- Do not reject or normalize unknown security values — parser tolerance for unrecognized metadata is a repo convention (see `Ticket Header Tolerance for Concise Format` in gotchas.md).
- This ticket is a pure prefactor: no prompt, supervisor, or review logic here.
