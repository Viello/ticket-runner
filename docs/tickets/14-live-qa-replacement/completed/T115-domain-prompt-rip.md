# T115 — Domain and Worker prompt rip: scenario data dies at the source
Status: completed
Completed: 2026-10-04T06:42:00Z
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: None
Security: required

### Requirements
- Remove the smoke-scenario data path at its origin: the `Ticket` entity loses its `smoke_scenarios` collection; the Markdown parser stops extracting the `### Smoke Scenarios` region and treats a legacy heading in old ticket files as inert content (must not crash or misattribute it to another region); the ready `Signal` loses its `manual_verification` payload and validator — old signal files on disk that still carry the key must parse via unknown-key tolerance, and new signals must not emit it; the Worker prompt's default invariants and completion protocol replace the smoke-scenario contract with the live-qa contract (human verification happens after green checks via a `/live-qa` session the human runs; the Worker drafts no scenarios and self-reports no manual verification).
- Jump-start:
  - Files to touch: `runner/domain/ticket.py` (field line 58, coercion lines 124–128), `runner/adapters/markdown/parser.py` (`_parse_smoke_scenarios` lines 142–199, call sites lines 52/65), `runner/domain/signal.py` (`manual_verification` field 303, validator 181–237, parse wiring 331–335/359–360, default-flag property 337–340), `runner/application/prompt_builder.py` (invariant text lines 23–24, schema section 193–201, contract section 202–204).
  - Seams to work at: `tests/unit/domain/test_signal.py`, `tests/unit/adapters/test_ticket_parser.py`, `tests/unit/application/test_prompt_builder.py`.
  - Anchor: the signal's existing unknown-key tolerance pattern for forward-compat payloads.
  - Verification: `python -m pytest tests/unit/domain tests/unit/adapters/test_ticket_parser.py tests/unit/application/test_prompt_builder.py`
- Gatekeeper still references the removed fields during this ticket's intermediate states — land the domain removals with Gatekeeper's fallback chain (`getattr(..., (), ...)`) intact if needed to keep the suite green, or adapt the minimal call sites in `runner/application/gatekeeper.py` to stop sourcing scenario data, leaving full consumer removal to T116. Prefer: remove the field and the Gatekeeper sourcing chain in one green commit; T116 then finishes cards, logging, and adapters.

### Acceptance Criteria
- `Ticket` has no scenario attribute; parser output for legacy Spec-13 tickets parses cleanly with the section ignored.
- Ready signal payload schema excludes `manual_verification`; a legacy signal JSON containing it still parses.
- `PromptBuilder` output contains no smoke-scenario or manual-verification language and does instruct the live-qa discipline (human runs `/live-qa` after green checks).
- Full suite `python -m pytest` green.
- Security verification: signal-parsing hardening that survives (ANSI stripping, path/traversal guards, git-header injection protections on surviving fields) remains covered by tests; removing the validator must not widen the trusted surface of any remaining field.

### Smoke Scenarios
**Scenario: legacy ticket parses inertly** [also auto-covered]
- Setup: A completed ticket from earlier specs (`docs/tickets/14-live-qa-replacement/completed/T114-discord-notify-one-shot-cli.md`) that carries a populated `### Smoke Scenarios` section.
- Why: Completed tickets and legacy signals from earlier specs must remain readable by the Doctor, Queue, and Gatekeeper without raising exceptions or populating non-existent scenario attributes.
- Steps:
  1. Open a PowerShell terminal in the repository root (`d:\Projects`).
  2. Run the legacy parser and signal compatibility verification one-liner:
     ```powershell
     python -c "from pathlib import Path; from runner.adapters.markdown.parser import TicketMarkdownParser; from runner.domain.signal import ReadySignal; t = TicketMarkdownParser().parse(Path('docs/tickets/14-live-qa-replacement/completed/T114-discord-notify-one-shot-cli.md')); assert not hasattr(t, 'smoke_scenarios'); payload = dict(ticket_id='T114', status='ready_for_verification', modified_files=[], self_review_notes='ok', new_gotchas=[], timestamp='2026-10-04T00:00:00Z', manual_verification=[dict(name='old')]); s = ReadySignal.parse(payload, 'T114'); assert not hasattr(s, 'manual_verification'); print('Legacy compatibility verified: clean parse and unknown-key tolerance confirmed.')"
     ```
- Expected:
  - The command exits with return code 0.
  - Output displays: `Legacy compatibility verified: clean parse and unknown-key tolerance confirmed.`.
  - The parsed `Ticket` object has no `smoke_scenarios` attribute.
  - The parsed `ReadySignal` object tolerates the legacy `manual_verification` key without error and does not expose a `manual_verification` attribute.

### Gotchas
- The empty-manual-verification warning in the Gatekeeper (lines 1255–1264) and `EvidenceCard` construction read these fields — coordinate so the suite never goes red mid-queue.
- `docs/tickets/gotchas.md` entries reference the old field names; leave history intact (Gotchas log is append-only memory, not live code).
