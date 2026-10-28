"""Spec 17 Behavioral Test Suite: Human-First Ticket Document Format, Dual-Track Skills, and Human-First Gatekeeper Controls.

Validates Spec 17 end-to-end lifecycle requirements:
  - Seam 1: Canonical Specimen A (to-ticket-runner) document parsing, mode default ("AFK"),
            strict enum status, inline security rationale, jump-start extraction, and checkbox criteria.
  - Seam 2: Specimen B (to-tickets) Human+AI dialect rejection diagnostic directing to /implement or /to-ticket-runner.
  - Seam 3: Pre-Dispatch HITL gate halting before worker dispatch, transitioning to WAITING_FOR_USER,
            and supporting guidance injection, skip finalization with status note, and operator abort.
  - Seam 4: Dispatch-baseline checkbox tick acceptance (- [ ] -> - [x]) vs unauthorized ticket edit rejection,
            consuming a verification attempt and restoring disk baseline.
  - Seam 5: EvidenceCard surfacing unticked acceptance criteria for operator oversight.
  - Seam 6: In-place bold-label header finalization, timestamp recording, body byte preservation, and archive relocation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.markdown.parser import TicketMarkdownParser
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.gatekeeper import (
    CommandOutcome,
    GatekeeperCommandExecutor,
    GatekeeperVerificationLoop as VerificationLoop,
    VerificationReport,
)
from runner.application.ticket_processor import TicketProcessor
from runner.domain.evidence import ApprovalDecision
from runner.domain.exceptions import TicketFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from runner.application.handoff_coordinator import SingleCycleStatus, WorkerRunResult
from runner.ports.intervention import (
    InterventionAction,
    InterventionDecision,
)
from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from tests.fakes.fake_approval_gateway import FakeApprovalGateway
from tests.fakes.fake_intervention import FakeInterventionGateway
from tests.fakes.fake_signal_repository import FakeSignalRepository
from tests.fakes.fake_status_publisher import FakeStatusPublisher


class _StubCycleRunner:
    def __init__(
        self,
        results: list[WorkerRunResult],
        on_call: Any = None,
    ) -> None:
        self._results = list(results)
        self.calls: list[dict[str, Any]] = []
        self._on_call = on_call

    async def __call__(self, ticket: Ticket, **kwargs: Any) -> WorkerRunResult:
        self.calls.append({"ticket": ticket, "kwargs": kwargs})
        if self._on_call:
            self._on_call(ticket, len(self.calls))
        if self._results:
            return self._results.pop(0)
        return WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_default")


class _StubExecutor(GatekeeperCommandExecutor):
    def __init__(self, reports: list[VerificationReport]) -> None:
        super().__init__()
        self._reports = list(reports)
        self.calls: list[Any] = []

    async def verify(self, config: Any) -> VerificationReport:
        self.calls.append(config)
        if self._reports:
            return self._reports.pop(0)
        return _passing_report()


def _passing_report() -> VerificationReport:
    return VerificationReport(
        passed=True,
        diagnostics=(),
        results=(
            CommandOutcome(
                label="test",
                command="pytest",
                exit_code=0,
                timed_out=False,
                tail="All tests passed",
            ),
        ),
        skipped_commands=(),
    )


def _make_ready_signal(ticket_id: str) -> ReadySignal:
    return ReadySignal(
        ticket_id=ticket_id,
        status=SignalStatus.READY_FOR_VERIFICATION,
        modified_files=("sample.py",),
        self_review_notes="Ready for verification",
        new_gotchas=(),
        timestamp=datetime.now(timezone.utc),
        scope="test-spec",
    )


class _StubSignalRepo(FakeSignalRepository):
    def __init__(self, sig: ReadySignal) -> None:
        super().__init__()
        self.seed_ready(sig)

    def consume_ready(self, ticket_id: str) -> None:
        pass


# ==============================================================================
# Seam 1: Canonical Specimen A Document Parsing & Domain Representation
# ==============================================================================


def test_specimen_a_canonical_parsing_and_attributes(tmp_path: Path) -> None:
    ticket_text = (
        "# T129 — Queue Migrations and Living Docs Alignment\n"
        "**Mode:** AFK\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-human-first-ticket-document-format.md\n"
        "**Blocked by:** T127, T128\n"
        "**Security:** required (subprocess shell quoting)\n"
        "**Reasoning:** high\n\n"
        "## What to build\n\n"
        "Complete the Spec 17 end-to-end verification and synchronize queues.\n\n"
        "## Jump-start\n\n"
        "- **Files/areas to touch:**\n"
        "  - `tests/specs/test_spec_17_human_first_ticket_format.py`\n"
        "- **Seams:** Spec 17 verification suite\n"
        "- **Existing-code anchors:** `test_spec_16_live_run_remediation.py`\n"
        "- **Verification commands:** `pytest`\n"
        "- Orientation begins here.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Criterion one\n"
        "- [x] Criterion two\n\n"
        "## Smoke scenarios\n\n"
        "- [ ] Scenario: Full suite pass\n"
        "  - Setup: Repo configured\n"
        "  - Why: Asserts clean execution\n"
        "  - Steps:\n"
        "    1. Run tests\n"
        "  - Expected: Zero failures\n\n"
        "## Gotchas\n\n"
        "- Avoid unix pipelines on Windows.\n"
    )

    ticket_file = tmp_path / "T129-test.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")

    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)

    assert ticket.id == "T129"
    assert ticket.title == "Queue Migrations and Living Docs Alignment"
    assert ticket.mode == "AFK"
    assert ticket.status == TicketStatus.PENDING
    assert ticket.spec_path == "docs/specs/17-human-first-ticket-document-format.md"
    assert ticket.security_required is True
    assert ticket.reasoning == "high"
    assert "Complete the Spec 17 end-to-end" in ticket.requirements[0]
    assert len(ticket.jump_start) >= 4
    assert ticket.acceptance_criteria == ("Criterion one", "Criterion two")
    assert ticket.checked_criteria == frozenset({"Criterion two"})
    assert ticket.gotchas == ("Avoid unix pipelines on Windows.",)


def test_specimen_a_mode_defaults_to_afk_when_omitted(tmp_path: Path) -> None:
    ticket_text = (
        "# T130 — Omitted Mode Ticket\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-human-first-ticket-document-format.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Feature description.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Criterion 1\n"
    )
    ticket_file = tmp_path / "T130-omitted-mode.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")

    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)
    assert ticket.mode == "AFK"


# ==============================================================================
# Seam 2: Specimen B Dialect Rejection Diagnostic
# ==============================================================================


def test_specimen_b_dialect_rejection_diagnostic(tmp_path: Path) -> None:
    specimen_b_text = (
        "# T011: Write docs/agents/live-test-sites.md\n\n"
        "**Status:** ready-for-agent\n"
        "**Labels:** ready-for-agent, security\n"
        "**Security:** required\n"
        "**Parent:** docs/specs/15-multi-agent-hardening-and-live-test-site.md\n\n"
        "**What to build:** Document the four live-test sites.\n\n"
        "**Jump-start:** (orientation starts here)\n"
        "- **Files/areas to touch:** `docs/agents/live-test-sites.md`\n"
        "- **Verify:** `pytest`\n\n"
        "**Blocked by:** T006, T008\n\n"
        "- [ ] Acceptance criterion 1\n"
    )
    ticket_file = tmp_path / "T011-specimen-b.md"
    ticket_file.write_text(specimen_b_text, encoding="utf-8")

    parser = TicketMarkdownParser()
    with pytest.raises(TicketFormatError) as exc_info:
        parser.parse(ticket_file)

    err = str(exc_info.value)
    assert "to-tickets (Human+AI) format" in err or "interactive" in err.lower()
    assert "/implement" in err
    assert "/to-ticket-runner" in err


# ==============================================================================
# Seam 3: Pre-Dispatch HITL Gate Lifecycle (Guidance, Skip, Abort)
# ==============================================================================


def test_pre_dispatch_hitl_gate_guidance_injection(tmp_path: Path) -> None:
    ticket_text = (
        "# T200 — Human-in-the-loop Ticket\n"
        "**Mode:** HITL\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-spec.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Needs human architectural choice.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Decision implemented\n"
    )
    ticket_file = tmp_path / "T200-hitl.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)

    paths = RuntimePaths(root_dir=tmp_path / ".agent")
    paths.ensure_signals_dir()
    signals = FilesystemSignalRepository(paths)
    ready_signal_file = paths.ready_signal_path(ticket.id)

    def _on_worker_call(t: Ticket, count: int) -> None:
        ready_signal_file.write_text(
            json.dumps({
                "ticket_id": t.id,
                "status": "ready_for_verification",
                "modified_files": ["arch.py"],
                "self_review_notes": "Implemented with human guidance",
                "new_gotchas": [],
                "timestamp": "2026-10-28T00:00:00+00:00",
            }),
            encoding="utf-8",
        )

    cycle_runner = _StubCycleRunner(
        [WorkerRunResult(status=SingleCycleStatus.READY, session_id="ses_hitl")],
        on_call=_on_worker_call,
    )
    executor = _StubExecutor([_passing_report()])

    # Gateway provides guidance
    gateway = FakeInterventionGateway(
        hitl_decisions=[
            InterventionDecision(
                action=InterventionAction.PROCEED,
                hint="Use adapter pattern rather than direct library call",
            )
        ]
    )
    publisher = FakeStatusPublisher()

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,
        intervention_gateway=gateway,
        status_publisher=publisher,
        runtime_paths=paths,
    )

    outcome = asyncio.run(processor(ticket))
    assert outcome.is_approved is True
    assert len(gateway.hitl_records) == 1
    assert len(cycle_runner.calls) == 1
    prompt_used = cycle_runner.calls[0]["kwargs"].get("prompt", "")
    assert "Use adapter pattern rather than direct library call" in prompt_used


def test_pre_dispatch_hitl_gate_skip_ticket(tmp_path: Path) -> None:
    ticket_text = (
        "# T201 — Human Skip Ticket\n"
        "**Mode:** HITL\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-spec.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Will be skipped by human.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Never run\n"
    )
    ticket_file = tmp_path / "T201-skip.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)

    paths = RuntimePaths(root_dir=tmp_path / ".agent")
    signals = FilesystemSignalRepository(paths)
    cycle_runner = _StubCycleRunner([])
    executor = _StubExecutor([])
    gateway = FakeInterventionGateway(
        hitl_decisions=[InterventionDecision(action=InterventionAction.SKIP)]
    )

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,
        intervention_gateway=gateway,
        runtime_paths=paths,
    )

    outcome = asyncio.run(processor(ticket))
    assert outcome.is_skipped is True
    assert outcome.status_note == "Skipped by operator at HITL pre-dispatch gate"
    assert len(cycle_runner.calls) == 0


def test_pre_dispatch_hitl_gate_abort_run(tmp_path: Path) -> None:
    ticket_text = (
        "# T202 — Human Abort Ticket\n"
        "**Mode:** HITL\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-spec.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Will be aborted by human.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Abort\n"
    )
    ticket_file = tmp_path / "T202-abort.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)

    paths = RuntimePaths(root_dir=tmp_path / ".agent")
    signals = FilesystemSignalRepository(paths)
    cycle_runner = _StubCycleRunner([])
    executor = _StubExecutor([])
    gateway = FakeInterventionGateway(
        hitl_decisions=[InterventionDecision(action=InterventionAction.ABORT)]
    )

    processor = TicketProcessor(
        cycle_runner=cycle_runner,
        signal_repository=signals,
        executor=executor,
        intervention_gateway=gateway,
        runtime_paths=paths,
    )

    outcome = asyncio.run(processor(ticket))
    assert outcome.is_aborted is True
    assert len(cycle_runner.calls) == 0


# ==============================================================================
# Seam 4: Dispatch Baseline Checkbox Acceptance vs Unauthorized Mutation Rejection
# ==============================================================================


def test_dispatch_baseline_checkbox_tick_acceptance(tmp_path: Path) -> None:
    ticket_text = (
        "# T203 — Baseline Ticket\n"
        "**Mode:** AFK\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-spec.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Acceptance test.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Criterion 1\n"
        "- [ ] Criterion 2\n\n"
        "## Gotchas\n\n"
        "- None\n"
    )
    ticket_file = tmp_path / "T203-baseline.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)
    ready = _make_ready_signal(ticket.id)

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        # Worker legitimately ticks Criterion 1
        content = ticket_file.read_text(encoding="utf-8")
        updated = content.replace("- [ ] Criterion 1", "- [x] Criterion 1")
        ticket_file.write_text(updated, encoding="utf-8")
        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_baseline",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    sig_repo = _StubSignalRepo(ready)

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=sig_repo,
        executor=_StubExecutor([_passing_report()]),
        intervention_gateway=FakeInterventionGateway(),
    )

    res = asyncio.run(loop.run())
    assert res.is_passed is True
    assert res.attempts == 1
    assert "- [x] Criterion 1" in ticket_file.read_text(encoding="utf-8")


def test_dispatch_baseline_unauthorized_edit_rejection_and_attempt_consumption(tmp_path: Path) -> None:
    ticket_text = (
        "# T204 — Baseline Mutation Ticket\n"
        "**Mode:** AFK\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-spec.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Original requirement.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Criterion 1\n\n"
        "## Gotchas\n\n"
        "- None\n"
    )
    ticket_file = tmp_path / "T204-mutation.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)
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
            # Unauthorized mutation: Worker edits ## What to build
            content = ticket_file.read_text(encoding="utf-8")
            hacked = content.replace("Original requirement.", "Malicious requirement rewrite.")
            ticket_file.write_text(hacked, encoding="utf-8")
        else:
            # Compliant edit on attempt 2: only flip checkbox
            content = ticket_file.read_text(encoding="utf-8")
            valid = content.replace("- [ ] Criterion 1", "- [x] Criterion 1")
            ticket_file.write_text(valid, encoding="utf-8")

        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_mutation",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    sig_repo = _StubSignalRepo(ready)

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=sig_repo,
        executor=_StubExecutor([_passing_report()]),
        intervention_gateway=FakeInterventionGateway(),
    )

    res = asyncio.run(loop.run())
    assert res.is_passed is True
    # Attempt 1 was consumed by unauthorized edit rejection, attempt 2 succeeded
    assert res.attempts == 2
    assert cycle_count == 2
    assert len(received_prompts) == 1
    assert "outside '## Acceptance criteria'" in received_prompts[0]
    # And baseline was restored so "Malicious" was eradicated
    assert "Malicious" not in ticket_file.read_text(encoding="utf-8")


# ==============================================================================
# Seam 5: EvidenceCard Surfacing Unticked Acceptance Criteria
# ==============================================================================


def test_evidence_card_surfaces_unticked_criteria(tmp_path: Path) -> None:
    ticket_text = (
        "# T205 — Unticked Criteria Ticket\n"
        "**Mode:** AFK\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-spec.md\n"
        "**Blocked by:** none\n\n"
        "## What to build\n\n"
        "Feature description.\n\n"
        "## Acceptance criteria\n\n"
        "- [ ] Completed criterion\n"
        "- [ ] Outstanding criterion A\n"
        "- [ ] Outstanding criterion B\n"
    )
    ticket_file = tmp_path / "T205-unticked.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_file)
    ready = _make_ready_signal(ticket.id)

    async def _worker_cycle(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        # Worker only ticks the first criterion
        content = ticket_file.read_text(encoding="utf-8")
        updated = content.replace("- [ ] Completed criterion", "- [x] Completed criterion")
        ticket_file.write_text(updated, encoding="utf-8")
        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            occupancy=500,
            session_id="ses_unticked",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    sig_repo = _StubSignalRepo(ready)

    fake_approval = FakeApprovalGateway(decisions=[ApprovalDecision.APPROVE])

    loop = VerificationLoop(
        ticket=ticket,
        cycle_runner=_worker_cycle,
        signal_repository=sig_repo,
        executor=_StubExecutor([_passing_report()]),
        intervention_gateway=FakeInterventionGateway(),
        approval_gateway=fake_approval,
        approval_mode="human",
    )

    res = asyncio.run(loop.run())
    assert res.is_passed is True
    assert len(fake_approval.received_cards) == 1
    evidence_card = fake_approval.received_cards[0]
    assert evidence_card.unticked_criteria == (
        "Outstanding criterion A",
        "Outstanding criterion B",
    )


# ==============================================================================
# Seam 6: In-Place Header Finalization, Preservation & Archive Relocation
# ==============================================================================


def test_inplace_header_finalization_and_archive_relocation(tmp_path: Path) -> None:
    queue_dir = tmp_path / "docs" / "tickets" / "17-human-first-ticket-document-format"
    queue_dir.mkdir(parents=True, exist_ok=True)
    completed_dir = queue_dir / "completed"

    ticket_text = (
        "# T206 — Finalize Ticket\n"
        "**Mode:** AFK\n"
        "**Status:** pending\n"
        "**Spec:** docs/specs/17-human-first-ticket-document-format.md\n"
        "**Blocked by:** none\n"
        "**Security:** optional\n"
        "**Reasoning:** low\n\n"
        "## What to build\n\n"
        "Finalize this ticket cleanly.\n\n"
        "## Jump-start\n\n"
        "- **Files/areas to touch:** `store.py`\n\n"
        "## Acceptance criteria\n\n"
        "- [x] Ticked criterion\n"
        "- [ ] Unticked criterion\n\n"
        "## Gotchas\n\n"
        "- None.\n"
    )
    ticket_file = queue_dir / "T206-finalize-ticket.md"
    ticket_file.write_text(ticket_text, encoding="utf-8")

    store = DirectoryTicketStore(root_dir=tmp_path / "docs" / "tickets")
    ticket = store.select_next_pending()
    assert ticket is not None
    assert ticket.id == "T206"

    fixed_timestamp = "2026-10-28T16:00:00+00:00"
    completed_path = store.finalize_completed(
        ticket,
        completed_at=fixed_timestamp,
        status_note="reviewed; All checks passed",
    )

    # Ticket is relocated to completed/
    assert completed_path == completed_dir / "T206-finalize-ticket.md"
    assert completed_path.is_file()
    assert not ticket_file.exists()

    content = completed_path.read_text(encoding="utf-8")

    # Header is updated in-place with strict fields in canonical order
    assert "**Mode:** AFK\n" in content
    assert "**Status:** completed\n" in content
    assert "**Completed:** 2026-10-28T16:00:00Z\n" in content
    assert "**Status note:** reviewed; All checks passed\n" in content
    assert "**Spec:** docs/specs/17-human-first-ticket-document-format.md\n" in content
    assert "**Blocked by:** none\n" in content
    assert "**Security:** optional\n" in content
    assert "**Reasoning:** low\n" in content

    # Checkboxes, Jump-start, and Gotchas are preserved untouched
    assert "- [x] Ticked criterion\n" in content
    assert "- [ ] Unticked criterion\n" in content
    assert "Finalize this ticket cleanly." in content
    assert "- **Files/areas to touch:** `store.py`\n" in content
    assert "- None.\n" in content
