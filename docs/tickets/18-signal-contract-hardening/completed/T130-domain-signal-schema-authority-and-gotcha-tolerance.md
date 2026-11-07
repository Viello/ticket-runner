# T130: Domain Signal Schema Authority and Gotcha Tolerance

**Status:** done (reviewed; domain Signal schema authority + Gotchas tolerance)
**Completed:** 2026-10-30T14:25:41Z
**Labels:** ready-for-agent
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** Make the domain the single authority for the ready and question Signal schemas. A new frozen field-spec value object and renderers describe every field and produce a complete example payload and protocol text for each Signal. At the same time, `new_gotchas` accepts the canonical `{problem, solution}` object, the `fix` alias, and plain strings, canonicalising all three to the `Problem: …` / `Solution: …` text form the Gotchas store already consumes. Ticket identity, status, modified files, timestamp, and scope stay strict.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/signal_schema.py` (new)
  - `runner/domain/signal.py`
  - `tests/unit/domain/test_signal_schema.py` (new)
  - `tests/unit/domain/test_signal.py`
- **Seams:** `ReadySignal.parse` / `ReadySignal.__post_init__`, `QuestionSignal.parse` / `QuestionSignal.__post_init__`, and the new `SignalFieldSpec`, `READY_SIGNAL_FIELDS`, `QUESTION_SIGNAL_FIELDS`, `render_ready_signal_example`, `render_question_signal_example`, `render_ready_signal_protocol`, and `render_question_signal_protocol`.
- **Existing-code anchors:** `_validate_text`, `_validate_string_tuple`, `_decode_payload`, and `_preview` in `runner/domain/signal.py`; frozen value-object style in `runner/domain/runtime_paths.py`; `_ready_payload` and `_question_payload` builders in `tests/unit/domain/test_signal.py`.
- **Verify:** `py -3 -m pytest tests/unit/domain/test_signal.py tests/unit/domain/test_signal_schema.py -q`

**Blocked by:** None (can start immediately)

- [x] `SignalFieldSpec` is a frozen value object carrying `name`, `description`, and `example`; ordered field-spec tuples cover every field of `ReadySignal` and `QuestionSignal`, and a reflection test fails when a parser field is absent from its tuple or a renderer advertises a field the parser rejects.
- [x] Renderers accept a Ticket id and use a fixed valid timestamp; `render_ready_signal_example` and `render_question_signal_example` return complete payloads that parse through the real parsers, and the protocol renderers return complete human-readable section text for the same fields.
- [x] `new_gotchas` accepts the canonical `{problem, solution}` object, the `{problem, fix}` alias (`solution` wins when both are present), and plain strings; all three canonicalise identically to a `Problem: …` / `Solution: …` text form, and unknown keys inside a Gotcha object are ignored.
- [x] Blank required keys, non-string and non-mapping entries, nested lists, and junk raise `SignalFormatError` naming `new_gotchas` and the entry index; `ticket_id`, `status`, `modified_files`, `timestamp`, `scope`, and all question fields remain strict.
- [x] Targeted tests pass; Ruff and mypy are clean on every changed file.

**Verified:** 2026-10-30 — 182 targeted domain tests; full suite 2,136 passed / 4 skipped; Ruff and mypy clean on the domain files. Three-axis review: Standards findings remediated (paths now come from `RuntimePaths`, ticket ids validated against `TICKET_ID_PATTERN`, error-prefix duplication removed); Security MEDIUM advisories recorded (untrusted Gotcha text still reaches `docs/tickets/gotchas.md` unfiltered — pre-existing, out of scope).
