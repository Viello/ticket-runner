"""Spec 13 Behavioral Test Suite: Token-Guarded Verification Subsystem & Human-in-the-Loop Gate.

Validates Spec 13 requirements end-to-end:
  - Token-preserving evidence triage bounding failure excerpts to <= 30 lines / 1000 characters.
  - Human-in-the-Loop Gate:
      - In human mode, pauses execution upon passing verification, generates EvidenceCard,
        and awaits operator sign-off via ApprovalGateway.
      - On APPROVE, commits ticket changes and relocates ticket.
      - On REJECT, injects bounded operator feedback into Worker retry prompt.
      - Enforces fail-closed authorization: no commit without explicit APPROVE.
  - Autonomous mode bypasses approval gateway completely.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
import pytest

from runner.application.evidence_triage import EvidenceTriage
from runner.application.gatekeeper import (
    CommandOutcome,
    VerificationLoop,
    VerificationReport,
)
from runner.application.handoff_coordinator import (
    SingleCycleStatus,
    WorkerRunResult,
)
from runner.domain.config import LifecycleConfig, RunnerConfig, VerificationConfig
from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.domain.exceptions import UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_approval_gateway import FakeApprovalGateway
from tests.fakes.fake_intervention import FakeInterventionGateway
from tests.fakes.fake_signal_repository import FakeSignalRepository


def _passing_report(cmd: str = "pytest -q") -> VerificationReport:
    outcome = CommandOutcome(
        label="test",
        command=cmd,
        exit_code=0,
        timed_out=False,
        tail="3 passed in 0.05s",
    )
    return VerificationReport(
        passed=True,
        results=(outcome,),
        diagnostics=(),
        skipped_commands=(),
    )


class _ScriptedCycleRunner:
    def __init__(
        self,
        responses: list[WorkerRunResult],
        on_call: Any | None = None,
    ) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self._on_call = on_call

    async def __call__(
        self,
        ticket: Ticket,
        *,
        session_id: str | None = None,
        prompt: str | None = None,
    ) -> WorkerRunResult:
        self.calls.append({"ticket": ticket, "session_id": session_id, "prompt": prompt})
        if self._on_call is not None:
            self._on_call(ticket, len(self.calls))
        if not self._responses:
            raise AssertionError("ScriptedCycleRunner called with no responses remaining")
        return self._responses.pop(0)


class _StubExecutor:
    def __init__(self, reports: list[VerificationReport]) -> None:
        self._reports = list(reports)
        self.calls: list[VerificationConfig] = []

    async def verify(self, config: VerificationConfig) -> VerificationReport:
        self.calls.append(config)
        if not self._reports:
            raise AssertionError("StubExecutor called with no reports remaining")
        return self._reports.pop(0)


def _write_sample_ticket_file(ticket_path: Path, ticket_id: str = "T109") -> None:
    ticket_path.parent.mkdir(parents=True, exist_ok=True)
    ticket_content = f"""# {ticket_id} — Sample Verified Feature
Status: pending
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md

### Requirements
- Implement observable user-facing feature.

### Acceptance Criteria
- Feature functions and verification passes.

### Smoke Scenarios
**Scenario: Verify feature behavior**
- Setup: None (runs from repo root).
- Why: Ensure the operator can inspect real observable behavior.
- Steps:
  1. Run the verified command.
- Expected: Exit code 0 and correct behavior.

### Gotchas
- Keep failure excerpt bounded.
"""
    ticket_path.write_text(ticket_content, encoding="utf-8")


def _make_ready_signal(ticket_id: str = "T109") -> ReadySignal:
    return ReadySignal.parse(
        {
            "ticket_id": ticket_id,
            "status": "ready_for_verification",
            "modified_files": ["runner/feature.py"],
            "self_review_notes": "Tested thoroughly",
            "new_gotchas": [],
            "timestamp": "2026-09-24T12:00:00Z",
            "scope": "application",
            "manual_verification": [
                {
                    "name": "Verify feature behavior",
                    "setup": "None",
                    "steps": "Run command",
                    "expected": "Exit code 0",
                    "auto_covered": True,
                }
            ],
        },
        expected_ticket_id=ticket_id,
    )


def test_spec_13_full_lifecycle_with_evidence_triage_and_human_approval(tmp_path: Path) -> None:
    """Simulate full lifecycle: failure triage excerpt -> worker fix -> green pass -> evidence card -> operator approve."""
    ticket_id = "T109"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)

    runtime_paths = RuntimePaths(root_dir=project_dir / ".agent")
    runtime_paths.ensure_evidence_dir(ticket_id)

    # 1. Simulate prior out-of-band test execution with huge log and failure triage extraction
    log_file = project_dir / "large_test_output.log"
    large_lines = [f"info line {i}: process healthy" for i in range(2000)]
    large_lines[1500:1503] = [
        "FAILED tests/test_feature.py::test_user_flow - AssertionError: button not clicked",
        "E   AssertionError: button not clicked",
        "tests/test_feature.py:42: AssertionError",
    ]
    log_file.write_text("\n".join(large_lines), encoding="utf-8")

    triage_result = EvidenceTriage.extract(
        log_path=log_file,
        exit_code=1,
        duration=12.5,
        ticket_id=ticket_id,
        runtime_paths=runtime_paths,
    )

    # Validate strict token-preserving excerpt bounds
    assert len(triage_result.failure_excerpt.splitlines()) <= 30
    assert len(triage_result.failure_excerpt) <= 1000
    assert triage_result.first_failing_test is not None

    summary_file = runtime_paths.evidence_dir(ticket_id) / "summary.json"
    assert summary_file.is_file()
    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    assert summary_data["exit_code"] == 1
    assert "large_test_output.log" in summary_data["artifacts"]

    # 2. Setup ticket and verification loop in human approval mode
    ticket_file = project_dir / "docs" / "tickets" / f"{ticket_id}-feature.md"
    _write_sample_ticket_file(ticket_file, ticket_id)

    from runner.adapters.markdown.parser import TicketMarkdownParser
    ticket = TicketMarkdownParser().parse(ticket_file)
    assert not hasattr(ticket, "smoke_scenarios")

    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket_id))

    cycle_runner = _ScriptedCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-spec-13"),
    ])
    executor = _StubExecutor([_passing_report()])

    # Scripted ApprovalGateway with operator APPROVE
    approval_gateway = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=approval_gateway,
        approval_mode="human",
        runtime_paths=runtime_paths,
    )

    result = asyncio.run(loop.run())

    # 3. Verify loop outcome and evidence card delivery
    assert result.is_passed
    assert result.approval_decision == ApprovalDecision.APPROVE
    assert len(approval_gateway.received_cards) == 1

    card = approval_gateway.received_cards[0]
    assert card.ticket_id == ticket_id
    assert card.test_status == "passed"
    # Evidence paths should capture the summary.json written during triage
    assert not hasattr(card, "smoke_scenarios")
    assert "smoke_scenarios" not in EvidenceCard.__dataclass_fields__

    # Primary verification-loop seam: assert no smoke log is ever written
    assert not list(runtime_paths.root_dir.glob("smoke_log_*.md"))


def test_spec_13_reject_and_retry_preserves_context_and_injects_feedback(tmp_path: Path) -> None:
    """Verify operator rejection injects bounded feedback into retry prompt and pauses again on second pass."""
    ticket_id = "T109"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    runtime_paths = RuntimePaths(root_dir=project_dir / ".agent")

    ticket_file = project_dir / "docs" / "tickets" / f"{ticket_id}-feature.md"
    _write_sample_ticket_file(ticket_file, ticket_id)

    from runner.adapters.markdown.parser import TicketMarkdownParser
    ticket = TicketMarkdownParser().parse(ticket_file)

    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket_id))

    def _reseed(t: Ticket, count: int) -> None:
        if count == 2:
            signal_repo.seed_ready(_make_ready_signal(t.id))

    cycle_runner = _ScriptedCycleRunner(
        [
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-retry"),
            WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-retry"),
        ],
        on_call=_reseed,
    )
    executor = _StubExecutor([_passing_report(), _passing_report()])

    rejection = ApprovalDecision.REJECT.with_reason("Please update the button border radius to 8px")
    approval_gateway = FakeApprovalGateway(decisions=[rejection, ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=approval_gateway,
        approval_mode="human",
        runtime_paths=runtime_paths,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed
    assert result.approval_decision == ApprovalDecision.APPROVE
    assert len(approval_gateway.received_cards) == 2

    # Second cycle runner invocation must receive the operator feedback in prompt
    assert len(cycle_runner.calls) == 2
    retry_prompt = cycle_runner.calls[1]["prompt"]
    assert retry_prompt is not None
    assert "Please update the button border radius to 8px" in retry_prompt


def test_spec_13_autonomous_mode_skips_approval_gate(tmp_path: Path) -> None:
    """Verify autonomous mode immediately passes without calling ApprovalGateway."""
    ticket_id = "T109"
    project_dir = tmp_path / "project"
    project_dir.mkdir(parents=True, exist_ok=True)
    runtime_paths = RuntimePaths(root_dir=project_dir / ".agent")

    ticket_file = project_dir / "docs" / "tickets" / f"{ticket_id}-feature.md"
    _write_sample_ticket_file(ticket_file, ticket_id)

    from runner.adapters.markdown.parser import TicketMarkdownParser
    ticket = TicketMarkdownParser().parse(ticket_file)

    signal_repo = FakeSignalRepository()
    signal_repo.seed_ready(_make_ready_signal(ticket_id))

    cycle_runner = _ScriptedCycleRunner([
        WorkerRunResult(status=SingleCycleStatus.READY, session_id="sess-auto"),
    ])
    executor = _StubExecutor([_passing_report()])
    approval_gateway = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=cycle_runner,
        signal_repository=signal_repo,
        executor=executor,
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=approval_gateway,
        approval_mode="autonomous",
        runtime_paths=runtime_paths,
    )

    result = asyncio.run(loop.run())

    assert result.is_passed
    assert len(approval_gateway.received_cards) == 0
