"""Unit tests for RichTerminalDisplay adapter (T057)."""

from rich.console import Console
import pytest

from runner.adapters.ui.terminal import (
    RichTerminalDisplay,
    calculate_token_bar,
    HOTKEY_LEGENDS,
)
from runner.domain.state import RunnerState, StateStatus, TokenState
from tests.fakes.fake_terminal_display import FakeTerminalDisplay


def _make_state(
    active_ticket_id: str | None = "T042",
    status: StateStatus = StateStatus.WORKING,
    current_tokens: int = 118_200,
    verification_attempts: int = 2,
    presence_mode: str = "nearby",
    opencode_session_id: str | None = "9f4a2c1e",
    branch: str = "agent/ticket-runner",
) -> RunnerState:
    return RunnerState(
        active_ticket_id=active_ticket_id,
        status=status,
        opencode_session_id=opencode_session_id,
        selected_model="anthropic/claude-3-5-sonnet",
        presence_mode=presence_mode,
        verification_attempts=verification_attempts,
        tokens=TokenState(current=current_tokens),
        branch=branch,
        started_at="2026-09-19T10:00:00+00:00",
        last_checkpoint=None,
    )


def test_calculate_token_bar_zero_tokens() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(0)
    assert pct == 0
    assert bar_plain == "░░░░░░░░░░"
    assert len(bar_plain) == 10


def test_calculate_token_bar_early_session_60k() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(60_000)
    assert pct == 40
    assert bar_plain == "████░░░░░░"
    assert len(bar_plain) == 10
    assert "[green]████[/green]" in bar_markup


def test_calculate_token_bar_normal_running_118k() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(118_200)
    assert pct == 79
    assert bar_plain == "████████░░"
    assert len(bar_plain) == 10
    assert "[green]████████[/green]" in bar_markup
    assert "[yellow]" not in bar_markup
    assert "[red]" not in bar_markup


def test_calculate_token_bar_yellow_warning_threshold_120k() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(120_000)
    assert pct == 80
    assert bar_plain == "█████████░"
    assert len(bar_plain) == 10
    assert "[green]████████[/green]" in bar_markup
    assert "[yellow]█[/yellow]" in bar_markup
    assert "[red]" not in bar_markup


def test_calculate_token_bar_red_handoff_threshold_135k() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(135_000)
    assert pct == 90
    assert bar_plain == "██████████"
    assert len(bar_plain) == 10
    assert "[green]████████[/green]" in bar_markup
    assert "[yellow]█[/yellow]" in bar_markup
    assert "[red]█[/red]" in bar_markup


def test_calculate_token_bar_ceiling_150k() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(150_000)
    assert pct == 100
    assert bar_plain == "██████████"
    assert "[green]████████[/green]" in bar_markup
    assert "[yellow]█[/yellow]" in bar_markup
    assert "[red]█[/red]" in bar_markup


def test_calculate_token_bar_over_ceiling_clamped() -> None:
    bar_markup, bar_plain, pct = calculate_token_bar(200_000)
    assert pct == 100
    assert bar_plain == "██████████"


def test_top_panel_rendering_verbatim_layout() -> None:
    console = Console(record=True, width=80)
    display = RichTerminalDisplay(console=console)
    state = _make_state()

    display.update_state(state, queue_remaining=2)
    display.render_to_console()

    output = console.export_text()
    # Assert each row format matching verbatim spec
    assert "ticket  T042 · status  WORKING · attempt  2 / 3" in output
    assert "tokens  [████████░░] 118,200 / 150,000 (79%)" in output
    assert "presence  nearby · session  9f4a2c1e" in output
    assert "branch  agent/ticket-runner · queue  T042 (2 remaining)" in output
    assert "─" * 20 in output
    assert "[p] pause  [m] toggle mode  [q] quit  [o] open TUI" in output


def test_top_panel_rendering_empty_queue() -> None:
    console = Console(record=True, width=80)
    display = RichTerminalDisplay(console=console)
    state = _make_state(active_ticket_id=None, status=StateStatus.IDLE)

    display.update_state(state, queue_remaining=0)
    display.render_to_console()

    output = console.export_text()
    assert "ticket  none · status  IDLE · attempt  2 / 3" in output
    assert "branch  agent/ticket-runner · queue  empty" in output


def test_bottom_panel_rolling_ring_buffer() -> None:
    console = Console(record=True, width=80)
    display = RichTerminalDisplay(console=console)
    state = _make_state()
    display.update_state(state, queue_remaining=1)

    display.emit("worker", "Tool: Read CONTEXT.md")
    display.emit("gate", "Gatekeeper: running pytest tests/ ...")
    display.emit("runner", "Authoring commit: feat(queue): defer clean-slate prompt")

    display.render_to_console()
    output = console.export_text()

    assert "[worker] Tool: Read CONTEXT.md" in output
    assert "[gate  ] Gatekeeper: running pytest tests/ ..." in output
    assert "[runner] Authoring commit: feat(queue): defer clean-slate prompt" in output


def test_hotkey_legend_states() -> None:
    console = Console(record=True, width=80)
    display = RichTerminalDisplay(console=console)
    state = _make_state()
    display.update_state(state, queue_remaining=1)

    # 1. Normal
    display.set_legend_state("normal")
    display.render_to_console()
    assert "[p] pause  [m] toggle mode  [q] quit  [o] open TUI" in console.export_text()

    # 2. Confirm-pending
    console.clear()
    console = Console(record=True, width=80)
    display._console = console
    display.set_legend_state("confirm_pending")
    display.render_to_console()
    assert "Open TUI? [y] confirm / [n] cancel" in console.export_text()

    # 3. TUI queued
    console = Console(record=True, width=80)
    display._console = console
    display.set_legend_state("tui_queued")
    display.render_to_console()
    assert "[p] pause  [m] toggle mode  [q] quit  [o] pending…" in console.export_text()

    # 4. TUI open
    console = Console(record=True, width=80)
    display._console = console
    display.set_legend_state("tui_open")
    display.render_to_console()
    assert "[r] Resume  (all other keys suspended)" in console.export_text()


def test_display_start_stop_refresh_lifecycle() -> None:
    console = Console(record=True, width=80)
    display = RichTerminalDisplay(console=console)
    state = _make_state()
    display.update_state(state, queue_remaining=1)

    display.start()
    assert display.is_active
    display.refresh()
    display.stop()
    assert not display.is_active


def test_fake_terminal_display_records_snapshots_and_lines() -> None:
    fake = FakeTerminalDisplay()
    state = _make_state()

    assert not fake.is_running
    fake.start()
    assert fake.is_running
    assert fake.started

    fake.update_state(state, queue_remaining=3)
    assert len(fake.snapshots) == 1
    assert fake.current_state == state
    assert fake.queue_remaining == 3

    fake.emit("worker", "Tool: Read CONTEXT.md")
    fake.emit("gate", "Gatekeeper: running pytest tests/ ...")
    fake.emit("runner", "Authoring commit: feat(queue): test")

    assert len(fake.events) == 3
    assert fake.events[0] == ("worker", "Tool: Read CONTEXT.md")
    assert len(fake.lines) == 3
    assert "[worker]" in fake.lines[0]
    assert "[gate  ]" in fake.lines[1]
    assert "[runner]" in fake.lines[2]

    with pytest.raises(ValueError, match="Invalid source 'invalid'"):
        fake.emit("invalid", "Should raise")

    fake.refresh()
    assert fake.refresh_count == 1

    fake.stop()
    assert not fake.is_running
    assert fake.stopped


@pytest.mark.anyio
async def test_worker_supervisor_emits_to_ui_event_sink() -> None:
    import json
    from tests.fakes.fake_command_runner import FakeCommandRunner
    from runner.application.worker_supervisor import WorkerSupervisor

    fake_display = FakeTerminalDisplay()
    cmd_runner = FakeCommandRunner()

    tool_event = json.dumps({
        "type": "tool_call",
        "sessionID": "ses_test123",
        "part": {
            "tool": "read",
            "state": {"input": {"filePath": "CONTEXT.md"}}
        }
    })
    step_finish_event = json.dumps({
        "type": "step_finish",
        "sessionID": "ses_test123",
        "tokens": {"total": 1000, "input": 800, "output": 200, "reasoning": 0}
    })

    cmd_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "test prompt"],
        stdout_lines=[tool_event, step_finish_event],
        exit_code=0,
    )

    supervisor = WorkerSupervisor(
        command_runner=cmd_runner,
        ui_event_sink=fake_display,
    )

    result = await supervisor.run("T001", "test prompt")
    assert len(fake_display.events) >= 1
    source, msg = fake_display.events[0]
    assert source == "worker"
    assert msg == "Tool: Read CONTEXT.md"


@pytest.mark.anyio
async def test_gatekeeper_executor_emits_to_ui_event_sink() -> None:
    from tests.fakes.fake_command_runner import FakeCommandRunner
    from runner.application.gatekeeper import GatekeeperCommandExecutor
    from runner.domain.config import VerificationConfig

    fake_display = FakeTerminalDisplay()
    cmd_runner = FakeCommandRunner()

    cmd_runner.register_spawn(
        ["cmd.exe", "/d", "/s", "/c", "pytest -q"],
        stdout_lines=["1 passed"],
        exit_code=0,
    )

    executor = GatekeeperCommandExecutor(
        command_runner=cmd_runner,
        platform="win32",
        path_resolver=lambda _: "pytest",
        ui_event_sink=fake_display,
    )

    report = await executor.verify(VerificationConfig(build_cmd="", test_cmd="pytest -q"))
    assert report.passed

    # Verify gatekeeper emitted running and passed events
    assert len(fake_display.events) == 2
    assert fake_display.events[0] == ("gate", "Gatekeeper: running pytest -q ...")
    assert fake_display.events[1] == ("gate", "Gatekeeper: pytest -q passed")


@pytest.mark.anyio
async def test_queue_orchestrator_emits_to_ui_event_sink() -> None:
    from pathlib import Path
    from tests.fakes.fake_command_runner import FakeCommandRunner
    from tests.fakes.fake_ticket_repository import FakeTicketRepository
    from runner.application.queue_orchestrator import QueueOrchestrator, TicketOutcome
    from runner.domain.ticket import Ticket, TicketStatus

    fake_display = FakeTerminalDisplay()
    ticket_store = FakeTicketRepository([
        Ticket(
            id="T042",
            title="Add display",
            status=TicketStatus.PENDING,
            spec_path="docs/specs/06-state-persistence-and-terminal-ui.md",
            requirements=(),
            acceptance_criteria=(),
            gotchas=(),
            path=Path("docs/tickets/06-state-persistence-and-terminal-ui/T042-add-display.md"),
        )
    ])

    async def fake_processor(ticket: Ticket) -> TicketOutcome:
        return TicketOutcome.approved(
            new_gotchas=(),
            changes=["Added display"],
            scope="ui",
            commit_prefix="feat",
        )

    class MockGitOps:
        commit_prefix = "feat"
        async def commit_ticket(self, **kwargs: object) -> str:
            return "abc1234"

    git_ops = MockGitOps()

    orchestrator = QueueOrchestrator(
        ticket_store=ticket_store,
        processor=fake_processor,
        git_operations=git_ops,
        ui_event_sink=fake_display,
    )

    outcome = await orchestrator.run_next()
    assert outcome is not None
    assert outcome.is_approved

    # Check emissions from runner
    sources = [src for src, _ in fake_display.events]
    assert all(s == "runner" for s in sources)
    msgs = [msg for _, msg in fake_display.events]
    assert "Starting ticket T042" in msgs
    assert "Authoring commit: feat: Add display" in msgs
    assert "Ticket T042 approved" in msgs

