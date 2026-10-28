"""Unit tests for VerificationLoop manual verification surfacing (T069)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    VerificationLoop,
    VerificationReport,
    verify_ticket_mutation,
)
from runner.application.handoff_coordinator import (
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.domain.config import VerificationConfig
from runner.domain.evidence import ApprovalDecision
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_approval_gateway import FakeApprovalGateway
from tests.fakes.fake_intervention import FakeInterventionGateway


@dataclass(frozen=True)
class _LegacyReadySignal(ReadySignal):
    manual_verification: tuple[dict, ...] = ()
    _manual_verification_was_present: bool = False

    @property
    def manual_verification_is_default(self) -> bool:
        return not self._manual_verification_was_present


def _make_ticket(ticket_id: str = "T069") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Smoke Scenarios Surfacing",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/10-stuck-detection-and-observability.md",
        requirements=("Surfacing manual verification in gatekeeper",),
        acceptance_criteria=("Full checklist on pass",),
        gotchas=(),
        path=Path(f"docs/tickets/10-stuck-detection-and-observability/{ticket_id}-test.md"),
    )


def _passing_report(cmd: str = "pytest -q") -> VerificationReport:
    outcome = CommandOutcome(
        label="test", command=cmd, exit_code=0, timed_out=False, tail="1 passed"
    )
    return VerificationReport(
        passed=True, results=(outcome,), diagnostics=(), skipped_commands=()
    )


class _StubCycleRunner:
    def __init__(self, response: WorkerRunResult) -> None:
        self._response = response

    async def __call__(
        self,
        ticket: Ticket,
        *,
        session_id: str | None = None,
        prompt: str | None = None,
    ) -> WorkerRunResult:
        return self._response


class _StubExecutor(GatekeeperCommandExecutor):
    def __init__(self, report: VerificationReport) -> None:
        super().__init__()
        self._report = report

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        return self._report


class _StubSignalRepo:
    def __init__(self, signal: ReadySignal | None) -> None:
        self._signal = signal
        self.consumed = False

    def read_ready(self, ticket_id: str) -> ReadySignal | None:
        return self._signal

    def consume_ready(self, ticket_id: str) -> None:
        self.consumed = True

    def read_pending_question(self, ticket_id: str) -> Any:
        return None

    def clean_question(self, ticket_id: str) -> None:
        pass

    def purge(self, ticket_id: str) -> None:
        pass

    def write_answer(self, ticket_id: str, answer: str) -> Any:
        return None


@pytest.fixture
def sample_scenarios() -> tuple[dict[str, str], ...]:
    return (
        {
            "name": "Full terminal checklist verification",
            "setup": "Start terminal UI in test harness",
            "steps": "1. Run runner\n2. Wait for gatekeeper pass",
            "expected": "Checklist is printed with full details",
        },
        {
            "name": "Discord summary verification",
            "setup": "Configure fake discord adapter",
            "steps": "1. Trigger pass\n2. Check adapter calls",
            "expected": "Discord summary received with scenario names",
        },
    )


@pytest.fixture
def mixed_scenarios() -> tuple[dict[str, Any], ...]:
    return (
        {
            "name": "Auto-covered scenario",
            "setup": "Auto-covered setup",
            "steps": "1. Run auto test",
            "expected": "Auto test passes",
            "auto_covered": True,
            "update_notes": "Updates: T001 — Old scenario name",
        },
        {
            "name": "Manual-only scenario",
            "setup": "Manual setup",
            "steps": "1. Verify manually",
            "expected": "Manual verification passes",
            "auto_covered": False,
            "update_notes": "",
        },
    )


def test_absent_manual_verification_backward_compatible():
    """A ReadySignal payload without manual_verification parses with () and emits nothing."""
    ticket = _make_ticket()
    ready = ReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        # manual_verification defaults to ()
    )
    assert not hasattr(ready, "manual_verification")

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    notified: list[str] = []

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        notify=notified.append,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    # Nothing emitted for absent manual_verification
    assert not notified


def test_legacy_manual_verification_produces_no_terminal_output_and_no_warnings(sample_scenarios, caplog):
    """When a legacy ready signal contains manual_verification, Gatekeeper prints no scenarios and emits no warning."""
    ticket = _make_ticket()
    ready = _LegacyReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    notified: list[str] = []

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        notify=notified.append,
    )

    with caplog.at_level("WARNING"):
        res = asyncio.run(loop.run())
    assert res.is_passed
    assert len(notified) == 0
    assert not any("manual_verification" in r.message for r in caplog.records)


def test_legacy_manual_verification_does_not_inject_commit_body(sample_scenarios):
    """Gatekeeper does not inject scenario checklists into commit bodies."""
    ticket = _make_ticket()
    ready = _LegacyReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        manual_verification=sample_scenarios,
        _manual_verification_was_present=True,
    )

    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    mock_git = MagicMock()
    mock_git.commit_ticket = AsyncMock(return_value="commit_sha_123")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        git_operations=mock_git,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    mock_git.commit_ticket.assert_not_called()




def test_ready_signal_tolerates_malformed_legacy_manual_verification():
    """Legacy manual_verification payloads (even malformed) are ignored via unknown-key tolerance."""
    payload_bad_entry = {
        "ticket_id": "T069",
        "status": "ready_for_verification",
        "modified_files": ["foo.py"],
        "self_review_notes": "ok",
        "new_gotchas": [],
        "timestamp": "2026-09-21T00:00:00+00:00",
        "manual_verification": ["not-a-dict"],
    }
    signal = ReadySignal.parse(payload_bad_entry, "T069")
    assert not hasattr(signal, "manual_verification")

    payload_bad_type = {
        "ticket_id": "T069",
        "status": "ready_for_verification",
        "modified_files": ["foo.py"],
        "self_review_notes": "ok",
        "new_gotchas": [],
        "timestamp": "2026-09-21T00:00:00+00:00",
        "manual_verification": [{"name": 123}],
    }
    signal = ReadySignal.parse(payload_bad_type, "T069")
    assert not hasattr(signal, "manual_verification")


def test_legacy_manual_verification_tolerated_in_signal():
    """Legacy manual_verification with newlines or ANSI is ignored without crashing."""
    payload = {
        "ticket_id": "T069",
        "status": "ready_for_verification",
        "modified_files": ["foo.py"],
        "self_review_notes": "ok",
        "new_gotchas": [],
        "timestamp": "2026-09-21T00:00:00+00:00",
        "manual_verification": [
            {
                "name": "Scenario\r\nName\x1b[31mRed\x1b[0m",
                "setup": "Line1\nLine2",
                "steps": "Step",
                "expected": "Pass",
            }
        ],
    }
    signal = ReadySignal.parse(payload, "T069")
    assert signal.ticket_id == "T069"
    assert not hasattr(signal, "manual_verification")


def test_no_smoke_log_appended_after_pass(
    mixed_scenarios: tuple[dict[str, Any], ...],
    tmp_path: Path,
) -> None:
    """Verify that after a passing verification cycle, no smoke log is ever written under .agent/."""
    ticket = _make_ticket("T078")
    ready = _LegacyReadySignal(
        ticket_id=ticket.id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/application/gatekeeper.py",),
        self_review_notes="Done",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        scope="test-spec",
        manual_verification=mixed_scenarios,
        _manual_verification_was_present=True,
    )
    cycle_result = WorkerRunResult(
        status=SingleCycleStatus.READY,
        occupancy=1000,
        session_id="ses_123",
        resources_accessed=frozenset({"code-review", "AGENTS.md", "security-review"}),
    )
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_StubCycleRunner(cycle_result),
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        runtime_paths=runtime_paths,
    )

    res = asyncio.run(loop.run())
    assert res.is_passed

    smoke_logs = list((tmp_path / ".agent").glob("smoke_log_*.md"))
    assert len(smoke_logs) == 0


def _create_disk_ticket(
    tmp_path: Path,
    ticket_id: str = "T125",
    content: str | None = None,
) -> tuple[Ticket, Path]:
    ticket_file = tmp_path / f"{ticket_id}-test.md"
    if content is None:
        content = (
            f"# {ticket_id} — Baseline Boundary Test\n"
            "**Mode:** AFK\n"
            "**Status:** pending\n"
            "**Spec:** docs/specs/17-test.md\n"
            "\n"
            "## What to build\n"
            "The feature to build.\n"
            "\n"
            "## Jump-start\n"
            "- **Files/areas to touch:** `runner/foo.py`\n"
            "\n"
            "## Acceptance criteria\n"
            "- [ ] Criterion 1\n"
            "- [ ] Criterion 2\n"
            "- [ ] Criterion 3\n"
            "\n"
            "## Smoke scenarios\n"
            "- [ ] Scenario 1\n"
            "\n"
            "## Gotchas\n"
            "- Quirk 1\n"
        )
    ticket_file.write_text(content, encoding="utf-8")
    ticket = Ticket(
        id=ticket_id,
        title="Baseline Boundary Test",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/17-test.md",
        requirements=("The feature to build.",),
        acceptance_criteria=("Criterion 1", "Criterion 2", "Criterion 3"),
        gotchas=("- Quirk 1",),
        path=ticket_file,
    )
    return ticket, ticket_file


def _make_ready_signal(ticket_id: str = "T125") -> ReadySignal:
    return ReadySignal(
        ticket_id=ticket_id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("runner/foo.py",),
        self_review_notes="Verified",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        scope="test-spec",
    )


def test_verify_ticket_mutation_pure_unit() -> None:
    baseline = (
        "# T125 — Title\n"
        "**Status:** pending\n\n"
        "## What to build\n\n"
        "Feature description.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Criterion 1\n"
        "- [ ] Criterion 2\n\n"
        "## Gotchas\n\n"
        "- Quirk\n"
    )

    # 1. Identical content is valid
    ok, _ = verify_ticket_mutation(baseline, baseline)
    assert ok

    # 2. Flipping - [ ] to - [x] or - [X] is valid
    valid_edit = baseline.replace("- [ ] Criterion 1", "- [x] Criterion 1").replace(
        "- [ ] Criterion 2", "- [X] Criterion 2"
    )
    ok, msg = verify_ticket_mutation(baseline, valid_edit)
    assert ok
    assert msg == ""

    # 3. Modifying header fails
    bad_header = baseline.replace("**Status:** pending", "**Status:** completed")
    ok, msg = verify_ticket_mutation(baseline, bad_header)
    assert not ok
    assert "outside '## Acceptance criteria'" in msg

    # 4. Modifying What to build fails
    bad_wtb = baseline.replace("Feature description.", "Hacked description.")
    ok, msg = verify_ticket_mutation(baseline, bad_wtb)
    assert not ok
    assert "outside '## Acceptance criteria'" in msg

    # 5. Modifying criterion wording fails
    bad_wording = baseline.replace("- [ ] Criterion 1", "- [x] Criterion 1 changed")
    ok, msg = verify_ticket_mutation(baseline, bad_wording)
    assert not ok
    assert "acceptance criterion text was modified" in msg

    # 6. Unchecking an existing criterion fails
    ticked_baseline = baseline.replace("- [ ] Criterion 1", "- [x] Criterion 1")
    unticked_edit = ticked_baseline.replace("- [x] Criterion 1", "- [ ] Criterion 1")
    ok, msg = verify_ticket_mutation(ticked_baseline, unticked_edit)
    assert not ok
    assert "un-ticking an existing criterion is prohibited" in msg

    # 7. Adding lines fails
    added_lines = baseline + "- [ ] Criterion 3\n"
    ok, msg = verify_ticket_mutation(baseline, added_lines)
    assert not ok
    assert "line count changed" in msg

    # 8. Deleting lines fails
    deleted_lines = baseline.replace("- [ ] Criterion 2\n", "")
    ok, msg = verify_ticket_mutation(baseline, deleted_lines)
    assert not ok
    assert "line count changed" in msg

    # 9. Modifying gotchas fails
    bad_gotchas = baseline.replace("- Quirk", "- Hacked quirk")
    ok, msg = verify_ticket_mutation(baseline, bad_gotchas)
    assert not ok
    assert "outside '## Acceptance criteria'" in msg


def test_dispatch_baseline_permits_ticking_acceptance_criteria(tmp_path: Path) -> None:
    ticket, ticket_file = _create_disk_ticket(tmp_path)
    ready = _make_ready_signal(ticket.id)

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        # Worker flips checkboxes in the ticket file on disk
        text = ticket_file.read_text(encoding="utf-8")
        updated = text.replace("- [ ] Criterion 1", "- [x] Criterion 1").replace(
            "- [ ] Criterion 2", "- [X] Criterion 2"
        )
        ticket_file.write_text(updated, encoding="utf-8")
        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_1",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    assert res.attempts == 1

    # Ticks are preserved on disk
    final_text = ticket_file.read_text(encoding="utf-8")
    assert "- [x] Criterion 1" in final_text
    assert "- [X] Criterion 2" in final_text
    assert "- [ ] Criterion 3" in final_text


def test_dispatch_baseline_rejects_header_mutation(tmp_path: Path) -> None:
    ticket, ticket_file = _create_disk_ticket(tmp_path)
    ready = _make_ready_signal(ticket.id)

    cycle_count = 0
    received_prompts: list[str] = []

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        nonlocal cycle_count
        cycle_count += 1
        prompt = kwargs.get("prompt")
        if prompt:
            received_prompts.append(prompt)

        if cycle_count == 1:
            # Unauthorized edit: changes header
            text = ticket_file.read_text(encoding="utf-8")
            hacked = text.replace("**Status:** pending", "**Status:** completed")
            ticket_file.write_text(hacked, encoding="utf-8")
        else:
            # Cycle 2: compliant edit
            text = ticket_file.read_text(encoding="utf-8")
            valid = text.replace("- [ ] Criterion 1", "- [x] Criterion 1")
            ticket_file.write_text(valid, encoding="utf-8")

        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_1",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    signal_repo = _StubSignalRepo(ready)
    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=signal_repo,
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    # Attempt was consumed by the rejection, so total attempts == 2
    assert res.attempts == 2
    assert cycle_count == 2

    # Baseline was restored after cycle 1 failure, and prompt informed worker
    assert len(received_prompts) == 1
    assert "outside '## Acceptance criteria'" in received_prompts[0]


def test_dispatch_baseline_rejects_modifying_criterion_wording(tmp_path: Path) -> None:
    ticket, ticket_file = _create_disk_ticket(tmp_path)
    ready = _make_ready_signal(ticket.id)

    cycle_count = 0
    received_prompts: list[str] = []

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        nonlocal cycle_count
        cycle_count += 1
        prompt = kwargs.get("prompt")
        if prompt:
            received_prompts.append(prompt)

        if cycle_count == 1:
            # Unauthorized edit: modifies wording of criterion
            text = ticket_file.read_text(encoding="utf-8")
            hacked = text.replace("- [ ] Criterion 1", "- [x] Criterion 1 (hacked)")
            ticket_file.write_text(hacked, encoding="utf-8")
        else:
            # Compliant edit
            text = ticket_file.read_text(encoding="utf-8")
            valid = text.replace("- [ ] Criterion 1", "- [x] Criterion 1")
            ticket_file.write_text(valid, encoding="utf-8")

        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_1",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    assert res.attempts == 2
    assert len(received_prompts) == 1
    assert "acceptance criterion text was modified" in received_prompts[0]


def test_dispatch_baseline_rejects_ticket_deletion(tmp_path: Path) -> None:
    ticket, ticket_file = _create_disk_ticket(tmp_path)
    ready = _make_ready_signal(ticket.id)

    cycle_count = 0

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        nonlocal cycle_count
        cycle_count += 1
        if cycle_count == 1:
            ticket_file.unlink()
        else:
            text = ticket_file.read_text(encoding="utf-8")
            ticket_file.write_text(
                text.replace("- [ ] Criterion 1", "- [x] Criterion 1"), encoding="utf-8"
            )

        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_1",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    assert res.attempts == 2
    assert ticket_file.is_file()


def test_evidence_card_populated_with_unticked_criteria(tmp_path: Path) -> None:
    ticket, ticket_file = _create_disk_ticket(tmp_path)
    ready = _make_ready_signal(ticket.id)

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        # Worker ticks only Criterion 1; leaves Criterion 2 and 3 unticked
        text = ticket_file.read_text(encoding="utf-8")
        updated = text.replace("- [ ] Criterion 1", "- [x] Criterion 1")
        ticket_file.write_text(updated, encoding="utf-8")
        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_1",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    fake_approval = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=_StubSignalRepo(ready),
        executor=_StubExecutor(_passing_report()),
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=fake_approval,
        approval_mode="human",
    )

    res = asyncio.run(loop.run())
    assert res.is_passed
    assert len(fake_approval.received_cards) == 1
    card = fake_approval.received_cards[0]
    assert card.unticked_criteria == ("Criterion 2", "Criterion 3")


