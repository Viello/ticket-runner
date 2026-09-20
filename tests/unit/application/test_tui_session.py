"""Unit tests for TUI session pause-and-open protocol, launcher, and warning panel (T059)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import pytest
from rich.console import Console

from runner.adapters.ui.terminal import (
    HOTKEY_LEGENDS,
    RichTerminalDisplay,
    build_warning_panel,
)
from runner.adapters.ui.tui_launcher import (
    ALLOWED_TERMINAL_HOSTS,
    TuiLauncher,
    build_tui_command,
    is_detaching_terminal,
    validate_session_id,
    validate_terminal_host,
)
from runner.application.hotkey_dispatch import HotkeyDispatcher
from runner.application.state_coordinator import StateCoordinator
from runner.application.tui_coordinator import ModalState, TuiCoordinator
from runner.application.worker_supervisor import WorkerSupervisor
from runner.domain.state import RunnerState, StateStatus, TokenState
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_state_store import FakeStateStore
from tests.fakes.fake_terminal_display import FakeTerminalDisplay


def _make_state_coordinator(
    session_id: str = "ses_active123",
    ticket_id: str = "T059",
    status: StateStatus = StateStatus.WORKING,
) -> StateCoordinator:
    initial_state = RunnerState(
        active_ticket_id=ticket_id,
        status=status,
        opencode_session_id=session_id,
        selected_model="anthropic/claude-3-5-sonnet",
        presence_mode="nearby",
        verification_attempts=1,
        tokens=TokenState(current=50000),
        branch="agent/ticket-runner",
        started_at="2026-09-20T00:00:00+00:00",
        last_checkpoint=None,
    )
    store = FakeStateStore(initial_state=initial_state.to_dict())
    return StateCoordinator(state_store=store)


# ---------------------------------------------------------------------------
# 1. Launcher and Security Tests
# ---------------------------------------------------------------------------


def test_build_tui_command_supported_hosts() -> None:
    session_id = "ses_test999"

    # wt.exe: wt.exe cmd.exe /c opencode --session <id>
    cmd_wt = build_tui_command("wt.exe", session_id)
    assert cmd_wt == ["wt.exe", "cmd.exe", "/c", "opencode", "--session", session_id]

    # pwsh.exe: pwsh.exe -NoExit -Command opencode --session <id>
    cmd_pwsh = build_tui_command("pwsh.exe", session_id)
    assert cmd_pwsh == ["pwsh.exe", "-NoExit", "-Command", "opencode", "--session", session_id]

    # powershell.exe: powershell.exe -NoExit -Command opencode --session <id>
    cmd_ps = build_tui_command("powershell.exe", session_id)
    assert cmd_ps == ["powershell.exe", "-NoExit", "-Command", "opencode", "--session", session_id]

    # cmd.exe: cmd.exe /k opencode --session <id>
    cmd_cmd = build_tui_command("cmd.exe", session_id)
    assert cmd_cmd == ["cmd.exe", "/k", "opencode", "--session", session_id]


def test_build_tui_command_case_insensitivity_and_full_paths() -> None:
    session_id = "ses_abc123"
    cmd = build_tui_command(r"C:\Windows\System32\cmd.exe", session_id)
    assert cmd == [r"C:\Windows\System32\cmd.exe", "/k", "opencode", "--session", session_id]

    cmd_upper = build_tui_command("WT.EXE", session_id)
    assert cmd_upper == ["WT.EXE", "cmd.exe", "/c", "opencode", "--session", session_id]


def test_is_detaching_terminal() -> None:
    assert is_detaching_terminal("wt.exe") is True
    assert is_detaching_terminal("WT.EXE") is True
    assert is_detaching_terminal(r"C:\Users\Admin\wt.exe") is True
    assert is_detaching_terminal("pwsh.exe") is False
    assert is_detaching_terminal("powershell.exe") is False
    assert is_detaching_terminal("cmd.exe") is False


@pytest.mark.parametrize(
    "invalid_host",
    [
        "",
        "bash",
        "sh.exe",
        "cmd.exe & calc.exe",
        "wt.exe; rm -rf /",
        "powershell.exe | evil",
        "unsupported_terminal.exe",
    ],
)
def test_validate_terminal_host_rejection(invalid_host: str) -> None:
    with pytest.raises(ValueError):
        validate_terminal_host(invalid_host)


@pytest.mark.parametrize(
    "invalid_session",
    [
        "",
        "ses_test; rm -rf /",
        "ses_test && echo pwned",
        "ses_test|whoami",
        "ses test with spaces",
        'ses"test',
        "ses'test",
        "../ses_traversal",
    ],
)
def test_validate_session_id_security(invalid_session: str) -> None:
    with pytest.raises(ValueError):
        validate_session_id(invalid_session)


# ---------------------------------------------------------------------------
# 2. Warning Panel Verbatim & Styling Tests
# ---------------------------------------------------------------------------


def test_warning_panel_content_verbatim() -> None:
    console = Console(record=True, width=100)
    panel = build_warning_panel()
    console.print(panel)
    output = console.export_text()

    assert "⚠  OpenCode TUI open — Runner is paused & blind" in output
    assert "Execution is paused: no Gatekeeper, no Circuit Breaker, no token tracking." in output
    assert "Tokens consumed in TUI are NOT tracked against the 135k handoff budget." in output
    assert "Work done in TUI bypasses the Gatekeeper and Signal protocol." in output
    assert "Close the terminal window to resume managed execution." in output
    assert "[r] Resume  (required if using Windows Terminal)" in output


def test_terminal_display_shows_warning_panel_and_restores() -> None:
    console = Console(record=True, width=80)
    display = RichTerminalDisplay(console=console)
    state = RunnerState(
        active_ticket_id="T059",
        status=StateStatus.WORKING,
        opencode_session_id="ses_123",
        selected_model="anthropic/claude-3-5-sonnet",
        presence_mode="nearby",
        verification_attempts=1,
        tokens=TokenState(current=10000),
        branch="agent/ticket-runner",
        started_at="2026-09-20T00:00:00+00:00",
        last_checkpoint=None,
    )
    display.update_state(state, queue_remaining=2)

    # Initially normal
    display.render_to_console()
    init_output = console.export_text()
    assert "ticket  T059 · status  WORKING" in init_output

    # Show warning panel
    console.clear()
    console = Console(record=True, width=80)
    display._console = console
    display.show_warning_panel()
    display.render_to_console()
    warn_output = console.export_text()
    assert "⚠  OpenCode TUI open — Runner is paused & blind" in warn_output
    assert "ticket  T059 · status  WORKING" not in warn_output

    # Restore dashboard
    console.clear()
    console = Console(record=True, width=80)
    display._console = console
    display.restore_dashboard()
    display.render_to_console()
    restored_output = console.export_text()
    assert "ticket  T059 · status  WORKING" in restored_output


# ---------------------------------------------------------------------------
# 3. Modal State Machine Tests
# ---------------------------------------------------------------------------


def test_modal_state_machine_open_cancel() -> None:
    display = FakeTerminalDisplay()
    coordinator = TuiCoordinator(terminal_display=display)

    assert coordinator.modal_state == ModalState.NORMAL
    assert not coordinator.is_confirm_pending

    # [o] enters CONFIRM_PENDING
    assert coordinator.handle_key_o() is True
    assert coordinator.modal_state == ModalState.CONFIRM_PENDING
    assert coordinator.is_confirm_pending is True
    assert display.legend_state == "confirm_pending"

    # Repeated [o] in CONFIRM_PENDING is ignored
    assert coordinator.handle_key_o() is False

    # [n] cancels and restores NORMAL
    assert coordinator.handle_key_n() is True
    assert coordinator.modal_state == ModalState.NORMAL
    assert not coordinator.is_confirm_pending
    assert display.legend_state == "normal"


@pytest.mark.anyio
async def test_modal_state_machine_mid_run_queues_intent() -> None:
    display = FakeTerminalDisplay()
    cmd_runner = FakeCommandRunner()
    launcher = TuiLauncher(command_runner=cmd_runner)

    # Mock is_session_active returning True
    coordinator = TuiCoordinator(
        terminal_display=display,
        launcher=launcher,
        is_session_active=lambda: True,
    )

    coordinator.handle_key_o()
    assert coordinator.is_confirm_pending is True

    # [y] when session is active transitions to TUI_QUEUED
    res = await coordinator.handle_key_y()
    assert res is True
    assert coordinator.modal_state == ModalState.TUI_QUEUED
    assert coordinator.is_queued is True
    assert display.legend_state == "tui_queued"

    # No process spawned yet
    assert len(cmd_runner.spawns) == 0


# ---------------------------------------------------------------------------
# 4. TUI Session Launch and Universal [r] Resume Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_tui_launch_persists_state_and_resumes_wt_via_r_key() -> None:
    display = FakeTerminalDisplay()
    cmd_runner = FakeCommandRunner()
    launcher = TuiLauncher(command_runner=cmd_runner)
    state_coord = _make_state_coordinator(session_id="ses_tui_wt")

    resumed_runs: list[dict[str, Any]] = []

    async def mock_resume_worker(ticket: str, prompt: str, session_id: str) -> None:
        resumed_runs.append({"ticket": ticket, "prompt": prompt, "session_id": session_id})

    coordinator = TuiCoordinator(
        terminal_display=display,
        launcher=launcher,
        state_coordinator=state_coord,
        terminal_host="wt.exe",
        run_worker_fn=mock_resume_worker,
    )

    # Launch TUI in background task
    launch_task = asyncio.create_task(coordinator.launch_tui(session_id="ses_tui_wt"))
    await asyncio.sleep(0.01)

    # Verify state was saved with tui_open=True, tui_session_id=ses_tui_wt
    persisted = state_coord.get_or_create_state()
    assert persisted.tui_open is True
    assert persisted.tui_session_id == "ses_tui_wt"

    # Verify display entered warning state and legend is tui_open
    assert display.is_warning_visible is True
    assert display.legend_state == "tui_open"
    assert coordinator.modal_state == ModalState.TUI_OPEN

    # Verify process was spawned with correct wt.exe command
    assert len(cmd_runner.spawns) == 1
    assert cmd_runner.spawns[0] == ["wt.exe", "cmd.exe", "/c", "opencode", "--session", "ses_tui_wt"]

    # Press [r] to resume
    assert coordinator.handle_key_r() is True
    await launch_task

    # Verify state is cleared
    restored_state = state_coord.get_or_create_state()
    assert restored_state.tui_open is False
    assert restored_state.tui_session_id is None

    # Verify display restored
    assert display.is_warning_visible is False
    assert display.legend_state == "normal"
    assert coordinator.modal_state == ModalState.NORMAL

    # Verify resume worker was called with resume banner
    assert len(resumed_runs) == 1
    assert resumed_runs[0]["session_id"] == "ses_tui_wt"
    assert "Resuming after user inspection via TUI." in resumed_runs[0]["prompt"]


@pytest.mark.anyio
async def test_tui_launch_blocking_host_resumes_on_process_exit() -> None:
    from tests.fakes.fake_command_runner import FakeProcessHandle

    class BlockingProcessHandle(FakeProcessHandle):
        async def wait(self) -> int:
            await asyncio.sleep(0.05)
            return await super().wait()

    display = FakeTerminalDisplay()
    blocking_handle = BlockingProcessHandle()
    cmd_runner = FakeCommandRunner(default_spawn_handle=blocking_handle)
    launcher = TuiLauncher(command_runner=cmd_runner)
    state_coord = _make_state_coordinator(session_id="ses_blocking_cmd")

    resumed_runs: list[dict[str, Any]] = []

    async def mock_resume_worker(ticket: str, prompt: str, session_id: str) -> None:
        resumed_runs.append({"ticket": ticket, "prompt": prompt, "session_id": session_id})

    coordinator = TuiCoordinator(
        terminal_display=display,
        launcher=launcher,
        state_coordinator=state_coord,
        terminal_host="cmd.exe",
        run_worker_fn=mock_resume_worker,
    )

    launch_task = asyncio.create_task(coordinator.launch_tui(session_id="ses_blocking_cmd"))
    await asyncio.sleep(0.01)

    assert state_coord.get_or_create_state().tui_open is True
    assert cmd_runner.spawns[0] == ["cmd.exe", "/k", "opencode", "--session", "ses_blocking_cmd"]

    # Now await process exit completion
    await launch_task

    assert state_coord.get_or_create_state().tui_open is False
    assert len(resumed_runs) == 1
    assert "Resuming after user inspection via TUI." in resumed_runs[0]["prompt"]


# ---------------------------------------------------------------------------
# 5. Hotkey Dispatcher Integration Tests
# ---------------------------------------------------------------------------


def test_hotkey_dispatcher_modal_gates_other_keys() -> None:
    display = FakeTerminalDisplay()
    coordinator = TuiCoordinator(terminal_display=display)
    paused = False

    def toggle_pause() -> None:
        nonlocal paused
        paused = not paused

    dispatcher = HotkeyDispatcher(
        terminal_display=display,
        tui_coordinator=coordinator,
    )
    dispatcher.register_handler("p", toggle_pause)

    # 1. Normal state: 'p' toggles pause
    dispatcher.dispatch("p")
    assert paused is True

    # 2. Press 'o': enters confirm-pending
    dispatcher.dispatch("o")
    assert coordinator.is_confirm_pending is True

    # 3. While confirm-pending, 'p' is gated/ignored!
    dispatcher.dispatch("p")
    assert paused is True  # still True, not toggled!

    # 4. Press 'n': cancels modal
    dispatcher.dispatch("n")
    assert coordinator.is_confirm_pending is False

    # 5. 'p' works again
    dispatcher.dispatch("p")
    assert paused is False


@pytest.mark.anyio
async def test_supervisor_signal_boundary_triggers_queued_tui_and_resumes() -> None:
    import json
    from tests.fakes.fake_command_runner import FakeProcessHandle

    display = FakeTerminalDisplay()
    line1 = json.dumps({
        "type": "step_finish",
        "sessionID": "ses_workerqueue",
        "tokens": {"total": 500, "input": 400, "output": 100, "reasoning": 0},
    })
    worker_handle1 = FakeProcessHandle(stdout_lines=[line1, line1], delay=0.05)
    line2 = json.dumps({
        "type": "step_finish",
        "sessionID": "ses_workerqueue",
        "tokens": {"total": 800, "input": 600, "output": 200, "reasoning": 0},
    })
    worker_handle2 = FakeProcessHandle(stdout_lines=[line2])

    cmd_runner = FakeCommandRunner(default_spawn_handle=worker_handle1)
    launcher = TuiLauncher(command_runner=cmd_runner)
    state_coord = _make_state_coordinator(session_id="ses_workerqueue", status=StateStatus.WORKING)

    supervisor = WorkerSupervisor(
        command_runner=cmd_runner,
        state_coordinator=state_coord,
    )

    tui_coordinator = TuiCoordinator(
        terminal_display=display,
        launcher=launcher,
        state_coordinator=state_coord,
        supervisor=supervisor,
        terminal_host="wt.exe",
    )
    supervisor.tui_coordinator = tui_coordinator

    # Start run task in background
    run_task = asyncio.create_task(supervisor.run(ticket="T059", prompt="initial instruction"))
    await asyncio.sleep(0.005)

    # Mid-run: press [o], then [y]
    tui_coordinator.handle_key_o()
    assert tui_coordinator.is_confirm_pending is True
    await tui_coordinator.handle_key_y()
    assert tui_coordinator.is_queued is True
    assert display.legend_state == "tui_queued"

    # Provide second handle for resumed run
    cmd_runner.default_spawn_handle = worker_handle2

    # Give loop time to reach signal boundary and launch TUI
    await asyncio.sleep(0.12)
    assert tui_coordinator.modal_state == ModalState.TUI_OPEN
    assert state_coord.get_or_create_state().tui_open is True

    # Operator presses [r] to resume
    tui_coordinator.handle_key_r()

    # Await final resumed completion
    final_res = await run_task
    assert final_res.session_id == "ses_workerqueue"
    assert state_coord.get_or_create_state().tui_open is False
    assert display.legend_state == "normal"

