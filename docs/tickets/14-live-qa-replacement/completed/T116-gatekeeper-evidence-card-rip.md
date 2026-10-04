# T116 — Gatekeeper and Evidence Card consumers go silent
Status: completed
Completed: 2026-10-04T06:57:00Z
Spec: docs/specs/14-live-qa-replacement.md
Blocked by: T115

### Requirements
- Remove every surviving consumer of scenario data in the verification path: the `EvidenceCard` value object loses its scenario field; the Gatekeeper drops the scenario sourcing chain, the empty-manual-verification warning, the commit-body scenario injection, the terminal checklist print, and smoke-log appending; `RuntimePaths` loses the smoke-log path helper; the terminal approval panel and the Discord Evidence Card embed drop their scenario checklist sections and the scenario-specific Discord field packing/truncation that exists only for that checklist. The fail-closed human-approval contract is untouched: in `"human"` mode, no commit or pass is reachable without an explicit APPROVE. Secret scrubbing on all surviving embed content remains.
- Rewrite the Spec-13 spec-contract tests that asserted scenario counts (`tests/specs/test_spec_13_verification_and_approval.py` lines ~190/226) to assert the inverse: cards and parsed tickets carry no scenario data. Extend the primary verification-loop seam (fake approval gateway + fake Discord gateway) to assert no smoke log is ever written.
- Jump-start:
  - Files to touch: `runner/domain/evidence.py` (scenario coercion ~79–101), `runner/application/gatekeeper.py` (sourcing 1191–1208, warning 1255–1264, injection 1270–1289, print 1291–1314, `_append_smoke_log` 976–1041, call 1317), `runner/domain/runtime_paths.py` (`smoke_log_path` 149–163), `runner/adapters/ui/terminal_approval.py` (rendering 110–122), `runner/adapters/discord/approval.py` (scenario embed fields 165–223).
  - Seams to work at: `tests/unit/application/test_gatekeeper_human_approval.py` (fail-closed tests must pass unmodified in spirit), `tests/integration/test_discord_e2e.py` (highest seam — full lifecycle with `FakeDiscordGateway`), `tests/unit/adapters/test_terminal_approval.py`, `test_discord_approval.py`, `test_runtime_paths.py`, `test_evidence.py`.
  - Verification: `python -m pytest` full suite green.

### Acceptance Criteria
- `EvidenceCard` carries no scenario field; terminal panel and Discord embed render without a checklist section; the scenario-only embed field packing code is gone while the surviving fields keep their 1024/25-limit handling.
- A full passing verification cycle in human mode produces no `smoke_log_*` file under `.agent/`.
- Fail-closed behavior unchanged: missing gateway, unhandled decision, or operator abort still prevent commit.
- Commit bodies no longer embed scenario checklists; single-commit-per-ticket contract (ADR 0012) otherwise unchanged.
- No `.agent/` path traversal protections are weakened while `smoke_log_path` is deleted (the traversal guard pattern must survive in `RuntimePaths` for remaining paths).

### Smoke Scenarios
**Scenario: gate cycle writes no smoke log**
- Setup: None (runs from repo root with Python).
- Why: The Gatekeeper must stop authoring verification logs and rendering checklists entirely so durable verdicts come solely from the human's live-qa session.
- Steps:
  1. Run the self-contained verification loop runner:
     ```powershell
     python -c "import asyncio, io, shutil; from datetime import datetime, timezone; from pathlib import Path; from runner.domain.ticket import Ticket, TicketStatus; from runner.domain.signal import ReadySignal, SignalStatus; from runner.application.gatekeeper import VerificationLoop, VerificationReport, CommandOutcome; from runner.application.handoff_coordinator import WorkerRunResult, SingleCycleStatus; from runner.adapters.ui.terminal_approval import TerminalApprovalAdapter; from tests.fakes.fake_intervention import FakeInterventionGateway; from tests.fakes.fake_signal_repository import FakeSignalRepository; from runner.domain.runtime_paths import RuntimePaths; tmp = Path('scratch_smoke_test'); tmp.mkdir(exist_ok=True); agent_dir = tmp / '.agent'; agent_dir.mkdir(exist_ok=True); paths = RuntimePaths(root_dir=agent_dir); ticket = Ticket(id='T116', title='Smoke Test Ticket', status=TicketStatus.PENDING, spec_path='docs/specs/14-test.md', requirements=('Test',), acceptance_criteria=('Pass',), gotchas=(), path=tmp / 'T116.md'); ready = ReadySignal(ticket_id='T116', status=SignalStatus.READY_FOR_VERIFICATION, modified_files=('runner/application/gatekeeper.py',), self_review_notes='Done', new_gotchas=(), timestamp=datetime.now(timezone.utc)); sig_repo = FakeSignalRepository(); sig_repo.seed_ready(ready); runner = type('DummyRunner', (), {'__call__': lambda self, *a, **k: asyncio.sleep(0, result=WorkerRunResult(status=SingleCycleStatus.READY, session_id='ses_s'))})(); executor = type('DummyExec', (), {'verify': lambda self, *a: asyncio.sleep(0, result=VerificationReport(passed=True, results=(CommandOutcome('test', 'pytest', 0, False, 'pass'),), diagnostics=(), skipped_commands=()))})(); adapter = TerminalApprovalAdapter(stdin=type('MockStdin', (), {'read': lambda self, n=1: 'y', 'readline': lambda self: 'y\n', 'isatty': lambda self: True})()); loop = VerificationLoop(ticket=ticket, cycle_runner=runner, signal_repository=sig_repo, executor=executor, intervention_gateway=FakeInterventionGateway(), approval_gateway=adapter, approval_mode='human', runtime_paths=paths); res = asyncio.run(loop.run()); smoke_logs = list(agent_dir.glob('smoke_log_*.md')); assert res.is_passed; assert len(smoke_logs) == 0; shutil.rmtree(tmp); print('SUCCESS: Verified gate cycle authors no smoke log and Evidence Card renders without scenarios')"
     ```
  2. Observe the rendered Evidence Card panel and final confirmation message.
- Expected: Evidence Card renders with Ticket, Test Status, and Evidence Paths, with no "Smoke Scenarios" checklist section. The script prints `SUCCESS: Verified gate cycle authors no smoke log and Evidence Card renders without scenarios`.

### Gotchas
- `runner/adapters/discord/approval.py` truncation logic (lines 180–223) is shared-shape code: remove only the scenario field loop, keep limits for evidence paths and other fields.
- Old completed tickets' `### Smoke Scenarios` must NOT break the Queue/Doctor scan even though Gatekeeper no longer parses them (guaranteed by T115's inert-parser work — verify, don't assume).
