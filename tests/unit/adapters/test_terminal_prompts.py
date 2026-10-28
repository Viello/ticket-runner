"""Unit tests for TerminalHostPrompt UI adapter."""

from __future__ import annotations

import pytest

from pathlib import Path
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.intervention import InterventionAction
from runner.adapters.ui.terminal_prompts import TerminalHostPrompt, TerminalInterventionGateway

CANDIDATES = ("wt.exe", "pwsh.exe", "powershell.exe", "cmd.exe")


def test_render_menu_format() -> None:
    prompt = TerminalHostPrompt()
    menu = prompt.render_menu(CANDIDATES)
    expected = (
        "Select terminal host for interactive sessions:\n"
        "  [1] wt.exe\n"
        "  [2] pwsh.exe\n"
        "  [3] powershell.exe\n"
        "  [4] cmd.exe\n"
        "> _"
    )
    assert menu == expected


def test_select_host_zero_hosts_returns_none() -> None:
    output_lines: list[str] = []
    read_called = False

    def fake_read_key() -> str:
        nonlocal read_called
        read_called = True
        return "1"

    prompt = TerminalHostPrompt(
        read_key=fake_read_key,
        output_fn=output_lines.append,
        is_interactive=lambda: True,
    )
    assert prompt.select_host(()) is None
    assert output_lines == []
    assert read_called is False


def test_select_host_single_host_auto_selects_silently() -> None:
    output_lines: list[str] = []
    read_called = False

    def fake_read_key() -> str:
        nonlocal read_called
        read_called = True
        return "1"

    prompt = TerminalHostPrompt(
        read_key=fake_read_key,
        output_fn=output_lines.append,
        is_interactive=lambda: True,
    )
    selected = prompt.select_host(["cmd.exe"])
    assert selected == "cmd.exe"
    assert output_lines == []
    assert read_called is False


def test_select_host_non_interactive_auto_selects_highest_priority() -> None:
    output_lines: list[str] = []
    read_called = False

    def fake_read_key() -> str:
        nonlocal read_called
        read_called = True
        return "2"

    prompt = TerminalHostPrompt(
        read_key=fake_read_key,
        output_fn=output_lines.append,
        is_interactive=lambda: False,
    )
    selected = prompt.select_host(["pwsh.exe", "cmd.exe"])
    assert selected == "pwsh.exe"
    assert output_lines == []
    assert read_called is False


def test_select_host_interactive_valid_key_sequence() -> None:
    # Select option 2 ('powershell.exe') and confirm with Enter
    keys = ["2", "\r"]
    key_iter = iter(keys)
    output_lines: list[str] = []

    prompt = TerminalHostPrompt(
        read_key=lambda: next(key_iter),
        output_fn=output_lines.append,
        is_interactive=lambda: True,
    )
    selected = prompt.select_host(["wt.exe", "powershell.exe", "cmd.exe"])

    assert selected == "powershell.exe"
    assert len(output_lines) == 1
    assert "Select terminal host for interactive sessions:" in output_lines[0]
    assert "[2] powershell.exe" in output_lines[0]


def test_select_host_interactive_invalid_keys_loop_until_valid() -> None:
    # 9 (out of range), 'x' (non-digit), '\r' (Enter before selection), '3' (valid), '\n' (confirm)
    keys = ["9", "x", "\r", "3", "\n"]
    key_iter = iter(keys)
    output_lines: list[str] = []

    prompt = TerminalHostPrompt(
        read_key=lambda: next(key_iter),
        output_fn=output_lines.append,
        is_interactive=lambda: True,
    )
    selected = prompt.select_host(["wt.exe", "powershell.exe", "cmd.exe"])

    assert selected == "cmd.exe"


def test_select_host_interactive_eof_falls_back_to_highest_priority() -> None:
    prompt = TerminalHostPrompt(
        read_key=lambda: "",
        output_fn=lambda _: None,
        is_interactive=lambda: True,
    )
    selected = prompt.select_host(["wt.exe", "cmd.exe"])
    assert selected == "wt.exe"


def test_select_host_interactive_os_error_falls_back_to_highest_priority() -> None:
    def raise_os_error() -> str:
        raise OSError("read error")

    prompt = TerminalHostPrompt(
        read_key=raise_os_error,
        output_fn=lambda _: None,
        is_interactive=lambda: True,
    )
    selected = prompt.select_host(["pwsh.exe", "cmd.exe"])
    assert selected == "pwsh.exe"


def test_terminal_intervention_gateway_prompt_escalation_yes() -> None:
    from pathlib import Path
    from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
    from runner.domain.exceptions import NonInteractiveError
    from runner.domain.ticket import Ticket, TicketStatus

    ticket = Ticket(
        id="T066",
        title="Test Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/10.md",
        requirements=(),
        acceptance_criteria=(),
        gotchas=(),
        path=Path("docs/tickets/10/T066.md"),
    )

    # Operator inputs "y"
    gateway = TerminalInterventionGateway(input_fn=lambda prompt: "y")
    assert gateway.prompt_escalation(ticket, "report content") is True

    # Operator hits Enter (empty string)
    gateway_enter = TerminalInterventionGateway(input_fn=lambda prompt: "")
    assert gateway_enter.prompt_escalation(ticket, "report content") is True

    # Operator inputs "n"
    gateway_no = TerminalInterventionGateway(input_fn=lambda prompt: "n")
    assert gateway_no.prompt_escalation(ticket, "report content") is False

    # Non-interactive stdin raises NonInteractiveError
    def raise_eof(p: str) -> str:
        raise EOFError()

    gateway_non_interactive = TerminalInterventionGateway(input_fn=raise_eof)
    with pytest.raises(NonInteractiveError):
        gateway_non_interactive.prompt_escalation(ticket, "report content")



def test_terminal_intervention_gateway_pauses_and_resumes_active_display() -> None:
    from pathlib import Path
    from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
    from runner.domain.ticket import Ticket, TicketStatus

    ticket = Ticket(
        id="T066",
        title="Test Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/10.md",
        requirements=(),
        acceptance_criteria=(),
        gotchas=(),
        path=Path("docs/tickets/10/T066.md"),
    )

    class FakeDisplay:
        def __init__(self, is_active: bool = True) -> None:
            self.is_active = is_active
            self.actions: list[str] = []

        def stop(self) -> None:
            self.actions.append("stop")
            self.is_active = False

        def start(self) -> None:
            self.actions.append("start")
            self.is_active = True

    # 1. Normal prompt with active display
    display = FakeDisplay(is_active=True)
    gateway = TerminalInterventionGateway(
        input_fn=lambda p: "y",
        display=display,
    )
    assert gateway.display is display
    res = gateway.prompt_escalation(ticket, "diagnostic report")
    assert res is True
    assert display.actions == ["stop", "start"]

    # 2. Inactive display: no stop/start calls
    inactive_display = FakeDisplay(is_active=False)
    gateway2 = TerminalInterventionGateway(
        input_fn=lambda p: "n",
        display=inactive_display,
    )
    res2 = gateway2.prompt_escalation(ticket, "diagnostic report")
    assert res2 is False
    assert inactive_display.actions == []

    # 3. Exception in input_fn: display is still restarted in finally
    display_err = FakeDisplay(is_active=True)

    def raise_eof_fn(_: str) -> str:
        raise EOFError()

    gateway3 = TerminalInterventionGateway(
        input_fn=raise_eof_fn,
        display=display_err,
    )
    with pytest.raises(Exception):
        gateway3.prompt_escalation(ticket, "diagnostic report")
    assert display_err.actions == ["stop", "start"]





def _make_hitl_ticket(
    ticket_id: str = "T126",
    title: str = "HITL Pre-Dispatch Gate",
    mode: str = "HITL",
    status: TicketStatus = TicketStatus.PENDING,
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=title,
        status=status,
        spec_path="docs/specs/17.md",
        requirements=(),
        acceptance_criteria=(),
        gotchas=(),
        path=Path(f"docs/tickets/17/{ticket_id}.md"),
        mode=mode,
    )


def test_terminal_intervention_gateway_request_hitl_proceed_with_guidance() -> None:
    ticket = _make_hitl_ticket()
    outputs: list[str] = []
    gateway = TerminalInterventionGateway(
        input_fn=lambda prompt: "p Focus on tests first",
        output_fn=outputs.append,
    )
    decision = gateway.request_hitl_intervention(ticket)
    assert decision.action == InterventionAction.PROCEED
    assert decision.hint == "Focus on tests first"


def test_terminal_intervention_gateway_request_hitl_proceed_no_guidance() -> None:
    ticket = _make_hitl_ticket()
    gateway = TerminalInterventionGateway(input_fn=lambda prompt: "proceed")
    decision = gateway.request_hitl_intervention(ticket)
    assert decision.action == InterventionAction.PROCEED
    assert decision.hint is None


def test_terminal_intervention_gateway_request_hitl_skip() -> None:
    ticket = _make_hitl_ticket()
    gateway = TerminalInterventionGateway(input_fn=lambda prompt: "skip")
    decision = gateway.request_hitl_intervention(ticket)
    assert decision.action == InterventionAction.SKIP


def test_terminal_intervention_gateway_request_hitl_abort() -> None:
    ticket = _make_hitl_ticket()
    for word in ("a", "abort", "cancel"):
        gateway = TerminalInterventionGateway(input_fn=lambda prompt, w=word: w)
        decision = gateway.request_hitl_intervention(ticket)
        assert decision.action == InterventionAction.ABORT


def test_terminal_intervention_gateway_request_hitl_non_interactive_aborts() -> None:
    ticket = _make_hitl_ticket()

    def raise_eof(_: str) -> str:
        raise EOFError()

    gateway = TerminalInterventionGateway(input_fn=raise_eof)
    decision = gateway.request_hitl_intervention(ticket)
    assert decision.action == InterventionAction.ABORT


def test_terminal_intervention_gateway_request_hitl_invalid_input_repompts() -> None:
    ticket = _make_hitl_ticket()
    inputs = iter(["invalid", "wat", "p Use clean architecture"])
    gateway = TerminalInterventionGateway(input_fn=lambda prompt: next(inputs))
    decision = gateway.request_hitl_intervention(ticket)
    assert decision.action == InterventionAction.PROCEED
    assert decision.hint == "Use clean architecture"
