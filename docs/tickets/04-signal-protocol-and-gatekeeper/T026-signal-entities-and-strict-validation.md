# T026 — Signal entities and strict validation
Status: pending
Security: required
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: none

### Requirements
- Add domain entities `ReadySignal` and `QuestionSignal` matching the Spec 04 schemas, plus an optional `scope` on `ReadySignal` (lowercase token, never a ticket number; absent means the orchestrator default applies later).
- Strict validation: missing fields, wrong types, unknown `status` or `type`, `ticket_id` mismatch with the expected Ticket, unparseable or non-ISO-8601 timestamps, `choice` questions without non-empty options, or an answer/status mismatch raise a new `SignalFormatError` rooted at `TicketRunnerError`. Unknown extra JSON fields are tolerated; identity fields are never silently defaulted.
- Parsing is pure: it takes JSON text (or a mapping) plus the expected `ticket_id`; no I/O and no path construction in the domain.
- Jump-start:
  - Files to touch: `runner/domain/signal.py` (new), `runner/domain/exceptions.py`, `runner/domain/__init__.py`, `tests/unit/domain/test_signal.py` (new).
  - Seams: entity constructors and parse classmethods; `SignalFormatError`.
  - Anchor patterns: frozen-dataclass validation in `runner/domain/ticket.py`; exception hierarchy in `runner/domain/exceptions.py`.
  - Verification: `pytest tests/unit/domain/test_signal.py`.

### Acceptance Criteria
- A valid ready payload with every schema field parses; `scope` is optional; ISO-8601 timestamps including a trailing `Z` are accepted.
- Valid question payloads parse for both `choice` (non-empty options) and `text` (options null or absent).
- One parametrized case per violation asserts `SignalFormatError` naming the offending field; `json.JSONDecodeError` never escapes parsing.
- Ticket-id mismatch is rejected even when every other field is valid.
- `modified_files` and `new_gotchas` are `tuple[str, ...]`; non-string items are rejected.

### Gotchas
- Python 3.11 `datetime.fromisoformat` needs `value.replace("Z", "+00:00")` for UTC timestamps.
- Keep the module dependency-free (domain purity); no `RuntimePaths` import.
- These error messages later appear in Worker diagnostics — keep them single-line and actionable.
- Security: the payload is untrusted Worker output — treat it strictly as data (no eval, no path construction from field values, bounded error messages).
