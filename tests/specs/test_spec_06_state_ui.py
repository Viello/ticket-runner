"""Spec 06 Traceability Test Suite: State Persistence, Crash Recovery, and Terminal UI.

Validates all 19 User Stories from docs/specs/06-state-persistence-and-terminal-ui.md:
  US 01: Persist operational state to .agent/state.json on every state transition
  US 02: Atomic disk writes using temporary file replacements
  US 03: Detect interrupted run on startup, inspect git status, resume session
  US 04: Split live terminal dashboard in nearby mode with pinned top header
  US 05: Scrolling ring buffer showing last 15 lines of Worker/Gatekeeper logs
  US 06: Press [p] to pause execution and release tickets.md file lock
  US 07: Press [m] to toggle between nearby and away mode
  US 08: Press [q] to trigger graceful shutdown and save state
  US 09: Console hotkey polling executes non-blockingly on Windows
  US 10: Configurable queue completion behavior (standby vs terminate)
  US 11: Terminal banner announcing queue completion when all tickets pass
  US 12: Press [o] in terminal to open interactive OpenCode TUI window
  US 13: Two-key confirmation ([o] -> [y] confirm / [n] cancel)
  US 14: Mid-run [o]+[y] queues intent until next signal boundary
  US 15: Rich dashboard freezes and displays warning panel when TUI open
  US 16: Warning panel verbatim content and styling specifications
  US 17: Doctor terminal host detection across candidate binaries
  US 18: Resume banner injection via --auto when resuming after TUI
  US 19: Crash recovery with tui_open logs warning and clears flag
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from typing import Any
import pytest

from rich.console import Console

from runner.adapters.filesystem.json_state_store import JsonStateStore
from runner.adapters.markdown.file_lock import QueueFileLock
from runner.adapters.ui.keyboard import KeyboardPoller
from runner.adapters.ui.terminal import RichTerminalDisplay, build_warning_panel
from runner.adapters.ui.tui_launcher import (
    ALLOWED_TERMINAL_HOSTS,
    TuiLauncher,
    build_tui_command,
    is_detaching_terminal,
    validate_session_id,
    validate_terminal_host,
)
from runner.application.crash_recovery import CrashRecoveryCoordinator
from runner.application.doctor import CHECK_TERMINAL_HOST, Doctor
from runner.application.git_operations import GitOperations
from runner.application.hotkey_dispatch import HotkeyDispatcher
from runner.application.presence_coordinator import PresenceCoordinator
from runner.application.queue_orchestrator import QueueOrchestrator, format_celebration_banner
from runner.application.state_coordinator import StateCoordinator
from runner.application.tui_coordinator import ModalState, RESUME_BANNER, TuiCoordinator
from runner.application.worker_supervisor import (
    RunTerminationReason,
    SessionRunResult,
    WorkerSupervisor,
)
from runner.container import build_container
from runner.domain.config import (
    GitConfig,
    LifecycleConfig,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    UIConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.ring_buffer import RingBuffer
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.state import RunnerState, StateStatus
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle
from tests.fakes.fake_state_store import FakeStateStore
from tests.fakes.fake_terminal_display import FakeTerminalDisplay


def _make_config(session_terminal: str = "wt.exe") -> RunnerConfig:
    return RunnerConfig(
        project=ProjectConfig(name="spec06-test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
        ui=UIConfig(session_terminal=session_terminal),
    )


# ---------------------------------------------------------------------------
# US 01: State Persistence to .agent/state.json
# ---------------------------------------------------------------------------
def test_us01_persist_state_to_json_on_transitions(tmp_path: Path) -> None:
    """US 01: Runner persists state to .agent/state.json on every state transition."""
    state_file = tmp_path / "state.json"
    store = JsonStateStore(path=state_file)
    coordinator = StateCoordinator(state_store=store, branch="agent/ticket-runner")

    coordinator.transition_to_working(ticket_id="T001", session_id="ses_abc123")
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["status"] == "WORKING"
    assert data["active_ticket_id"] == "T001"
    assert data["opencode_session_id"] == "ses_abc123"

    coordinator.transition_to_gatekeeper(verification_attempts=1)
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["status"] == "GATEKEEPER"
    assert data["verification_attempts"] == 1

    coordinator.transition_to_idle()
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["status"] == "IDLE"
    assert data["active_ticket_id"] is None


# ---------------------------------------------------------------------------
# US 02: Atomic State Writes via Temp File
# ---------------------------------------------------------------------------
def test_us02_atomic_state_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """US 02: State updates are written atomically using temporary file replacement."""
    state_file = tmp_path / "state.json"
    store = JsonStateStore(path=state_file)

    replaced_paths: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def tracked_replace(src: Any, dst: Any) -> None:
        replaced_paths.append((Path(src), Path(dst)))
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracked_replace)

    payload = {"status": "WORKING", "active_ticket_id": "T002"}
    store.write(payload)

    assert state_file.exists()
    assert len(replaced_paths) == 1
    src, dst = replaced_paths[0]
    assert src.suffix == ".tmp"
    assert dst == state_file
    assert json.loads(state_file.read_text(encoding="utf-8")) == payload


# ---------------------------------------------------------------------------
# US 03: Crash Recovery Working Tree Inspection and Resumption
# ---------------------------------------------------------------------------
def test_us03_crash_recovery_resumes_interrupted_run(tmp_path: Path) -> None:
    """US 03: Detect interrupted run on startup, inspect git status, resume session."""
    async def _run() -> None:
        state_file = tmp_path / "state.json"
        store = JsonStateStore(path=state_file)
        initial = (
            RunnerState.idle(
                branch="agent/ticket-runner",
                selected_model="test-provider/test-model",
                presence_mode="nearby",
            ).to_working(ticket_id="T003", session_id="ses_resume123")
        )
        store.write(initial.to_dict())

        runner = FakeCommandRunner()
        # Stub git status --porcelain
        runner.register_result(
            ["git", "status", "--porcelain"],
            CommandResult(exit_code=0, stdout=" M runner/application/worker_supervisor.py\n?? untracked.py\n", stderr=""),
        )
        # Stub opencode run for resumption
        runner.register_result(
            ["opencode", "run", "--format", "json", "--session", "ses_resume123"],
            CommandResult(exit_code=0, stdout=json.dumps({"type": "step_finish", "part": {"tokens": {"total": 50000}}}), stderr=""),
        )

        git_ops = GitOperations(runner=runner, cwd=tmp_path)
        supervisor = WorkerSupervisor(
            command_runner=runner,
            runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
            budget_config=TokenBudgetConfig(),
            cwd=tmp_path,
        )
        state_coord = StateCoordinator(state_store=store, branch="agent/ticket-runner")

        coordinator = CrashRecoveryCoordinator(
            state_store=store,
            git_operations=git_ops,
            worker_supervisor=supervisor,
            state_coordinator=state_coord,
        )

        result = await coordinator.recover()
        assert result.recovered is True
        assert result.ticket_id == "T003"
        assert result.session_id == "ses_resume123"
        assert "runner/application/worker_supervisor.py" in result.uncommitted_files

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# US 04: Split Live Terminal Dashboard Header
# ---------------------------------------------------------------------------
def test_us04_split_terminal_dashboard_header() -> None:
    """US 04: Split terminal dashboard in nearby mode renders 6-row top panel."""
    console = Console(width=80, height=24, record=True)
    display = RichTerminalDisplay(console=console)
    state = (
        RunnerState.idle(branch="agent/ticket-runner", presence_mode="nearby")
        .to_working(ticket_id="T042", session_id="ses_9f4a2c1e", verification_attempts=2)
    )
    state = replace(state, tokens={"current": 118200, "warning_sent": False})
    display.update_state(state, queue_remaining=2)
    display.render_to_console()
    output = console.export_text()

    assert "ticket  T042 · status  WORKING · attempt  2 / 3" in output
    assert "118,200 / 150,000" in output
    assert "presence  nearby · session  ses_9f4a2c1e" in output
    assert "branch  agent/ticket-runner · queue  T042 (2 remaining)" in output
    assert "[p] pause  [m] toggle mode  [q] quit  [o] open TUI" in output


# ---------------------------------------------------------------------------
# US 05: Rolling Ring Buffer (15 entries FIFO)
# ---------------------------------------------------------------------------
def test_us05_scrolling_ring_buffer_fifo() -> None:
    """US 05: Ring buffer keeps maximum 15 entries, evicting oldest on overflow."""
    buffer = RingBuffer(max_entries=15)
    for i in range(20):
        buffer.append("worker", f"Tool invocation #{i}")

    assert len(buffer.entries) == 15
    assert "Tool invocation #5" in buffer.entries[0]
    assert "Tool invocation #19" in buffer.entries[-1]


# ---------------------------------------------------------------------------
# US 06: Hotkey [p] Pauses Execution and Releases File Lock
# ---------------------------------------------------------------------------
def test_us06_hotkey_p_pauses_orchestrator(tmp_path: Path) -> None:
    """US 06: Pressing [p] pauses orchestrator and releases tickets.md file lock."""
    lock_file = tmp_path / "tickets.lock"
    lock = QueueFileLock(lock_path=lock_file)
    lock.acquire()
    assert lock.is_locked

    class DummyOrchestrator:
        def __init__(self, lock: QueueFileLock) -> None:
            self.is_paused = False
            self.lock = lock

        def pause(self) -> None:
            self.is_paused = True
            self.lock.release()

        def resume(self) -> None:
            self.is_paused = False
            self.lock.acquire()

    orch = DummyOrchestrator(lock)
    dispatcher = HotkeyDispatcher(orchestrator=orch)  # type: ignore[arg-type]

    dispatcher.dispatch("p")
    assert orch.is_paused is True
    assert not lock.is_locked

    dispatcher.dispatch("p")
    assert orch.is_paused is False
    assert lock.is_locked
    lock.release()


# ---------------------------------------------------------------------------
# US 07: Hotkey [m] Toggles Presence Mode
# ---------------------------------------------------------------------------
def test_us07_hotkey_m_toggles_presence_mode(tmp_path: Path) -> None:
    """US 07: Pressing [m] toggles presence mode between nearby and away."""
    store = FakeStateStore()
    state_coord = StateCoordinator(state_store=store, branch="main")
    presence = PresenceCoordinator(state_coordinator=state_coord)
    dispatcher = HotkeyDispatcher(presence_coordinator=presence)

    assert presence.current_mode == "nearby"
    dispatcher.dispatch("m")
    assert presence.current_mode == "away"
    dispatcher.dispatch("m")
    assert presence.current_mode == "nearby"


# ---------------------------------------------------------------------------
# US 08: Hotkey [q] Triggers Graceful Shutdown
# ---------------------------------------------------------------------------
def test_us08_hotkey_q_triggers_graceful_shutdown() -> None:
    """US 08: Pressing [q] sets stop event and requests supervisor kill."""
    stop_event = asyncio.Event()

    class DummySupervisor:
        def __init__(self) -> None:
            self.killed = False
            self.reason = None

        def request_kill(self, reason: RunTerminationReason) -> None:
            self.killed = True
            self.reason = reason

    sup = DummySupervisor()
    dispatcher = HotkeyDispatcher(
        supervisor=sup,  # type: ignore[arg-type]
        stop_event=stop_event,
    )

    assert not stop_event.is_set()
    dispatcher.dispatch("q")
    assert stop_event.is_set()
    assert sup.killed is True
    assert sup.reason == RunTerminationReason.KILLED_INTERRUPT


# ---------------------------------------------------------------------------
# US 09: Non-blocking Windows Console Input Polling
# ---------------------------------------------------------------------------
def test_us09_nonblocking_keyboard_poller() -> None:
    """US 09: KeyboardPoller schedules polling non-blockingly on asyncio loop."""
    async def _run() -> None:
        pressed_keys: list[str] = []
        fake_keys = ["p", "m", None]

        def read_key() -> str | None:
            return fake_keys.pop(0) if fake_keys else None

        poller = KeyboardPoller(
            poll_interval=0.01,
            key_reader=read_key,
            on_key=lambda k: pressed_keys.append(k),
        )
        poller.start()
        await asyncio.sleep(0.05)
        await poller.stop()

        assert "p" in pressed_keys
        assert "m" in pressed_keys

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# US 10: Configurable Queue Completion Policies (standby vs terminate)
# ---------------------------------------------------------------------------
def test_us10_queue_completion_policy_options() -> None:
    """US 10: LifecycleConfig accepts standby and terminate completion policies."""
    cfg_terminate = LifecycleConfig(queue_completion="terminate")
    assert cfg_terminate.queue_completion == "terminate"

    cfg_standby = LifecycleConfig(queue_completion="standby")
    assert cfg_standby.queue_completion == "standby"


# ---------------------------------------------------------------------------
# US 11: Terminal Banner Announcing Queue Completion
# ---------------------------------------------------------------------------
def test_us11_completion_banner_rendering() -> None:
    """US 11: format_celebration_banner renders double-bordered completion banner on queue completion."""
    banner = format_celebration_banner(tickets_committed=5, total_tokens=125400)

    assert "Queue complete! All tickets committed." in banner
    assert "5 tickets" in banner
    assert "~125k tokens" in banner
    assert "╔" in banner and "╗" in banner and "╚" in banner and "╝" in banner


# ---------------------------------------------------------------------------
# US 12 & 13: Hotkey [o] Two-Key Confirmation Modal
# ---------------------------------------------------------------------------
def test_us12_us13_two_key_confirmation_modal() -> None:
    """US 12 & 13: Pressing [o] enters confirm-pending; [n] cancels; [y] confirms."""
    async def _run() -> None:
        display = FakeTerminalDisplay()
        launcher = TuiLauncher(command_runner=FakeCommandRunner())
        coordinator = TuiCoordinator(terminal_display=display, launcher=launcher)
        dispatcher = HotkeyDispatcher(tui_coordinator=coordinator)

        assert coordinator.modal_state == ModalState.NORMAL
        assert display.legend_state == "normal"

        # 1. Press [o] -> enters confirm-pending
        dispatcher.dispatch("o")
        assert coordinator.is_confirm_pending is True
        assert display.legend_state == "confirm_pending"

        # 2. Press [n] -> cancels and restores normal
        dispatcher.dispatch("n")
        assert coordinator.modal_state == ModalState.NORMAL
        assert display.legend_state == "normal"

        # 3. Press [o] then unrelated key -> ignored
        dispatcher.dispatch("o")
        assert coordinator.is_confirm_pending is True
        dispatcher.dispatch("p")  # ignored during modal
        assert coordinator.is_confirm_pending is True

        # 4. Press [y] when session active -> transitions to queued
        coordinator._is_session_active = lambda: True
        task = dispatcher.dispatch("y")
        if task:
            await task
        assert coordinator.is_queued is True
        assert display.legend_state == "tui_queued"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# US 14: Mid-run [o]+[y] Queues Intent Until Signal Boundary
# ---------------------------------------------------------------------------
def test_us14_mid_run_queues_intent_until_signal_boundary() -> None:
    """US 14: Mid-run [o]->[y] queues TUI open until next signal boundary."""
    async def _run() -> None:
        display = FakeTerminalDisplay()
        runner = FakeCommandRunner()
        launcher = TuiLauncher(command_runner=runner)

        coordinator = TuiCoordinator(
            terminal_display=display,
            launcher=launcher,
            terminal_host="wt.exe",
            is_session_active=lambda: True,
        )

        coordinator.handle_key_o()
        await coordinator.handle_key_y()
        assert coordinator.is_queued is True
        assert len(runner.spawns) == 0

        # At signal boundary, queued intent fires
        launch_task = asyncio.create_task(coordinator.on_signal_boundary(session_id="ses_boundary_123"))
        await asyncio.sleep(0.01)
        assert coordinator.is_tui_open is True
        assert len(runner.spawns) == 1
        assert runner.spawns[0] == ["wt.exe", "cmd.exe", "/c", "opencode", "--session", "ses_boundary_123"]

        # Clean up by resuming
        coordinator.handle_key_r()
        await launch_task
        assert coordinator.modal_state == ModalState.NORMAL

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# US 15 & 16: Dashboard Warning Panel Rendering & Styling
# ---------------------------------------------------------------------------
def test_us15_us16_dashboard_warning_panel_styling() -> None:
    """US 15 & 16: TUI warning panel renders verbatim text matching exact styling."""
    panel = build_warning_panel()
    console = Console(width=100, height=20, record=True)
    console.print(panel)
    output = console.export_text()

    assert "⚠  OpenCode TUI open — Runner is paused & blind" in output
    assert "Execution is paused: no Gatekeeper, no Circuit Breaker, no token tracking." in output
    assert "Tokens consumed in TUI are NOT tracked against the 135k handoff budget." in output
    assert "Work done in TUI bypasses the Gatekeeper and Signal protocol." in output
    assert "Close the terminal window to resume managed execution." in output
    assert "[r] Resume  (required if using Windows Terminal)" in output


# ---------------------------------------------------------------------------
# US 17: Doctor Terminal Host Detection
# ---------------------------------------------------------------------------
def test_us17_doctor_terminal_host_validation() -> None:
    """US 17: Candidate terminal hosts are strictly validated."""
    for host in ("wt.exe", "pwsh.exe", "powershell.exe", "cmd.exe"):
        assert validate_terminal_host(host) == host

    with pytest.raises(ValueError, match="Unsupported terminal host"):
        validate_terminal_host("bash.exe")

    with pytest.raises(ValueError, match="disallowed shell character"):
        validate_terminal_host("cmd.exe; rm -rf")


# ---------------------------------------------------------------------------
# US 18: Resume Banner Injected After TUI Inspection
# ---------------------------------------------------------------------------
def test_us18_resume_banner_injection() -> None:
    """US 18: Runner injects resume banner when resuming managed execution."""
    async def _run() -> None:
        resumed_calls: list[dict[str, Any]] = []

        async def fake_run_worker(ticket: str, prompt: str, session_id: str | None = None) -> None:
            resumed_calls.append({"ticket": ticket, "prompt": prompt, "session_id": session_id})

        coordinator = TuiCoordinator(
            run_worker_fn=fake_run_worker,
        )
        coordinator._modal_state = ModalState.TUI_OPEN

        await coordinator.resume(session_id="ses_abc")
        assert len(resumed_calls) == 1
        call = resumed_calls[0]
        assert call["session_id"] == "ses_abc"
        assert call["prompt"] == RESUME_BANNER
        assert "Resuming after user inspection via TUI. Continue from where you left off." in call["prompt"]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# US 19: Crash Recovery with tui_open Logs Warning and Clears Flag
# ---------------------------------------------------------------------------
def test_us19_crash_recovery_clears_tui_open_flag(tmp_path: Path) -> None:
    """US 19: When tui_open: true in state.json, recovery logs warning and clears flag."""
    async def _run() -> None:
        state_file = tmp_path / "state.json"
        store = JsonStateStore(path=state_file)
        initial = (
            RunnerState.idle(
                branch="agent/ticket-runner",
                selected_model="test-provider/test-model",
                presence_mode="nearby",
            )
            .to_working(ticket_id="T019", session_id="ses_crash_tui")
            .set_tui_open(session_id="ses_crash_tui")
        )
        store.write(initial.to_dict())

        runner = FakeCommandRunner()
        runner.register_result(["git", "status", "--porcelain"], CommandResult(exit_code=0, stdout="", stderr=""))
        runner.register_result(
            ["opencode", "run", "--format", "json", "--session", "ses_crash_tui"],
            CommandResult(exit_code=0, stdout=json.dumps({"type": "step_finish", "part": {"tokens": {"total": 1000}}}), stderr=""),
        )

        logged_messages: list[str] = []
        git_ops = GitOperations(runner=runner, cwd=tmp_path)
        supervisor = WorkerSupervisor(
            command_runner=runner,
            runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
            budget_config=TokenBudgetConfig(),
            cwd=tmp_path,
        )
        state_coord = StateCoordinator(state_store=store, branch="agent/ticket-runner")

        recovery = CrashRecoveryCoordinator(
            state_store=store,
            git_operations=git_ops,
            worker_supervisor=supervisor,
            state_coordinator=state_coord,
            printer=lambda msg: logged_messages.append(msg),
        )

        result = await recovery.recover()
        assert result.warning_logged is True
        assert any("Runner exited while TUI session was open" in m for m in logged_messages)

        # State file should have tui_open cleared
        saved_state = json.loads(state_file.read_text(encoding="utf-8"))
        assert saved_state.get("tui_open") is False
        assert saved_state.get("tui_session_id") is None

    asyncio.run(_run())
