# T131: Prompt Renders Domain Protocol and Execution Skill Defers

**Status:** done (reviewed; prompt renders domain protocol and skill defers)
**Completed:** 2026-10-30T16:10:00Z
**Labels:** ready-for-agent
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** Render the prompt's ready and question protocol sections from the T130 domain renderers instead of hand-written bullets. Each rendered section declares itself authoritative over the execution skill or any other document. The prompt teaches the object Gotcha shape and notes that plain strings are also accepted, without advertising the `fix` alias. The canonical execution skill drops both embedded JSON examples and points at the prompt's protocol section as the only schema-adjacent text.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/application/prompt_builder.py`
  - `.agents/skills/implement-ticket-runner/SKILL.md`
  - `tests/unit/application/test_prompt_builder.py`
  - `tests/unit/skills/test_dual_track_skills.py`
- **Seams:** The `## Operational Guardrails & Completion Protocol` ready and question sections in `build_prompt`; the blocked-escalation and signal-readiness sections in the execution skill.
- **Existing-code anchors:** The f-string prompt template in `runner/application/prompt_builder.py`; `render_ready_signal_protocol` and `render_question_signal_protocol` from T130; existing prompt assertions in `tests/unit/application/test_prompt_builder.py`.
- **Verify:** `py -3 -m pytest tests/unit/application/test_prompt_builder.py tests/unit/skills/test_dual_track_skills.py -q`

**Blocked by:** T130

- [x] The prompt's ready protocol section is produced by `render_ready_signal_protocol` and contains every `ReadySignal` field name plus the exact `"ready_for_verification"` status; the question section is produced by `render_question_signal_protocol` and contains every `QuestionSignal` field name.
- [x] Each protocol section states that it is authoritative over the execution skill or any other document when examples disagree.
- [x] The prompt shows the canonical `{problem, solution}` Gotcha shape and one line stating that plain strings are also accepted; the `fix` alias is not advertised.
- [x] `.agents/skills/implement-ticket-runner/SKILL.md` contains no embedded ready or question Signal JSON example and names the prompt protocol section as the schema pointer, preserving the rest of the execution discipline.
- [x] Prompt-builder and dual-track skill tests pass; Ruff and mypy are clean on every changed file.

**Verified:** 2026-10-30 — 45 prompt-builder and dual-track skill tests, 544 application tests, 182 domain tests; Ruff and mypy clean on all changed files. Reviewed against Standards and Spec axes with zero findings above Low.
