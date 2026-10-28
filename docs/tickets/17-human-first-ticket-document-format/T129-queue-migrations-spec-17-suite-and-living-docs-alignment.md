# T129: Queue Migrations, End-to-End Spec 17 Verification Suite, and Spec-Closing Living Docs Alignment

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/17-human-first-ticket-document-format.md

**What to build:** Verify the full Spec 17 lifecycle end-to-end in `tests/specs/test_spec_17_human_first_ticket_format.py`, migrate `D:\Projects`'s active tickets to the `to-tickets` (Human+AI) format and live-test Target Projects' queues to the `to-ticket-runner` canonical format, and align ADRs (`0008`, `0012`, `0023`) and root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `docs/tickets/gotchas.md`).

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `tests/specs/test_spec_17_human_first_ticket_format.py`
  - `docs/tickets/15-multi-agent-hardening-and-live-test-site/` (migrate active tickets `T011`, `T012`, `T019`, `T099` to `to-tickets` Specimen B; archive/remove completed `T000-wayfinder-map.md`)
  - Live-test Target Projects (`D:\Repos\agent-skills`, `D:\Repos\agent-runner-driver`, `D:\Sandbox\ticket-runner-live-target`, `D:\Repos\empty-starter` — migrate active/welcome tickets to `to-ticket-runner` Specimen A and sync skills)
  - `docs/adr/0008-configurable-worker-execution-skill.md`
  - `docs/adr/0012-single-commit-ticket-lifecycle-and-ephemeral-queue-clean-slate.md`
  - `docs/adr/0023-wayfinder-ticket-type-label-convention.md`
  - `AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `docs/tickets/gotchas.md`
- **Seams:** End-to-end spec verification suite (`tests/specs/`), active ticket queues across `D:\Projects` and Target Projects, and root architectural documentation.
- **Existing-code anchors:** `tests/specs/test_spec_16_live_run_remediation.py`; `runner/tools/scaffold_sandbox.py` (welcome ticket template); `docs/adr/0008-configurable-worker-execution-skill.md`, `docs/adr/0012-single-commit-ticket-lifecycle-and-ephemeral-queue-clean-slate.md`, `docs/adr/0023-wayfinder-ticket-type-label-convention.md`.
- **Verify:** `py -3 -m pytest`

**Blocked by:** T125, T126, T127, T128

- [ ] `tests/specs/test_spec_17_human_first_ticket_format.py` exercises the complete Spec 17 lifecycle: Specimen A queue parse, `to-tickets` dialect rejection diagnostic, Pre-Dispatch `HITL` gate (guidance injection, skip with `**Status note:**`, and abort), Worker checkbox tick acceptance vs unauthorized edit rejection (consuming an attempt and restoring baseline), `EvidenceCard.unticked_criteria` surfacing, and in-place bold-label header finalization and archive relocation.
- [ ] Active tickets in `D:\Projects\docs\tickets\15-multi-agent-hardening-and-live-test-site\` (`T011`, `T012`, `T019`, `T099`) are migrated to the `to-tickets` (Specimen B Human+AI) format (with completed `T000-wayfinder-map.md` relocated to `completed/`), while historical archived tickets in `D:\Projects` remain untouched.
- [ ] Active/welcome tickets and `.agents/skills/` across the live-test Target Projects (`D:\Repos\agent-skills`, `D:\Repos\agent-runner-driver`, `D:\Sandbox\ticket-runner-live-target`, `D:\Repos\empty-starter`) and `runner/tools/scaffold_sandbox.py` use the `to-ticket-runner` (Specimen A) canonical format and `implement-ticket-runner` default skill.
- [ ] ADRs `0008`, `0012`, and `0023` and root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`, `docs/tickets/gotchas.md`) are updated to reflect the dual-track skills (`to-tickets`/`implement` vs `to-ticket-runner`/`implement-ticket-runner`), Specimen A/B formats, Pre-Dispatch `HITL` gate, and dispatch-baseline tick boundary, and the full `pytest` suite passes with 0 failures.
