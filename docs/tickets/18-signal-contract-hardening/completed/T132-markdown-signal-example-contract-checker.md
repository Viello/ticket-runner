# T132: Markdown Signal Example Contract Checker and Repository Skill Test

**Status:** done (reviewed; pure domain signal contract checker and skill tests)
**Completed:** 2026-10-30T16:45:00Z
**Labels:** ready-for-agent
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** A pure domain contract checker extracts fenced `json` blocks from markdown, classifies ready versus question examples, substitutes documented placeholders, and validates each through the real parsers. The repository gains a test that runs the checker over the canonical execution skill so a reintroduced stale example fails locally rather than in a Target Project.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/signal_contract.py` (new)
  - `tests/unit/domain/test_signal_contract.py` (new)
  - `tests/unit/skills/test_signal_skill_contract.py` (new)
- **Seams:** Pure `extract_fenced_json_blocks`, classification of ready versus question blocks, recursive placeholder substitution, and `validate_markdown_signal_examples`.
- **Existing-code anchors:** `ReadySignal.parse` and `QuestionSignal.parse` in `runner/domain/signal.py`; the placeholder family (`<ticket_id>`, `<ISO-8601-UTC>`) previously used by `.agents/skills/implement-ticket-runner/SKILL.md`; `tests/unit/skills/test_dual_track_skills.py` for skill-file test style.
- **Verify:** `py -3 -m pytest tests/unit/domain/test_signal_contract.py tests/unit/skills/test_signal_skill_contract.py -q`

**Blocked by:** T130, T131

- [x] `extract_fenced_json_blocks` returns the contents of fenced `json` blocks only; other fences, invalid JSON, and non-mapping JSON blocks are ignored rather than reported.
- [x] A block is classified as a ready example when it carries `ticket_id` and either `modified_files` or the ready status, and as a question example when it carries `ticket_id` and `question`; blocks carrying neither classification are ignored.
- [x] Placeholder substitution is recursive for `<ticket_id>` and the documented timestamp placeholder family; unknown placeholders remain in place so the parser error names them.
- [x] `validate_markdown_signal_examples(markdown, ticket_id=...)` validates each classified block through the real parsers and returns indexed error strings; valid ready and question examples return no errors; the stale question block is rejected naming its missing fields.
- [x] A repository test validates `.agents/skills/implement-ticket-runner/SKILL.md`; it passes after T131 and fails if an embedded Signal example that the parsers reject is reintroduced.
- [x] Targeted tests pass; Ruff and mypy are clean on every changed file.

**Verified:** 2026-10-30 — 12 targeted domain and skill contract tests, 519 domain and skills tests, full suite 2,153 passed / 4 skipped; Ruff and mypy clean on changed files. Standards and Spec code review completed with zero findings above Low.
