"""Unit tests for WorkerSupervisor application orchestrator (T019)."""

import asyncio
import json
from pathlib import Path
import pytest

from runner.application.worker_supervisor import (
    BOUNDED_RUN_TIMEOUT_SECONDS,
    STALL_SILENCE_SECONDS,
    RunTerminationReason,
    SessionRunResult,
    WorkerSupervisor,
)
from runner.domain.config import TokenBudgetConfig
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.telemetry import BudgetMonitor
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner


def _make_ticket(ticket_id: str = "T019") -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Worker supervisor test ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/03-worker-orchestration-and-handoff.md",
        requirements=("Requirement 1",),
        acceptance_criteria=("Criterion 1",),
        gotchas=(),
        path=Path(f"docs/tickets/03-worker-orchestration-and-handoff/{ticket_id}-test.md"),
    )


# --- AC 1: Telemetry and Warning Notification ---


def test_scripted_stream_warn_notification_and_occupancy(tmp_path: Path) -> None:
    """A scripted stream (step_start -> text -> step_finish at 120k) yields exactly one

    WARN notice through the injected recorder and leaves occupancy equal to the last
    step_finish value.
    """
    fake_runner = FakeCommandRunner()
    session_id = "ses_abc123456"

    lines = [
        json.dumps({
            "type": "step_start",
            "sessionID": session_id,
        }) + "\r\n",
        json.dumps({
            "type": "text",
            "sessionID": session_id,
            "part": {"text": "Executing initial inspection"},
        }) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_id,
            "part": {
                "tokens": {
                    "total": 120000,
                    "input": 100000,
                    "output": 20000,
                }
            },
        }) + "\r\n",
    ]

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "prompt text"],
        stdout_lines=lines,
        stderr="clean run\n",
        exit_code=0,
    )

    recorded_notices: list[str] = []
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        notify=recorded_notices.append,
    )

    ticket = _make_ticket("T019")

    async def _run() -> SessionRunResult:
        return await supervisor.run(ticket=ticket, prompt="prompt text")

    result = asyncio.run(_run())

    # Exactly one WARN notice emitted
    assert len(recorded_notices) == 1
    assert "120000" in recorded_notices[0]
    assert "T019" in recorded_notices[0]

    # Result state validation
    assert result.session_id == session_id
    assert result.occupancy == 120000
    assert result.latest_occupancy == 120000
    assert result.exit_code == 0
    assert result.reason == RunTerminationReason.EXITED
    assert result.ready_signal_present is False
    assert result.stderr_tail == "clean run"


# --- AC 2: JSONL and Stderr Logging Across Resumed Runs ---


def test_session_logging_and_append_across_resumed_runs(tmp_path: Path) -> None:
    """JSONL matches scripted stdout lines, appends across resumed runs, and captures stderr."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_resume999"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    run1_lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\r\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 50000}}}) + "\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "initial run"],
        stdout_lines=run1_lines,
        stderr="stderr run 1\n",
        exit_code=0,
    )

    run2_lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 80000}}}) + "\r\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", session_id, "--auto", "resumed run"],
        stdout_lines=run2_lines,
        stderr="stderr run 2\n",
        exit_code=0,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    ticket = _make_ticket("T019")

    async def _execute() -> tuple[SessionRunResult, SessionRunResult]:
        res1 = await supervisor.run(ticket=ticket, prompt="initial run")
        res2 = await supervisor.run(ticket=ticket, prompt="resumed run", session_id=session_id)
        return res1, res2

    res1, res2 = asyncio.run(_execute())

    assert res1.session_id == session_id
    assert res2.session_id == session_id

    # Verify log paths exist
    jsonl_path = runtime_paths.session_log_path("T019", session_id)
    stderr_path = runtime_paths.session_stderr_path("T019", session_id)

    assert jsonl_path.exists()
    assert stderr_path.exists()
    assert res2.jsonl_path == jsonl_path
    assert res2.stderr_path == stderr_path

    # Content of JSONL should contain all 4 lines (appended, not truncated)
    with jsonl_path.open("r", encoding="utf-8", newline="") as f:
        stored_lines = [line.rstrip("\r\n") for line in f]

    expected_stripped = [
        line.rstrip("\r\n") for line in (run1_lines + run2_lines)
    ]
    assert stored_lines == expected_stripped

    # Stderr sidecar should contain both stderr outputs
    stderr_content = stderr_path.read_text(encoding="utf-8")
    assert "stderr run 1\n" in stderr_content
    assert "stderr run 2\n" in stderr_content


# --- AC 3: Unknown Event Types and Unparseable Lines ---


def test_unknown_event_types_and_unparseable_lines(tmp_path: Path) -> None:
    """Unknown event types and unparseable lines are recorded and skipped; run completes."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_tolerant123"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    lines = [
        "THIS IS NOT JSON {{{{\n",
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "some_unknown_future_event", "sessionID": session_id, "data": 42}) + "\n",
        "ANOTHER UNPARSEABLE LINE\r\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_id,
            "part": {"tokens": {"total": 45000}},
        }) + "\n",
    ]

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "tolerant run"],
        stdout_lines=lines,
        stderr="handled cleanly\n",
        exit_code=42,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    async def _run() -> SessionRunResult:
        return await supervisor.run("T019", prompt="tolerant run")

    result = asyncio.run(_run())

    assert result.session_id == session_id
    assert result.exit_code == 42
    assert result.occupancy == 45000

    # JSONL log should record every line faithfully
    jsonl_path = runtime_paths.session_log_path("T019", session_id)
    assert jsonl_path.exists()
    logged_content = jsonl_path.read_text(encoding="utf-8")
    assert "THIS IS NOT JSON {{{{" in logged_content
    assert "some_unknown_future_event" in logged_content
    assert "ANOTHER UNPARSEABLE LINE" in logged_content


# --- AC 4: Ready Signal Detection and Session ID Allowlist ---


def test_ready_signal_presence_detection(tmp_path: Path) -> None:
    """Ready-signal presence flips based on real file existence in .agent/signals/."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_readytest"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 1000}}}) + "\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "signal run"],
        stdout_lines=lines,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    # 1. Before signal exists -> ready_signal_present is False
    async def _run1() -> SessionRunResult:
        return await supervisor.run("T019", prompt="signal run")

    res1 = asyncio.run(_run1())
    assert res1.ready_signal_present is False

    # 2. Create signal file on disk
    runtime_paths.ensure_signals_dir()
    signal_file = runtime_paths.ready_signal_path("T019")
    signal_file.write_text('{"status":"ready"}', encoding="utf-8")

    # 3. Next run detects signal file existence
    async def _run2() -> SessionRunResult:
        return await supervisor.run("T019", prompt="signal run")

    res2 = asyncio.run(_run2())
    assert res2.ready_signal_present is True


def test_session_id_allowlist_rejection_and_diagnostic(tmp_path: Path) -> None:
    """A session id failing the allowlist produces no log file and a diagnostic."""
    fake_runner = FakeCommandRunner()
    malicious_session_id = "../../malicious_escape"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    lines = [
        json.dumps({"type": "step_start", "sessionID": malicious_session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": malicious_session_id, "part": {"tokens": {"total": 1000}}}) + "\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "bad session id"],
        stdout_lines=lines,
    )

    recorded_notices: list[str] = []
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        notify=recorded_notices.append,
    )

    async def _run() -> SessionRunResult:
        return await supervisor.run("T019", prompt="bad session id")

    result = asyncio.run(_run())

    # Result indicates dropped session due to invalid ID
    assert result.reason == RunTerminationReason.DROPPED
    assert result.session_id == malicious_session_id
    assert result.jsonl_path is None
    assert result.stderr_path is None
    assert result.log_paths == ()

    # No files created in logs directory
    assert not runtime_paths.logs_dir.exists() or len(list(runtime_paths.logs_dir.iterdir())) == 0

    # Diagnostic is surfaced through notify
    assert len(recorded_notices) >= 1
    assert any("allowlist" in n.lower() or "invalid" in n.lower() for n in recorded_notices)
    assert any("allowlist" in d.lower() or "invalid" in d.lower() for d in result.diagnostics)


# --- Security: Command Construction and Argv Verification ---


def test_argv_construction_safety(tmp_path: Path) -> None:
    """Verify argv is passed as a token list without shell interpolation."""
    fake_runner = FakeCommandRunner()
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    session_id = "ses_safe123"

    lines = [json.dumps({"type": "step_start", "sessionID": session_id}) + "\n"]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "prompt with ; rm -rf / && echo dangerous"],
        stdout_lines=lines,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    async def _run() -> None:
        await supervisor.run("T019", prompt="prompt with ; rm -rf / && echo dangerous")

    asyncio.run(_run())

    assert len(fake_runner.spawn_invocations) == 1
    inv = fake_runner.spawn_invocations[0]
    assert isinstance(inv.cmd, list)
    assert inv.cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "--auto",
        "prompt with ; rm -rf / && echo dangerous",
    ]


def test_stderr_tail_trimming() -> None:
    """Verify stderr tail is trimmed properly without memory bloat."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_tailtest"

    huge_stderr = "\n".join(f"error line {i}" for i in range(200))
    lines = [json.dumps({"type": "step_start", "sessionID": session_id}) + "\n"]

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "huge stderr"],
        stdout_lines=lines,
        stderr=huge_stderr,
    )

    supervisor = WorkerSupervisor(command_runner=fake_runner)

    async def _run() -> SessionRunResult:
        return await supervisor.run("T019", prompt="huge stderr")

    result = asyncio.run(_run())

    tail_lines = result.stderr_tail.splitlines()
    assert len(tail_lines) <= 50
    assert tail_lines[-1] == "error line 199"


def test_sub_threshold_occupancy_does_not_fire_warning(tmp_path: Path) -> None:
    """Verify stream staying below warn threshold never emits a WARN notice."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_subthresh"
    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_id,
            "part": {"tokens": {"total": 50000}},
        }) + "\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "sub threshold"],
        stdout_lines=lines,
    )

    notices: list[str] = []
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        notify=notices.append,
    )

    result = asyncio.run(supervisor.run("T019", prompt="sub threshold"))

    assert len(notices) == 0
    assert result.occupancy == 50000
    assert result.reason == RunTerminationReason.EXITED


def test_multiple_steps_warn_fires_once_only(tmp_path: Path) -> None:
    """Verify multiple step_finish events crossing and staying above 120k only warn once."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_multistep"
    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 122000}}}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 128000}}}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 130000}}}) + "\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "multi step"],
        stdout_lines=lines,
    )

    notices: list[str] = []
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        notify=notices.append,
    )

    result = asyncio.run(supervisor.run("T019", prompt="multi step"))

    assert len(notices) == 1
    assert result.occupancy == 130000


def test_custom_token_budget_config(tmp_path: Path) -> None:
    """Verify custom TokenBudgetConfig warn threshold is respected."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_customcfg"
    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 60000}}}) + "\n",
    ]
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "custom cfg"],
        stdout_lines=lines,
    )

    notices: list[str] = []
    custom_budget = TokenBudgetConfig(warn=50000, handoff=80000, ceiling=100000)
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        budget_config=custom_budget,
        notify=notices.append,
    )

    result = asyncio.run(supervisor.run("T019", prompt="custom cfg"))

    assert len(notices) == 1
    assert "60000" in notices[0]
    assert "50000" in notices[0]
    assert result.occupancy == 60000


def test_default_notify_writes_to_stderr(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Verify default notify callable writes lines to sys.stderr with ticket context."""
    from runner.application.worker_supervisor import _default_notify
    import io

    fake_stderr = io.StringIO()
    monkeypatch.setattr("sys.stderr", fake_stderr)

    _default_notify("[T019] Notice message")
    assert "[T019] Notice message\n" == fake_stderr.getvalue()


# --- T020: Stall Watchdog, Termination Ladder, Bounded Runs ---


def test_t020_module_scope_constants() -> None:
    """Verify module constants STALL_SILENCE_SECONDS and BOUNDED_RUN_TIMEOUT_SECONDS."""
    assert STALL_SILENCE_SECONDS == 900
    assert BOUNDED_RUN_TIMEOUT_SECONDS == 300


def test_stall_watchdog_terminates_silent_stream_and_returns_stalled(tmp_path: Path) -> None:
    """A fake stream that goes silent beyond 900s (injected clock) returns STALLED and records termination."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_stall100"
    current_time = [0.0]

    def fake_clock() -> float:
        return current_time[0]

    # Handle that advances clock between lines to simulate silence beyond 900s
    class SilentDelayedHandle:
        def __init__(self) -> None:
            self.pid = 4321
            self.stderr = ""
            self.terminated = False

        async def stdout_lines(self):
            yield json.dumps({"type": "step_start", "sessionID": session_id})
            # Advance clock past stall silence limit (900s)
            current_time[0] = 905.0
            await asyncio.sleep(0.001)
            yield json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 1000}}})

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return -15

        async def terminate(self) -> None:
            self.terminated = True

    handle = SilentDelayedHandle()
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "stall prompt"],
        handle,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        clock=fake_clock,
    )

    result = asyncio.run(supervisor.run("T020", prompt="stall prompt"))

    assert result.reason == RunTerminationReason.STALLED
    assert handle.terminated is True
    # Termination ladder called taskkill on handle.pid
    assert any(
        cmd == ["taskkill", "/PID", "4321", "/T", "/F"]
        for cmd in fake_runner.commands
    )


def test_stall_watchdog_fires_on_zero_output_stream(tmp_path: Path) -> None:
    """A stream that produces no lines at all times out via stall watchdog and returns STALLED."""
    fake_runner = FakeCommandRunner()

    class EmptySilentHandle:
        def __init__(self) -> None:
            self.pid = 5566
            self.stderr = ""
            self.terminated = False

        async def stdout_lines(self):
            await asyncio.sleep(0.05)
            if False:
                yield ""

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return -9

        async def terminate(self) -> None:
            self.terminated = True

    handle = EmptySilentHandle()
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "empty silent"],
        handle,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        stall_timeout=0.01,
    )

    result = asyncio.run(supervisor.run("T020", prompt="empty silent"))

    assert result.reason == RunTerminationReason.STALLED
    assert handle.terminated is True
    assert any(
        cmd == ["taskkill", "/PID", "5566", "/T", "/F"]
        for cmd in fake_runner.commands
    )


def test_request_kill_mid_stream_returns_promptly_with_reason_and_logs(tmp_path: Path) -> None:
    """Calling request_kill(KILLED_HANDOFF) mid-stream returns promptly with that reason and persisted logs."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_handoffkill123"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 100000}}}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 135000}}}) + "\n",
        json.dumps({"type": "text", "sessionID": session_id, "part": {"text": "should not be processed"}}) + "\n",
    ]

    handle = fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "handoff prompt"],
        stdout_lines=lines,
        pid=7788,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    def budget_callback(action, occupancy):
        from runner.domain.telemetry import BudgetAction
        if action == BudgetAction.HANDOFF:
            supervisor.request_kill(RunTerminationReason.KILLED_HANDOFF)

    supervisor._on_budget_action = budget_callback

    result = asyncio.run(supervisor.run("T020", prompt="handoff prompt"))

    assert result.reason == RunTerminationReason.KILLED_HANDOFF
    assert result.session_id == session_id
    assert handle.terminated is True
    assert any(
        cmd == ["taskkill", "/PID", "7788", "/T", "/F"]
        for cmd in fake_runner.commands
    )

    # Verify all lines consumed up to kill were written to session log
    jsonl_path = runtime_paths.session_log_path("T020", session_id)
    assert jsonl_path.exists()
    content = jsonl_path.read_text(encoding="utf-8")
    assert "100000" in content
    assert "135000" in content


def test_request_kill_via_concurrent_async_task(tmp_path: Path) -> None:
    """Calling request_kill externally from a concurrent async task interrupts stream reading."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_ceilingkill123"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    class SlowStreamHandle:
        def __init__(self) -> None:
            self.pid = 9911
            self.stderr = ""
            self.terminated = False

        async def stdout_lines(self):
            yield json.dumps({"type": "step_start", "sessionID": session_id})
            while not self.terminated:
                await asyncio.sleep(0.01)
                yield json.dumps({"type": "text", "sessionID": session_id, "part": {"text": "working..."}})

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return 137

        async def terminate(self) -> None:
            self.terminated = True

    handle = SlowStreamHandle()
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "concurrent kill"],
        handle,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
    )

    async def scenario() -> SessionRunResult:
        run_task = asyncio.create_task(supervisor.run("T020", prompt="concurrent kill"))
        await asyncio.sleep(0.02)
        await supervisor.request_kill("KILLED_CEILING")
        return await run_task

    result = asyncio.run(scenario())

    assert result.reason == RunTerminationReason.KILLED_CEILING
    assert handle.terminated is True
    assert any(
        cmd == ["taskkill", "/PID", "9911", "/T", "/F"]
        for cmd in fake_runner.commands
    )


def test_bounded_run_wall_clock_timeout_kills_process(tmp_path: Path) -> None:
    """A bounded run exceeding 300s wall-clock (injected) is killed; an unbounded run under the same script is not."""
    session_id = "ses_bounded1"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    class WallClockScriptHandle:
        def __init__(self, clock_holder: list[float]) -> None:
            self.pid = 1122
            self.stderr = ""
            self.terminated = False
            self.clock_holder = clock_holder

        async def stdout_lines(self):
            yield json.dumps({"type": "step_start", "sessionID": session_id})
            self.clock_holder[0] += 120.0
            await asyncio.sleep(0.001)
            yield json.dumps({"type": "text", "sessionID": session_id, "part": {"text": "first phase"}})
            self.clock_holder[0] += 120.0
            await asyncio.sleep(0.001)
            yield json.dumps({"type": "text", "sessionID": session_id, "part": {"text": "second phase"}})
            self.clock_holder[0] += 120.0
            await asyncio.sleep(0.001)
            yield json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 5000}}})

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return 0

        async def terminate(self) -> None:
            self.terminated = True

    # 1. Bounded run: total clock exceeds 300s -> killed!
    clock_holder1 = [0.0]
    runner1 = FakeCommandRunner()
    handle1 = WallClockScriptHandle(clock_holder1)
    runner1.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "bounded prompt"],
        handle1,
    )
    supervisor1 = WorkerSupervisor(
        command_runner=runner1,
        runtime_paths=runtime_paths,
        clock=lambda: clock_holder1[0],
    )
    res_bounded = asyncio.run(supervisor1.run("T020", prompt="bounded prompt", bounded=True))

    assert res_bounded.reason == RunTerminationReason.STALLED
    assert handle1.terminated is True
    assert any(
        cmd == ["taskkill", "/PID", "1122", "/T", "/F"]
        for cmd in runner1.commands
    )

    # 2. Unbounded run: exact same script runs to completion without termination!
    clock_holder2 = [0.0]
    runner2 = FakeCommandRunner()
    handle2 = WallClockScriptHandle(clock_holder2)
    runner2.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "unbounded prompt"],
        handle2,
    )
    supervisor2 = WorkerSupervisor(
        command_runner=runner2,
        runtime_paths=runtime_paths,
        clock=lambda: clock_holder2[0],
    )
    res_unbounded = asyncio.run(supervisor2.run("T020", prompt="unbounded prompt", bounded=False))

    assert res_unbounded.reason == RunTerminationReason.EXITED
    assert handle2.terminated is False
    assert not any("taskkill" in cmd[0] for cmd in runner2.commands)


def test_stderr_flood_slow_stdout_exits_cleanly_without_deadlock(tmp_path: Path) -> None:
    """A child that floods stderr while stdout is slow returns EXITED without deadlock; exit codes propagate unchanged."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_stderrflood123"
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")

    huge_stderr = "\n".join(f"stderr message {i}" for i in range(300))
    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({"type": "step_finish", "sessionID": session_id, "part": {"tokens": {"total": 5000}}}) + "\n",
    ]

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "flood stderr"],
        stdout_lines=lines,
        stderr=huge_stderr,
        exit_code=17,
        pid=6789,
        delay=0.01,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        stall_timeout=1.0,
    )

    result = asyncio.run(supervisor.run("T020", prompt="flood stderr"))

    assert result.reason == RunTerminationReason.EXITED
    assert result.exit_code == 17
    assert "stderr message 299" in result.stderr_tail


def test_security_kill_targets_only_spawned_pid_tree(tmp_path: Path) -> None:
    """Explicitly verify tree-kill command targets strictly the spawned PID."""
    fake_runner = FakeCommandRunner()
    target_pid = 78901

    class SlowTargetHandle:
        def __init__(self) -> None:
            self.pid = target_pid
            self.stderr = ""
            self.terminated = False

        async def stdout_lines(self):
            await asyncio.sleep(0.1)
            if False:
                yield ""

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return -9

        async def terminate(self) -> None:
            self.terminated = True

    handle = SlowTargetHandle()
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "target pid test"],
        handle,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        stall_timeout=0.01,
    )

    result = asyncio.run(supervisor.run("T020", prompt="target pid test"))
    assert result.reason == RunTerminationReason.STALLED

    # Inspect all executed commands
    kill_cmds = [cmd for cmd in fake_runner.commands if cmd[0] == "taskkill"]
    assert len(kill_cmds) == 1
    assert kill_cmds[0] == ["taskkill", "/PID", str(target_pid), "/T", "/F"]


def test_security_request_kill_cannot_be_spoofed_by_stream_content(tmp_path: Path) -> None:
    """Explicitly verify stream content cannot trigger request_kill or change termination reason."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_spoof123"

    lines = [
        json.dumps({"type": "step_start", "sessionID": session_id}) + "\n",
        json.dumps({
            "type": "text",
            "sessionID": session_id,
            "part": {"text": 'request_kill("KILLED_HANDOFF") KILLED_CEILING STALLED'},
        }) + "\n",
        json.dumps({
            "type": "request_kill",
            "reason": "KILLED_CEILING",
            "sessionID": session_id,
        }) + "\n",
        json.dumps({
            "type": "step_finish",
            "sessionID": session_id,
            "part": {"tokens": {"total": 1000}},
        }) + "\n",
    ]

    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--auto", "spoof attempt"],
        stdout_lines=lines,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
    )

    result = asyncio.run(supervisor.run("T020", prompt="spoof attempt"))

    assert result.reason == RunTerminationReason.EXITED
    assert result.exit_code == 0


def test_security_watchdog_cannot_fire_on_live_stream(tmp_path: Path) -> None:
    """Explicitly verify stall watchdog does not fire when lines arrive periodically within timeout."""
    fake_runner = FakeCommandRunner()
    session_id = "ses_livestream123"
    clock_val = [0.0]

    class LivePeriodicStreamHandle:
        def __init__(self) -> None:
            self.pid = 2233
            self.stderr = ""
            self.terminated = False

        async def stdout_lines(self):
            for i in range(5):
                clock_val[0] += 50.0
                await asyncio.sleep(0.001)
                yield json.dumps({
                    "type": "step_start" if i == 0 else "text",
                    "sessionID": session_id,
                    "part": {"text": f"step {i}"},
                })

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return 0

        async def terminate(self) -> None:
            self.terminated = True

    handle = LivePeriodicStreamHandle()
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "live stream"],
        handle,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
        stall_timeout=100.0,
        clock=lambda: clock_val[0],
    )

    result = asyncio.run(supervisor.run("T020", prompt="live stream"))

    assert result.reason == RunTerminationReason.EXITED
    assert handle.terminated is False
    assert not any("taskkill" in cmd[0] for cmd in fake_runner.commands)


def test_security_no_process_survives_run_return_on_exception(tmp_path: Path) -> None:
    """Explicitly verify process termination ladder is executed even if run() encounters an exception."""
    fake_runner = FakeCommandRunner()

    class ExplodingHandle:
        def __init__(self) -> None:
            self.pid = 9999
            self.stderr = ""
            self.terminated = False

        async def stdout_lines(self):
            yield json.dumps({"type": "step_start", "sessionID": "ses_boom"})
            raise RuntimeError("Corrupted stream failure")

        def __aiter__(self):
            return self.stdout_lines()

        async def wait(self) -> int:
            return -1

        async def terminate(self) -> None:
            self.terminated = True

    handle = ExplodingHandle()
    fake_runner.register_spawn_handle(
        ["opencode", "run", "--format", "json", "--auto", "explode"],
        handle,
    )

    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=RuntimePaths(root_dir=tmp_path / ".agent"),
    )

    with pytest.raises(RuntimeError, match="Corrupted stream failure"):
        asyncio.run(supervisor.run("T020", prompt="explode"))

    assert handle.terminated is True
    assert any(
        cmd == ["taskkill", "/PID", "9999", "/T", "/F"]
        for cmd in fake_runner.commands
    )


