# T126: Pre-Dispatch `HITL` Gate in Gatekeeper, Intervention Port, and Terminal/Discord Prompts

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/17-human-first-ticket-document-format.md

**What to build:** Halt autonomous execution **before** spawning any Worker subprocess whenever `ticket_runner.py` encounters a ticket with `**Mode:** HITL` (or `**Status:** blocked`), transitioning to `WAITING_FOR_USER` and prompting the human via Terminal or Discord to provide guidance and proceed, skip the ticket, or cancel the run.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/ports/intervention.py`
  - `runner/adapters/ui/terminal_prompts.py`
  - `runner/application/ticket_processor.py`
  - `runner/application/gatekeeper.py`
  - `runner/application/queue_orchestrator.py`
  - `tests/fakes/fake_intervention.py`
  - `tests/unit/application/test_ticket_processor.py`
  - `tests/unit/adapters/test_terminal_prompts.py`
- **Seams:** Pre-dispatch check in `GatekeeperTicketProcessor._process_ticket` / `VerificationLoop.run` and human prompt seam on `InterventionGateway`.
- **Existing-code anchors:** `InterventionAction`, `InterventionDecision`, and `InterventionGateway` in `runner/ports/intervention.py`; `TerminalInterventionGateway` in `runner/adapters/ui/terminal_prompts.py`; `FakeInterventionGateway` in `tests/fakes/fake_intervention.py`; `GatekeeperTicketProcessor._process_ticket` in `runner/application/ticket_processor.py`.
- **Verify:** `py -3 -m pytest tests/unit/application/test_ticket_processor.py tests/unit/adapters/test_terminal_prompts.py -x`

**Blocked by:** T124 (Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer)

- [ ] When `GatekeeperTicketProcessor` / `VerificationLoop` picks up a ticket with `ticket.mode == "HITL"` (or `ticket.status == TicketStatus.BLOCKED`), the Gatekeeper does not invoke `cycle_runner` before consulting the operator.
- [ ] Prior to prompting, the Runner transitions state to `WAITING_FOR_USER` (`StateCoordinator.transition_to_waiting_for_user` and `RunState.WAITING_FOR_USER` status event), updates the Discord Status Card when Discord is enabled, and schedules presence escalation if away.
- [ ] `InterventionGateway`, `TerminalInterventionGateway`, and `FakeInterventionGateway` support the pre-dispatch `HITL` gate with three operator outcomes:
  1. **Proceed with human guidance**: Operator provides instructions/decision text, which is prepended to the Worker's initial prompt before Worker execution begins.
  2. **Skip ticket**: Marks the ticket `**Status:** skipped` with `**Status note:** Skipped by operator at HITL pre-dispatch gate` and advances to the next ticket without spawning a Worker.
  3. **Cancel / Abort run**: Raises `UserAbortError` and stops `ticket_runner.py` immediately.
