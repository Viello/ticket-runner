"""Spec 03 Behavioral Test Suite: Worker Orchestration and Context Handoff.

Validates Spec 03 User Stories end-to-end over scripted ``FakeCommandRunner`` streams
and real temporary filesystems under ``tmp_dir``:

  US 01: OpenCode runs as a managed CLI subprocess (``--format json --auto``), never a daemon
  US 02: Scoped prompt composes ticket slice, Spec Excerpt, global Gotchas, execution skill, rules
  US 03: Prompt points at the configured execution skill discipline (TDD, frequent tests)
  US 04: Prompt forbids Worker git commits and requires ``.agent/signals/{ticket_id}_ready.json``
  US 05: Pre-signal ``/code-review`` and conditional ``/security-review`` with ``self_review_notes``
  US 06: ``.agents/skills/diagnosing-bugs/SKILL.md`` is reachable on disk for hard failures
  US 07: Real-time JSON stream parsing of token usage, tool invocations, and textual progress
  US 08: Exactly one WARN notice when occupancy crosses 120,000 tokens
  US 09: Automated handoff instruction dispatched to the active session at 135,000 tokens
  US 10: ``.agent/checkpoints/{ticket_id}/handoff.md`` freshness verified before Session B
  US 11: Session B launches fresh, resuming from the Checkpoint with ``git status`` inspection
  US 12: Hard 150,000-token ceiling force-kills the subprocess
  US 13: Circuit Breaker escalates on crash or ceiling without a handoff Checkpoint
  US 14: Confirmed recovery synthesizes an emergency Checkpoint from ``git status`` / ``git diff``
  US 15: Raw JSON event streams logged to ``.agent/logs/{ticket_id}_session_{session_id}.jsonl``
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import time
from typing import Any

from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecMarkdownParser
from runner.adapters.opencode.opencode_worker import OpenCodeEvent
from runner.application.git_operations import GitOperations
from runner.application.handoff_coordinator import (
    EscalationNotice,
    HandoffCoordinator,
    SingleCycleStatus,
)
from runner.application.worker_supervisor import RunTerminationReason, WorkerSupervisor
from runner.domain.config import WorkerConfig
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_command_runner import FakeCommandRunner, FakeProcessHandle

SPEC_SLUG = "03-worker-orchestration-and-handoff"
SPEC_REL_PATH = f"docs/specs/{SPEC_SLUG}.md"

SPEC_MARKDOWN = (
    "# Spec 03: Worker Orchestration and Context Handoff\n\n"
    "## Problem Statement\n\n"
    "Context windows exhaust on large tasks.\n\n"
    "## Solution\n\n"
    "Supervise the worker subprocess and hand off context.\n"
)

GLOBAL_GOTCHAS_MARKDOWN = (
    "# Global Gotchas & Lessons Learned\n\n"
    "---\n\n"
    "### Probe gotcha for spec 03 suite\n"
    "- **Problem**: Probe problem marked for behavioral assertions.\n"
    "- **Solution**: Probe solution marked for behavioral assertions.\n"
)

PROBE_GOTCHA_TEXT = "Probe problem marked for behavioral assertions."


def _event(
    event_type: str,
    session_id: str | None = None,
    *,
    tokens: int | None = None,
    text: str | None = None,
    tool: str | None = None,
) -> str:
    """Render a single OpenCode JSONL stream line as it would appear on stdout."""
    payload: dict[str, Any] = {"type": event_type}
    if session_id is not None:
        payload["sessionID"] = session_id
    part: dict[str, Any] = {}
    if tokens is not None:
        part["tokens"] = {"total": tokens}
    if text is not None:
        part["text"] = text
    if tool is not None:
        part["tool"] = tool
        part["callID"] = "call_probe_1"
    if part:
        payload["part"] = part
    return json.dumps(payload)


def _scaffold_ticket(ticket_id: str = "T024", security_required: bool = False) -> Ticket:
    return Ticket(
        id=ticket_id,
        title="Spec 03 behavioral suite ticket",
        status=TicketStatus.PENDING,
        spec_path=SPEC_REL_PATH,
        requirements=("Requirement alpha for the suite.",),
        acceptance_criteria=("Acceptance beta for the suite.",),
        gotchas=("Ticket gotcha gamma for the suite.",),
        path=Path(f"docs/tickets/{SPEC_SLUG}/{ticket_id}-behavioral.md"),
        security_required=security_required,
    )


def _write_workspace(root: Path) -> Path:
    """Create the real temporary workspace documents the suite composes from."""
    specs_dir = root / "docs" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    (specs_dir / f"{SPEC_SLUG}.md").write_text(
        SPEC_MARKDOWN, encoding="utf-8", newline=""
    )

    gotchas_path = root / "docs" / "tickets" / "gotchas.md"
    gotchas_path.parent.mkdir(parents=True, exist_ok=True)
    gotchas_path.write_text(GLOBAL_GOTCHAS_MARKDOWN, encoding="utf-8", newline="")
    return gotchas_path


@dataclass
class Scenario:
    """Assembled Spec 03 runtime wired to a scripted command runner and real temp tree."""

    root: Path
    ticket: Ticket
    runtime_paths: RuntimePaths
    runner: FakeCommandRunner
    supervisor: WorkerSupervisor
    coordinator: HandoffCoordinator
    notices: list[str | EscalationNotice] = field(default_factory=list)

    @property
    def checkpoint_path(self) -> Path:
        return self.runtime_paths.checkpoint_path(self.ticket.id)

    @property
    def ready_signal_path(self) -> Path:
        return self.runtime_paths.ready_signal_path(self.ticket.id)


def _scenario(
    root: Path,
    *,
    ticket_id: str = "T024",
    security_required: bool = False,
    confirm_recovery: Callable[[EscalationNotice], bool] | None = None,
    clock: Callable[[], float] = time.time,
    on_event: Callable[[OpenCodeEvent], None] | None = None,
) -> Scenario:
    """Build a Scenario with injected clocks, thresholds, and decline-by-default recovery."""
    gotchas_path = _write_workspace(root)
    ticket = _scaffold_ticket(ticket_id, security_required=security_required)
    runtime_paths = RuntimePaths(root_dir=root / ".agent")
    runner = FakeCommandRunner()
    notices: list[str | EscalationNotice] = []

    supervisor = WorkerSupervisor(
        command_runner=runner,
        runtime_paths=runtime_paths,
        notify=notices.append,
        stall_timeout=30.0,
        bounded_timeout=30.0,
        on_event=on_event,
    )
    coordinator = HandoffCoordinator(
        supervisor=supervisor,
        runtime_paths=runtime_paths,
        gotchas_store=GotchasStore(path=gotchas_path),
        spec_parser=SpecMarkdownParser(),
        worker_config=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        clock=clock,
        notify=notices.append,
        git_operations=GitOperations(runner=runner, cwd=root),
        confirm_recovery=(
            confirm_recovery if confirm_recovery is not None else (lambda esc: False)
        ),
    )
    return Scenario(
        root=root,
        ticket=ticket,
        runtime_paths=runtime_paths,
        runner=runner,
        supervisor=supervisor,
        coordinator=coordinator,
        notices=notices,
    )


class _ArtifactWritingHandle(FakeProcessHandle):
    """Fake handle authoring an artifact deterministically at process exit."""

    def __init__(
        self,
        stdout_lines: list[str],
        artifact_path: Path,
        content: str,
        *,
        stderr: str = "",
        exit_code: int = 0,
    ) -> None:
        super().__init__(stdout_lines=stdout_lines, stderr=stderr, exit_code=exit_code)
        self._artifact_path = artifact_path
        self._content = content

    async def wait(self) -> int:
        self._artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with self._artifact_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(self._content)
        return self._exit_code


def _expected_handoff_prompt(checkpoint_path: Path) -> str:
    return (
        "Context budget threshold reached (135k tokens). Execute the handoff skill at "
        ".agents/skills/handoff/SKILL.md. Save the handoff document directly to "
        f"{checkpoint_path.as_posix()}. Include modified files, architectural decisions, "
        "test status, and immediate next steps. Then exit."
    )


def _expected_resume_prompt(checkpoint_path: Path, ticket_id: str) -> str:
    return (
        f"Read the context handoff document at `{checkpoint_path.as_posix()}`, "
        f"inspect `git status`, then continue working on ticket {ticket_id}."
    )


def _expected_nudge_prompt(ticket_id: str) -> str:
    return (
        f"You exited without writing `.agent/signals/{ticket_id}_ready.json`. "
        f"Write it with your `self_review_notes`, or report the blocker, then exit."
    )


def _opencode_cmd(prompt: str, session_id: str | None = None) -> list[str]:
    """Expected argv for the managed OpenCode CLI invocation contract."""
    cmd = ["opencode", "run", "--format", "json"]
    if session_id is not None:
        cmd.extend(["--session", session_id])
    cmd.extend(["--auto", prompt])
    return cmd


def _expected_jsonl_bytes(scripted_lines: list[str]) -> bytes:
    """Raw stream log bytes: CRLF-stripped lines re-terminated with LF, byte-for-byte."""
    return "".join(line.rstrip("\r\n") + "\n" for line in scripted_lines).encode("utf-8")


# --- US 01: Managed CLI Subprocess Invocation Contract ---


def test_spec_03_us_01_managed_subprocess_invocation_contract(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    session_id = "ses_contract01"
    initial_prompt = "Initial worker prompt."
    resume_prompt = "Resume worker prompt."
    scripted = [_event("step_start", session_id), _event("step_finish", session_id, tokens=1000)]

    scenario.runner.register_spawn(
        _opencode_cmd(initial_prompt),
        stdout_lines=scripted,
        exit_code=0,
    )
    scenario.runner.register_spawn(
        _opencode_cmd(resume_prompt, session_id),
        stdout_lines=scripted,
        exit_code=0,
    )

    async def drive() -> tuple[Any, Any]:
        first = await scenario.supervisor.run(scenario.ticket, initial_prompt)
        second = await scenario.supervisor.run(
            scenario.ticket, resume_prompt, session_id=session_id
        )
        return first, second

    first, second = asyncio.run(drive())

    assert scenario.runner.spawns == [
        _opencode_cmd(initial_prompt),
        _opencode_cmd(resume_prompt, session_id),
    ]
    assert first.reason == RunTerminationReason.EXITED
    assert second.reason == RunTerminationReason.EXITED
    assert second.session_id == session_id


# --- US 02, US 03, US 04, US 05, US 06: Prompt Contract ---


def test_spec_03_us_02_to_us_06_initial_prompt_contract(
    tmp_dir: Path, monkeypatch: Any
) -> None:
    scenario = _scenario(tmp_dir)
    monkeypatch.chdir(scenario.root)

    prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)

    # US 02: active ticket slice
    assert "T024" in prompt
    assert "Spec 03 behavioral suite ticket" in prompt
    assert "Requirement alpha for the suite." in prompt
    assert "Acceptance beta for the suite." in prompt
    assert "Ticket gotcha gamma for the suite." in prompt

    # US 02: automated Spec Excerpt extracted from the parent spec on disk
    assert "## Problem Statement" in prompt
    assert "Context windows exhaust on large tasks." in prompt
    assert "## Solution" in prompt
    assert "Supervise the worker subprocess and hand off context." in prompt
    assert SPEC_REL_PATH in prompt

    # US 02: global Gotchas pointer to docs/tickets/gotchas.md
    assert "docs/tickets/gotchas.md" in prompt
    assert PROBE_GOTCHA_TEXT not in prompt

    # US 03: execution skill pointer and discipline
    assert ".agents/skills/implement/SKILL.md" in prompt
    assert "Test-Driven Development" in prompt

    # US 04: commit prohibition and ready-signal instruction
    assert "git add" in prompt
    assert "git commit" in prompt
    assert "Do NOT" in prompt
    assert ".agent/signals/T024_ready.json" in prompt

    # US 05: review self-checks and self_review_notes
    assert "/code-review" in prompt
    assert "/security-review" not in prompt
    assert "self_review_notes" in prompt

    # US 06: diagnosing-bugs pointer available on disk
    assert ".agents/skills/diagnosing-bugs/SKILL.md" in prompt
    repo_root = Path(__file__).resolve().parents[2]
    assert (repo_root / ".agents" / "skills" / "diagnosing-bugs" / "SKILL.md").is_file()


def test_spec_03_us_05_conditional_security_review_when_flagged(
    tmp_dir: Path, monkeypatch: Any
) -> None:
    scenario = _scenario(tmp_dir, security_required=True)
    monkeypatch.chdir(scenario.root)

    prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)

    assert "/security-review" in prompt
    assert "Security: required" in prompt


# --- US 07, US 08: Telemetry Parsing and WARN-once ---


def test_spec_03_us_07_us_08_stream_telemetry_and_single_warn(tmp_dir: Path) -> None:
    events: list[OpenCodeEvent] = []
    scenario = _scenario(tmp_dir, on_event=events.append)
    session_id = "ses_telemetry07"
    scripted = [
        _event("step_start", session_id),
        _event("tool_call", session_id, tool="read_file"),
        _event("tool_result", session_id, text="file contents"),
        _event("text", session_id, text="working on requirements"),
        _event("step_finish", session_id, tokens=120000),
        _event("step_finish", session_id, tokens=121500),
        _event("step_finish", session_id, tokens=130000),
    ]
    scenario.runner.register_spawn(
        _opencode_cmd("telemetry prompt"),
        stdout_lines=scripted,
        exit_code=0,
    )

    result = asyncio.run(scenario.supervisor.run(scenario.ticket, "telemetry prompt"))

    # US 07: token usage, tool invocations, and textual progress captured in real time
    by_type = {event.type: event for event in events}
    assert by_type["tool_call"].part is not None
    assert by_type["tool_call"].part["tool"] == "read_file"
    assert by_type["tool_result"].part is not None
    assert by_type["tool_result"].part["text"] == "file contents"
    assert by_type["text"].part is not None
    assert by_type["text"].part["text"] == "working on requirements"
    finish_events = [event for event in events if event.type == "step_finish"]
    assert finish_events
    assert all(event.token_usage is not None for event in finish_events)
    assert finish_events[-1].token_usage is not None
    assert finish_events[-1].token_usage.occupancy == 130000
    assert result.occupancy == 130000

    # US 08: exactly one WARN despite three crossings above 120k
    warnings = [
        notice
        for notice in scenario.notices
        if isinstance(notice, str) and "Token budget warning" in notice
    ]
    assert len(warnings) == 1
    assert "120000" in warnings[0]
    assert "warn threshold: 120000" in warnings[0]


# --- US 09, US 10, US 11, US 15: Full A -> Handoff -> B -> READY Chain ---


def test_spec_03_us_09_us_10_us_11_us_15_full_chain_over_real_files(
    tmp_dir: Path,
) -> None:
    scenario = _scenario(tmp_dir)
    session_a_id = "ses_fullChainA"
    session_b_id = "ses_fullChainB"

    checkpoint_bytes = (
        "# Context Handoff: T024\n\n"
        "## Modified Files\n"
        "- runner/application/worker_supervisor.py\n\n"
        "## Next Steps\n"
        "- Finish the behavioral suite\n"
    )
    ready_bytes = '{"status": "ready", "self_review_notes": "All acceptance criteria verified."}\n'

    session_a_lines = [
        _event("step_start", session_a_id),
        _event("text", session_a_id, text="Approaching context limit"),
        _event("step_finish", session_a_id, tokens=135000),
    ]
    handoff_lines = [
        _event("step_start", session_a_id),
        _event("text", session_a_id, text="Writing checkpoint"),
        _event("step_finish", session_a_id, tokens=136000),
    ]
    session_b_lines = [
        _event("step_start", session_b_id),
        _event("step_finish", session_b_id, tokens=20000),
    ]

    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    handoff_prompt = _expected_handoff_prompt(scenario.checkpoint_path)
    resume_prompt = _expected_resume_prompt(scenario.checkpoint_path, "T024")

    scenario.runner.register_spawn(
        _opencode_cmd(initial_prompt),
        stdout_lines=session_a_lines,
        stderr="session a stderr\n",
        exit_code=0,
    )
    scenario.runner.register_spawn_handle(
        _opencode_cmd(handoff_prompt, session_a_id),
        _ArtifactWritingHandle(handoff_lines, scenario.checkpoint_path, checkpoint_bytes),
    )
    scenario.runner.register_spawn_handle(
        _opencode_cmd(resume_prompt),
        _ArtifactWritingHandle(session_b_lines, scenario.ready_signal_path, ready_bytes),
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    # US 09 / US 11: same-session handoff run, then fresh-session Session B resume
    assert scenario.runner.spawns == [
        _opencode_cmd(initial_prompt),
        _opencode_cmd(handoff_prompt, session_a_id),
        _opencode_cmd(resume_prompt),
    ]
    assert result.status == SingleCycleStatus.READY
    assert result.is_ready is True
    assert result.session_ids == (session_a_id, session_b_id)
    assert result.resumed_session_id == session_b_id
    assert result.handoffs == 1
    assert result.ready_signal_present is True
    assert result.occupancy == 136000

    # US 10: worker-authored Checkpoint accepted untouched (no emergency synthesis)
    assert scenario.checkpoint_path.read_bytes() == checkpoint_bytes.encode("utf-8")
    assert b"synthesized" not in scenario.checkpoint_path.read_bytes()

    # US 04 / US 05: ready signal artifact byte-for-byte with self_review_notes
    assert scenario.ready_signal_path.read_bytes() == ready_bytes.encode("utf-8")

    # US 15: raw JSON event streams logged byte-for-byte per session
    jsonl_a = result.jsonl_path_for(session_a_id)
    jsonl_b = result.jsonl_path_for(session_b_id)
    assert jsonl_a == scenario.runtime_paths.session_log_path("T024", session_a_id)
    assert jsonl_a.name == f"T024_session_{session_a_id}.jsonl"
    assert jsonl_a.read_bytes() == _expected_jsonl_bytes(session_a_lines + handoff_lines)
    assert jsonl_b == scenario.runtime_paths.session_log_path("T024", session_b_id)
    assert jsonl_b.read_bytes() == _expected_jsonl_bytes(session_b_lines)

    stderr_a = result.stderr_path_for(session_a_id)
    assert stderr_a == scenario.runtime_paths.session_stderr_path("T024", session_a_id)
    # The stderr sidecar is opened without newline="" so Windows text mode translates LF to CRLF
    assert stderr_a.read_bytes().replace(b"\r\n", b"\n") == b"session a stderr\n"


# --- US 10: Checkpoint Freshness Failure ---


def test_spec_03_us_10_stale_checkpoint_escalates_without_overwrite(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    session_a_id = "ses_staleA"

    session_a_lines = [
        _event("step_start", session_a_id),
        _event("step_finish", session_a_id, tokens=135000),
    ]
    handoff_lines = [
        _event("step_start", session_a_id),
        _event("step_finish", session_a_id, tokens=136000),
    ]

    stale_bytes = "# Old checkpoint from a previous session\n"
    scenario.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with scenario.checkpoint_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(stale_bytes)
    stale_mtime = time.time() - 7200.0
    os.utime(scenario.checkpoint_path, (stale_mtime, stale_mtime))

    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    handoff_prompt = scenario.coordinator.build_handoff_prompt(scenario.ticket)

    scenario.runner.register_spawn(
        _opencode_cmd(initial_prompt),
        stdout_lines=session_a_lines,
    )
    scenario.runner.register_spawn(
        _opencode_cmd(handoff_prompt, session_a_id),
        stdout_lines=handoff_lines,
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == SingleCycleStatus.CHECKPOINT_STALE
    assert result.is_ready is False
    assert len(scenario.runner.spawns) == 2
    # Declined escalation leaves the working tree untouched: stale Checkpoint byte-identical
    assert scenario.checkpoint_path.read_bytes() == stale_bytes.encode("utf-8")
    assert any(
        isinstance(notice, EscalationNotice)
        and notice.reason == SingleCycleStatus.CHECKPOINT_STALE.value
        for notice in scenario.notices
    )


# --- US 12: Hard 150k Ceiling ---


def test_spec_03_us_12_hard_ceiling_force_kills_subprocess(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    session_a_id = "ses_ceilingA"
    scripted = [
        _event("step_start", session_a_id),
        _event("step_finish", session_a_id, tokens=150000),
    ]
    handle = FakeProcessHandle(stdout_lines=scripted, pid=515151)
    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    scenario.runner.register_spawn_handle(
        _opencode_cmd(initial_prompt),
        handle,
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == SingleCycleStatus.CEILING
    assert handle.terminated is True
    assert ["taskkill", "/PID", "515151", "/T", "/F"] in scenario.runner.commands
    # Declined escalation: no emergency synthesis, no fresh resume session
    assert len(scenario.runner.spawns) == 1
    assert not scenario.checkpoint_path.exists()


# --- US 13, US 14: Crash Circuit Breaker and Confirmed Emergency Synthesis ---


def test_spec_03_us_13_us_14_crash_escalation_and_confirmed_synthesis(
    tmp_dir: Path,
) -> None:
    frozen_time = 1_700_000_000.0
    scenario = _scenario(
        tmp_dir,
        confirm_recovery=lambda escalation: True,
        clock=lambda: frozen_time,
    )
    session_a_id = "ses_crashSynthesis"
    session_b_id = "ses_emergencyResume"
    porcelain = " M runner/application/worker_supervisor.py\n?? scratch.tmp\n"
    diff_stat = (
        " runner/application/worker_supervisor.py | 4 ++--\n"
        " 1 file changed, 2 insertions(+), 2 deletions(-)\n"
    )
    ready_bytes = '{"status": "ready", "self_review_notes": "Recovered from synthesis."}\n'

    crash_lines = [_event("step_start", session_a_id)]
    retry_crash_lines = [_event("step_start", session_a_id)]
    resumed_lines = [
        _event("step_start", session_b_id),
        _event("step_finish", session_b_id, tokens=15000),
    ]

    class _CrashHandleA(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=crash_lines, stderr="boom: worker crashed\n", exit_code=1
            )

    class _CrashHandleB(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=retry_crash_lines,
                stderr="boom: retry crashed\n",
                exit_code=1,
            )

    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    retry_prompt = scenario.coordinator.build_crash_retry_prompt(
        scenario.ticket, "boom: worker crashed"
    )
    resume_prompt = _expected_resume_prompt(scenario.checkpoint_path, "T024")

    scenario.runner.register(["git", "status", "--porcelain"], stdout=porcelain)
    scenario.runner.register(["git", "diff", "--stat"], stdout=diff_stat)

    scenario.runner.register_spawn_handle(
        _opencode_cmd(initial_prompt), _CrashHandleA()
    )
    scenario.runner.register_spawn_handle(
        _opencode_cmd(retry_prompt, session_a_id),
        _CrashHandleB(),
    )
    scenario.runner.register_spawn_handle(
        _opencode_cmd(resume_prompt),
        _ArtifactWritingHandle(resumed_lines, scenario.ready_signal_path, ready_bytes),
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    # US 13: circuit breaker escalated on the second crash, alerting through the notify seam
    escalation_notices = [
        notice for notice in scenario.notices if isinstance(notice, EscalationNotice)
    ]
    assert len(escalation_notices) == 1
    assert escalation_notices[0].reason == "CRASH_AFTER_RETRY"
    assert escalation_notices[0].ticket_id == "T024"
    assert "boom: retry crashed" in escalation_notices[0].stderr_tail

    # US 14: confirmed recovery synthesized the emergency Checkpoint byte-for-byte
    expected_checkpoint = (
        "# Context Handoff: T024\n"
        "\n"
        "synthesized — no Worker handoff\n"
        "\n"
        "- Ticket: T024\n"
        "- Reason: CRASH_AFTER_RETRY\n"
        "- Source Session: ses_crashSynthesis\n"
        "- Timestamp: 1700000000.0\n"
        "\n"
        "## Working Tree Status (`git status --porcelain`)\n"
        "\n"
        "```\n"
        "M runner/application/worker_supervisor.py\n"
        "?? scratch.tmp\n"
        "```\n"
        "\n"
        "## Working Tree Diff Stat (`git diff --stat`)\n"
        "\n"
        "```\n"
        "runner/application/worker_supervisor.py | 4 ++--\n"
        " 1 file changed, 2 insertions(+), 2 deletions(-)\n"
        "```\n"
    )
    assert scenario.checkpoint_path.read_bytes() == expected_checkpoint.encode("utf-8")

    # Fresh Session B launched automatically without discarding uncommitted work
    assert scenario.runner.spawns == [
        _opencode_cmd(initial_prompt),
        _opencode_cmd(retry_prompt, session_a_id),
        _opencode_cmd(resume_prompt),
    ]
    assert result.status == SingleCycleStatus.READY
    assert result.resumed_session_id == session_b_id
    assert result.ready_signal_present is True
    assert scenario.ready_signal_path.read_bytes() == ready_bytes.encode("utf-8")


# --- Recovery Path 1: Exit 0 Without Ready Signal (Nudge) ---


def test_spec_03_recovery_nudge_after_exit_zero_without_ready_signal(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    session_id = "ses_nudgeOnly"
    ready_bytes = '{"status": "ready", "self_review_notes": "Nudged into signal."}\n'

    session_lines = [
        _event("step_start", session_id),
        _event("step_finish", session_id, tokens=30000),
    ]
    nudge_lines = [
        _event("step_start", session_id),
        _event("step_finish", session_id, tokens=31000),
    ]

    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    nudge_prompt = _expected_nudge_prompt("T024")

    scenario.runner.register_spawn(
        _opencode_cmd(initial_prompt),
        stdout_lines=session_lines,
    )
    scenario.runner.register_spawn_handle(
        _opencode_cmd(nudge_prompt, session_id),
        _ArtifactWritingHandle(nudge_lines, scenario.ready_signal_path, ready_bytes),
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    assert result.status == SingleCycleStatus.READY
    assert scenario.runner.spawns[1] == _opencode_cmd(nudge_prompt, session_id)
    assert scenario.ready_signal_path.read_bytes() == ready_bytes.encode("utf-8")


# --- Recovery Path 2: Crash Retry with Stderr Tail ---


def test_spec_03_recovery_crash_retry_embeds_stderr_tail(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    session_id = "ses_crashRetry"
    ready_bytes = '{"status": "ready", "self_review_notes": "Recovered after crash."}\n'

    crash_lines = [_event("step_start", session_id)]
    retry_lines = [
        _event("step_start", session_id),
        _event("step_finish", session_id, tokens=45000),
    ]

    class _CrashHandle(FakeProcessHandle):
        def __init__(self) -> None:
            super().__init__(
                stdout_lines=crash_lines,
                stderr="Traceback: missing module foo\n",
                exit_code=3,
            )

    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    expected_retry_prompt = (
        "The previous Worker process crashed or reported an error.\n\n"
        "Stderr tail:\n```\nTraceback: missing module foo\n```\n\n"
        "Please diagnose and resolve the issue, continue implementing ticket T024, "
        "and write `.agent/signals/T024_ready.json` upon completion, then exit."
    )

    scenario.runner.register_spawn_handle(
        _opencode_cmd(initial_prompt), _CrashHandle()
    )
    scenario.runner.register_spawn_handle(
        _opencode_cmd(expected_retry_prompt, session_id),
        _ArtifactWritingHandle(retry_lines, scenario.ready_signal_path, ready_bytes),
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    assert result.status == SingleCycleStatus.READY
    assert result.session_ids == (session_id,)
    assert scenario.runner.spawns == [
        _opencode_cmd(initial_prompt),
        _opencode_cmd(expected_retry_prompt, session_id),
    ]


# --- Handoff Chain Cap ---


def test_spec_03_handoff_chain_cap_escalates_after_five_cycles(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    session_ids = [f"ses_cap{i}" for i in range(1, 6)]

    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    handoff_prompt = _expected_handoff_prompt(scenario.checkpoint_path)
    resume_prompt = _expected_resume_prompt(scenario.checkpoint_path, "T024")

    for index, session_id in enumerate(session_ids):
        session_lines = [
            _event("step_start", session_id),
            _event("step_finish", session_id, tokens=135100),
        ]
        handoff_lines = [
            _event("step_start", session_id),
            _event("step_finish", session_id, tokens=136000),
        ]
        checkpoint_content = f"# Checkpoint cycle {index + 1}\n- Handing off fresh context\n"

        if index == 0:
            scenario.runner.register_spawn(
                _opencode_cmd(initial_prompt),
                stdout_lines=session_lines,
            )
        else:
            scenario.runner.register_spawn(
                _opencode_cmd(resume_prompt),
                stdout_lines=session_lines,
            )
        scenario.runner.register_spawn_handle(
            _opencode_cmd(handoff_prompt, session_id),
            _ArtifactWritingHandle(
                handoff_lines, scenario.checkpoint_path, checkpoint_content
            ),
        )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result.handoffs == 5
    assert result.session_ids == tuple(session_ids)
    assert result.escalation is not None
    assert result.escalation.reason == "5 handoffs without completion"
    # Exactly 5 worker sessions + 5 handoff runs: absolutely no sixth session
    assert len(scenario.runner.spawns) == 10
    for index, spawn in enumerate(scenario.runner.spawns):
        if index % 2 == 0:
            # Even spawns are fresh sessions (Session A or resumed Session N+1)
            assert "--session" not in spawn
        else:
            # Odd spawns are same-session handoff instruction runs bound to that cycle's session
            assert spawn[spawn.index("--session") + 1] == session_ids[(index - 1) // 2]


# --- Security: Session ID Sanitization ---


def test_spec_03_session_id_sanitization_blocks_logs_and_resume(tmp_dir: Path) -> None:
    scenario = _scenario(tmp_dir)
    malicious_session_id = "ses_evil;rm -rf /"
    scripted = [
        _event("step_start", malicious_session_id),
        _event("step_finish", malicious_session_id, tokens=135000),
    ]
    initial_prompt = scenario.coordinator.build_initial_prompt(scenario.ticket)
    scenario.runner.register_spawn(
        _opencode_cmd(initial_prompt),
        stdout_lines=scripted,
    )

    result = asyncio.run(scenario.coordinator.run_cycle(scenario.ticket))

    assert result.status == SingleCycleStatus.ESCALATED
    assert result == SingleCycleStatus.FAILED
    assert len(scenario.runner.spawns) == 1
    assert all("--session" not in spawn for spawn in scenario.runner.spawns)

    logs_dir = scenario.runtime_paths.logs_dir
    assert not logs_dir.exists() or list(logs_dir.iterdir()) == []

    assert any(
        isinstance(notice, str) and "allowlist" in notice.lower()
        for notice in scenario.notices
    )
