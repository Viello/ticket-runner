# T137: Standalone `-ticket-runner` Skills, Cleaned Interactive Skills, and Segregation Contract

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/19-dual-track-skill-segregation.md

**What to build:** Complete the dual-track skill split across all four supporting skills in both `D:\Projects\.agents\skills\` and `D:\Repos\agent-skills\` (`Viello/agent-skills`). Author self-contained `code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, and `handoff-ticket-runner` skill directories (each with `SKILL.md` marked `disable-model-invocation: true` and `agents/openai.yaml`) that route every human-blocking decision through `.agent/questions/<ticket_id>.json` (`WAITING_FOR_USER` on Discord or Terminal) while deferring Signal JSON schemas to the prompt's authoritative `Ready Signal Protocol` and `Question Signal Protocol` sections. Update `implement-ticket-runner` to reference the `-ticket-runner` review and debugging skills. Restore `code-review`, `security-review`, `diagnosing-bugs`, and `handoff` to pure interactive Human + AI skills with zero `.agent/signals/` or `.agent/questions/` instructions, update `ask-matt` and `D:\Repos\agent-skills\README.md` (54 canonical skills), and lock the boundary with a repository skill-segregation contract test.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `.agents/skills/code-review-ticket-runner/SKILL.md` & `.agents/skills/code-review-ticket-runner/agents/openai.yaml` (new; mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/security-review-ticket-runner/SKILL.md` & `.agents/skills/security-review-ticket-runner/agents/openai.yaml` (new; mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md` & `.agents/skills/diagnosing-bugs-ticket-runner/agents/openai.yaml` (new; mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/handoff-ticket-runner/SKILL.md` & `.agents/skills/handoff-ticket-runner/agents/openai.yaml` (new; mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/implement-ticket-runner/SKILL.md` (mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/code-review/SKILL.md` (mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/security-review/SKILL.md` (mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/diagnosing-bugs/SKILL.md` (mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/handoff/SKILL.md` (mirror in `D:\Repos\agent-skills\`)
  - `.agents/skills/ask-matt/SKILL.md` (mirror in `D:\Repos\agent-skills\`)
  - `D:\Repos\agent-skills\README.md`
  - `tests/unit/skills/test_dual_track_skills.py`
  - `tests/unit/skills/test_signal_skill_contract.py`
  - `tests/unit/application/test_prompt_builder.py` (`test_implement_ticket_runner_skill_mandates_explicit_file_read_for_code_review_and_agents_md`)
- **Seams:** Skill YAML frontmatter (`name`, `description`, `disable-model-invocation: true`), `agents/openai.yaml` interface metadata, `validate_markdown_signal_examples` in `runner/domain/signal_contract.py`, `generate_catalog_readme` in `scripts/publish_agent_skills.py`, and the 6-pair skill segregation contract in `tests/unit/skills/test_dual_track_skills.py`.
- **Existing-code anchors:** `.agents/skills/implement-ticket-runner/SKILL.md` and `.agents/skills/implement-ticket-runner/agents/openai.yaml`; `test_implement_ticket_runner_skill_conforms_to_autonomous_spec` and `test_implement_skill_is_pure_human_ai_interactive` in `tests/unit/skills/test_dual_track_skills.py`; `test_canonical_execution_skill_passes_contract` in `tests/unit/skills/test_signal_skill_contract.py`.
- **Verify:** `py -3 -m pytest tests/unit/skills/ tests/unit/application/test_prompt_builder.py -k "implement_ticket_runner_skill or skills or contract" -q`

**Blocked by:** None (can start immediately)

- [ ] `code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, and `handoff-ticket-runner` exist in both `.agents/skills/` and `D:\Repos\agent-skills\` with valid YAML frontmatter (`disable-model-invocation: true`) and `agents/openai.yaml`, contain no raw fenced JSON Signal blocks (`validate_markdown_signal_examples` returns `[]`), and defer Signal payload schemas to the prompt's `Ready Signal Protocol` and `Question Signal Protocol` sections.
- [ ] `code-review-ticket-runner` reviews uncommitted working-tree changes (`git diff HEAD` plus untracked files from `git status --short`) across `Standards`, `Spec`, and conditional `Security` (referencing `.agents/skills/security-review-ticket-runner/SKILL.md` when `Security:` is `required`, `true`, or `yes`), and instructs the Worker to emit `.agent/questions/<ticket_id>.json` when a `CRITICAL`/`HIGH` finding or spec contradiction requires a human architectural or policy decision.
- [ ] `security-review-ticket-runner` audits uncommitted changes across trust boundaries and instructs the Worker to emit `.agent/questions/<ticket_id>.json` when fixing a `CRITICAL`/`HIGH` security issue requires missing credentials, external secrets, or a human architectural/policy decision.
- [ ] `diagnosing-bugs-ticket-runner` guides autonomous feedback-loop construction and the four-phase Stuck-Test-Suite Protocol (`HANG`, `CASCADE`, `ENV`, `FLAKY`), forbids emitting `.agent/signals/<ticket_id>_ready.json` while the suite is failing or stuck, and instructs the Worker to emit `.agent/questions/<ticket_id>.json` (reporting classification, last output line or top repeating error, and isolation outcome) when a reproduction loop cannot be built or Phase D isolation fails after 1–2 attempts.
- [ ] `handoff-ticket-runner` writes the structured handoff checkpoint directly to `.agent/checkpoints/<ticket_id>/handoff.md` (covering Active Context, Completed Work, Pending State, Suggested `-ticket-runner` Skills, and Immediate Next Steps) without touching `STATUS.md`, committing, or prompting `[y/n]`, and `implement-ticket-runner/SKILL.md` directs the Worker to read `code-review-ticket-runner`, `security-review-ticket-runner`, and `diagnosing-bugs-ticket-runner`.
- [ ] All six interactive Human + AI skills (`to-tickets`, `implement`, `code-review`, `security-review`, `diagnosing-bugs`, `handoff`) in both `.agents/skills/` and `D:\Repos\agent-skills\` contain zero references to `.agent/signals/`, `.agent/questions/`, or `.agent/checkpoints/`, carry a one-line note pointing autonomous Ticket Runner runs to their `-ticket-runner` counterpart, and `ask-matt/SKILL.md` plus `D:\Repos\agent-skills\README.md` document the 6-pair dual-track matrix across all 54 canonical skills.
- [ ] Targeted skill and contract tests pass; Ruff and mypy are clean on every changed Python file.

