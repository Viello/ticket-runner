# T128: Dual-Track Skills Catalog (`Viello/agent-skills`) and Local `.agents/skills/` Vendoring

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/17-human-first-ticket-document-format.md

**What to build:** Split ticket authoring and execution in `Viello/agent-skills` (`D:\Repos\agent-skills`) and `D:\Projects\.agents/skills/` into the two explicit tracks defined in Spec 17 — Human+AI Interactive (`to-tickets` + `implement`) and Autonomous + Human-Compatible Ticket Runner (`to-ticket-runner` + `implement-ticket-runner`) — and align `code-review`, `ask-matt`, `smoke-fail`, and `README.md` (50 canonical skills total).

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `D:\Repos\agent-skills\to-ticket-runner\SKILL.md` & `D:\Repos\agent-skills\to-ticket-runner\agents\openai.yaml`
  - `D:\Repos\agent-skills\implement-ticket-runner\SKILL.md` & `D:\Repos\agent-skills\implement-ticket-runner\agents\openai.yaml`
  - `D:\Repos\agent-skills\to-tickets\SKILL.md`
  - `D:\Repos\agent-skills\implement\SKILL.md`
  - `D:\Repos\agent-skills\code-review\SKILL.md`
  - `D:\Repos\agent-skills\ask-matt\SKILL.md`
  - `D:\Repos\agent-skills\smoke-fail\SKILL.md`
  - `D:\Repos\agent-skills\README.md`
  - `D:\Projects\.agents\skills\` (vendored copies of `to-ticket-runner`, `implement-ticket-runner`, `to-tickets`, `implement`, `code-review`, `ask-matt`, `smoke-fail`)
  - `D:\Projects\scripts\publish_agent_skills.py`
  - `D:\Projects\tests\unit\adapters\test_ticket_parser.py` (smoke-fail template test)
- **Seams:** Skill instructions and templates in `D:\Repos\agent-skills` and vendored copies in `D:\Projects\.agents\skills/`, plus catalog verification in `scripts/publish_agent_skills.py`.
- **Existing-code anchors:** Specimen A and Specimen B in `docs/specs/17-human-first-ticket-document-format.md`; `test_smoke_fail_recovery_skill_ticket_runner_template_is_valid` in `tests/unit/adapters/test_ticket_parser.py`; `verify_tarball_endpoint` in `scripts/publish_agent_skills.py`.
- **Verify:** `py -3 -m pytest tests/unit/adapters/test_ticket_parser.py tests/unit/skills/ -x`

**Blocked by:** T127 (Default `implement-ticket-runner` Execution Skill Plumbing and Canonical Prompt Builder)

- [ ] `to-ticket-runner` (`SKILL.md` + `agents/openai.yaml`) is authored in `D:\Repos\agent-skills` and vendored into `D:\Projects\.agents\skills/to-ticket-runner/`, generating Specimen A 5-section tickets (`**Mode:** AFK | HITL`, `**Status:** pending`, `**Spec:**`, `**Blocked by:**`, `**Security:**`, `**Reasoning:**`, `## What to build`, `## Jump-start`, `## Acceptance criteria`, `## Smoke scenarios`, `## Gotchas`).
- [ ] `implement-ticket-runner` (`SKILL.md` + `agents/openai.yaml`) is authored in `D:\Repos\agent-skills` and vendored into `D:\Projects\.agents\skills/implement-ticket-runner/`, containing strictly autonomous Worker instructions (TDD at `## Jump-start` seams, Stuck-Test-Suite Protocol, 3-axis `/code-review`, flipping `- [ ]` → `- [x]` in `## Acceptance criteria`, severity-gated `.agent/questions/<ticket_id>.json` escalation, emitting `.agent/signals/<ticket_id>_ready.json`, and never committing or relocating files).
- [ ] `to-tickets/SKILL.md` is updated to Specimen B (compact Human+AI interactive format under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` with `completed/` archive subfolder, `**Status:** ready-for-agent`, inline `**What to build:**`, `**Jump-start:**`, `**Blocked by:**`, and `- [ ]` checkboxes).
- [ ] `implement/SKILL.md` is updated to the pure Human+AI interactive skill (zero autonomous signal noise) supporting both `to-tickets` files and manual interactive execution of `to-ticket-runner` files (closing `to-ticket-runner` files with strict `TicketMarkdownParser`-compatible headers: `**Status:** completed`, `**Completed:** <ISO-8601-UTC>`, and `**Status note:** reviewed; <summary>`, then relocating to `completed/` and committing).
- [ ] `code-review/SKILL.md` runs the 3-axis parallel review (`Standards`, `Spec`, and `Security` referencing `.agents/skills/security-review/SKILL.md` with severity-gated escalation), `smoke-fail/SKILL.md` uses the Specimen A `<ticket-runner-template>`, `ask-matt/SKILL.md` and `README.md` document both skill tracks (50 canonical skills total), and `test_smoke_fail_recovery_skill_ticket_runner_template_is_valid` passes.
