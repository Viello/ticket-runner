# T138: Prompt Builder, Ready Signal Protocol, and Handoff Coordinator `-ticket-runner` Wiring

**Status:** completed
**Completed:** 2026-11-03T10:17:00Z
**Status note:** reviewed; rewired PromptBuilder, ready Signal protocol text, and Context Handoff prompt to reference segregated -ticket-runner skills
**Labels:** ready-for-agent
**Parent:** docs/specs/19-dual-track-skill-segregation.md

**What to build:** Rewire Ticket Runner's prompt generation, authoritative Ready Signal protocol text, and 135k-token Context Handoff prompt to reference the segregated `-ticket-runner` skills. When the Runner builds a task prompt or handoff instruction for an autonomous Worker, every skill path rendered into the prompt points to `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/security-review-ticket-runner/SKILL.md`, `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`, and `.agents/skills/handoff-ticket-runner/SKILL.md`.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/signal_schema.py`
  - `runner/application/prompt_builder.py`
  - `runner/application/handoff_coordinator.py`
  - `tests/unit/domain/test_signal_schema.py`
  - `tests/unit/application/test_prompt_builder.py`
  - `tests/unit/application/test_handoff_coordinator.py`
  - `tests/specs/test_spec_03_worker.py`
- **Seams:** `render_ready_signal_protocol` in `runner/domain/signal_schema.py`; `DEFAULT_INVARIANTS`, `_with_token_budget`, and `build_prompt` in `runner/application/prompt_builder.py`; `HANDOFF_PROMPT_TEMPLATE` and `HandoffCoordinator.build_handoff_prompt` in `runner/application/handoff_coordinator.py`.
- **Existing-code anchors:** `render_ready_signal_protocol` in `runner/domain/signal_schema.py`; `security_review_line`, `DEFAULT_INVARIANTS`, and `_with_token_budget` in `runner/application/prompt_builder.py`; `HANDOFF_PROMPT_TEMPLATE` in `runner/application/handoff_coordinator.py`.
- **Verify:** `py -3 -m pytest tests/unit/domain/test_signal_schema.py tests/unit/application/test_prompt_builder.py tests/unit/application/test_handoff_coordinator.py tests/specs/test_spec_03_worker.py -q`

**Blocked by:** T137 (Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract)

- [x] `render_ready_signal_protocol` in `runner/domain/signal_schema.py` instructs the Worker to emit the ready Signal after reading `AGENTS.md` and `.agents/skills/code-review-ticket-runner/SKILL.md` with its file-reading tool.
- [x] `PromptBuilder.build` / `build_prompt` in `runner/application/prompt_builder.py` directs the Worker to read `.agents/skills/code-review-ticket-runner/SKILL.md` for pre-signal review, `.agents/skills/security-review-ticket-runner/SKILL.md` when `ticket.security_required` is true, and `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md` for non-trivial test failures or hard bugs.
- [x] `DEFAULT_INVARIANTS` and `_with_token_budget` in `runner/application/prompt_builder.py` reference `.agents/skills/handoff-ticket-runner/SKILL.md` for the 135k-token checkpoint handoff invariant.
- [x] `HANDOFF_PROMPT_TEMPLATE` and `HandoffCoordinator.build_handoff_prompt` in `runner/application/handoff_coordinator.py` instruct the Worker to execute `.agents/skills/handoff-ticket-runner/SKILL.md` and save the checkpoint directly to `.agent/checkpoints/<ticket_id>/handoff.md`.
- [x] Targeted domain, application, and Spec 03 tests pass; Ruff and mypy are clean on every changed file.
