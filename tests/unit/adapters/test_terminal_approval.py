"""Unit tests for TerminalApprovalAdapter UI adapter (T110)."""

from __future__ import annotations

import asyncio
import io
from typing import Any
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from runner.adapters.ui.terminal_approval import TerminalApprovalAdapter
from runner.domain.evidence import ApprovalDecision, EvidenceCard
from runner.domain.exceptions import NonInteractiveError
from runner.ports.approval_gateway import ApprovalGateway


class MockStdin:
    """Mock interactive or non-interactive stdin stream for testing terminal input."""

    def __init__(self, content: str = "", isatty: bool = True) -> None:
        self._stream = io.StringIO(content)
        self._isatty = isatty

    def isatty(self) -> bool:
        return self._isatty

    def read(self, n: int = 1) -> str:
        return self._stream.read(n)

    def readline(self) -> str:
        return self._stream.readline()

    def tell(self) -> int:
        return self._stream.tell()

    def seek(self, pos: int, whence: int = 0) -> int:
        return self._stream.seek(pos, whence)


@pytest.fixture
def sample_card() -> EvidenceCard:
    return EvidenceCard(
        ticket_id="T110",
        test_status="passed",
        harness_status="passed",
        evidence_paths=(".agent/evidence/T110/output.log",),
        smoke_scenarios=(
            {"name": "Terminal approve via keystroke", "auto_covered": True},
            {"name": "Terminal reject with reason", "auto_covered": False},
        ),
    )


def test_satisfies_approval_gateway_protocol() -> None:
    adapter = TerminalApprovalAdapter()
    assert isinstance(adapter, ApprovalGateway)


def test_render_card_contents(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    adapter = TerminalApprovalAdapter(console=console)

    panel = adapter.render_card(sample_card)
    console.print(panel)
    rendered = out.getvalue()

    assert "T110" in rendered
    assert "PASSED" in rendered
    assert ".agent/evidence/T110/output.log" in rendered
    assert "Terminal approve via keystroke" in rendered
    assert "Terminal reject with reason" in rendered
    assert "[y]" in rendered
    assert "[n]" in rendered
    assert "[d]" in rendered


def test_render_card_clamps_to_terminal_width(sample_card: EvidenceCard) -> None:
    # Gotcha test: rich panel must not exceed terminal width
    width = 60
    out = io.StringIO()
    console = Console(file=out, width=width, force_terminal=False)
    adapter = TerminalApprovalAdapter(console=console)

    panel = adapter.render_card(sample_card)
    console.print(panel)
    lines = [line for line in out.getvalue().splitlines() if line]
    assert all(len(line) <= width for line in lines)


@pytest.mark.anyio
async def test_request_approval_approve_keystroke(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    mock_stdin = MockStdin(content="y\n", isatty=True)

    adapter = TerminalApprovalAdapter(console=console, stdin=mock_stdin)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.APPROVE
    rendered = out.getvalue()
    assert "T110" in rendered
    assert "PASSED" in rendered


@pytest.mark.anyio
async def test_request_approval_reject_with_reason(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    mock_stdin = MockStdin(content="n\ntests look flaky\n", isatty=True)

    adapter = TerminalApprovalAdapter(console=console, stdin=mock_stdin)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "tests look flaky"


@pytest.mark.anyio
async def test_request_approval_diagnose_keystroke(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    mock_stdin = MockStdin(content="d\n", isatty=True)

    adapter = TerminalApprovalAdapter(console=console, stdin=mock_stdin)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.DIAGNOSE


@pytest.mark.anyio
async def test_request_approval_loops_on_invalid_keys(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    # operator inputs 'x', '?', then 'y'
    mock_stdin = MockStdin(content="x\n?\ny\n", isatty=True)

    adapter = TerminalApprovalAdapter(console=console, stdin=mock_stdin)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.APPROVE


@pytest.mark.anyio
async def test_request_approval_non_interactive_fallback(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    mock_stdin = MockStdin(content="y\n", isatty=False)

    adapter = TerminalApprovalAdapter(console=console, stdin=mock_stdin)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "non-interactive terminal"


@pytest.mark.anyio
async def test_request_approval_non_interactive_error_raised(sample_card: EvidenceCard) -> None:
    def raise_non_interactive() -> str:
        raise NonInteractiveError("No TTY")

    adapter = TerminalApprovalAdapter(read_key=raise_non_interactive, is_interactive=True)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "non-interactive terminal"


@pytest.mark.anyio
async def test_request_approval_injected_callables(sample_card: EvidenceCard) -> None:
    adapter = TerminalApprovalAdapter(
        read_key=lambda: "n",
        input_fn=lambda _: "manual review failed",
        is_interactive=lambda: True,
    )
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "manual review failed"


def test_request_approval_sync_in_sync_context(sample_card: EvidenceCard) -> None:
    adapter = TerminalApprovalAdapter(
        read_key=lambda: "y",
        is_interactive=True,
    )
    decision = adapter.request_approval_sync(sample_card)
    assert decision == ApprovalDecision.APPROVE


@pytest.mark.anyio
async def test_request_approval_sync_inside_running_loop(sample_card: EvidenceCard) -> None:
    # Gotcha test: sync call when loop is already running
    adapter = TerminalApprovalAdapter(
        read_key=lambda: "y",
        is_interactive=True,
    )
    decision = adapter.request_approval_sync(sample_card)
    assert decision == ApprovalDecision.APPROVE


def test_render_card_empty_paths_and_scenarios() -> None:
    card = EvidenceCard(
        ticket_id="T110",
        test_status="failed",
        harness_status="failed",
        evidence_paths=(),
        smoke_scenarios=(),
    )
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    adapter = TerminalApprovalAdapter(console=console)

    panel = adapter.render_card(card)
    console.print(panel)
    rendered = out.getvalue()

    assert ".agent/evidence/T110/" in rendered
    assert "(none)" in rendered
    assert "FAILED" in rendered
    assert "Harness Status:" in rendered


def test_render_card_string_scenarios() -> None:
    card = EvidenceCard(
        ticket_id="T110",
        test_status="passed",
        smoke_scenarios=("Manual Smoke Step 1", "Manual Smoke Step 2"),
    )
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    adapter = TerminalApprovalAdapter(console=console)

    panel = adapter.render_card(card)
    console.print(panel)
    rendered = out.getvalue()

    assert "Manual Smoke Step 1" in rendered
    assert "Manual Smoke Step 2" in rendered


@pytest.mark.anyio
async def test_request_approval_reject_with_empty_reason(sample_card: EvidenceCard) -> None:
    out = io.StringIO()
    console = Console(file=out, width=80, force_terminal=False)
    mock_stdin = MockStdin(content="n\n\n", isatty=True)

    adapter = TerminalApprovalAdapter(console=console, stdin=mock_stdin)
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "rejected by operator"


@pytest.mark.anyio
async def test_request_approval_reason_input_non_interactive_error(sample_card: EvidenceCard) -> None:
    def raise_on_input(prompt: str) -> str:
        raise EOFError()

    adapter = TerminalApprovalAdapter(
        read_key=lambda: "n",
        input_fn=raise_on_input,
        is_interactive=True,
    )
    decision = await adapter.request_approval(sample_card)

    assert decision == ApprovalDecision.REJECT
    assert decision.reason == "non-interactive terminal"


def test_is_interactive_variants() -> None:
    # Callable override
    adapter1 = TerminalApprovalAdapter(is_interactive=lambda: False)
    assert adapter1.is_interactive() is False

    # Boolean override
    adapter2 = TerminalApprovalAdapter(is_interactive=True)
    assert adapter2.is_interactive() is True

    # Injected read_key implies interactive
    adapter3 = TerminalApprovalAdapter(read_key=lambda: "y")
    assert adapter3.is_interactive() is True

    # Stdin isatty checked
    mock_tty = MockStdin(isatty=True)
    adapter4 = TerminalApprovalAdapter(stdin=mock_tty)
    assert adapter4.is_interactive() is True

    mock_notty = MockStdin(isatty=False)
    adapter5 = TerminalApprovalAdapter(stdin=mock_notty)
    assert adapter5.is_interactive() is False

