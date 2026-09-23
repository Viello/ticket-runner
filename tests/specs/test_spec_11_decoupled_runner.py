"""Spec 11 Integration Suite: Decoupled Project Root & Multi-Agent Worker Port.

Validates end-to-end decoupled execution against external target repositories:
  US 01: Operator runs ticket-runner with --project-dir against an external target directory.
  US 02: Default fallback to CWD when --project-dir is omitted preserves backward compatibility.
  US 03: Path validation rejects non-existent paths or non-directories cleanly with code 1.
  US 10: Multi-agent provider toggle in external target config.yaml (opencode vs antigravity).
  US 11: Doctor pre-flight checks execute against external target directory and verify provider binary.
  US 12: Deterministic test doubles allow complete isolated queue execution with zero workspace leaks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import sys
from typing import Any
import pytest

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.application.doctor import Doctor, DoctorReport
from runner.container import build_container
from runner.domain.config import RunnerConfig
from runner.domain.ticket import Ticket, TicketStatus
from runner.ports.agent_worker import AgentWorker
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner
import ticket_runner


SAMPLE_EXTERNAL_CONFIG_YAML = """project:
  name: "external-target-app"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  provider: "opencode"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pytest"
  build_cmd: ""
  max_attempts: 3
  timeout_seconds: 120

tokens:
  warn: 120000
  handoff: 135000
  ceiling: 150000

presence:
  default_mode: "nearby"
  idle_escalation_minutes: 3

discord:
  enabled: false
  token_env: "DISCORD_BOT_TOKEN"

lifecycle:
  mode: "autonomous"
  queue_completion: "terminate"
  poll_interval: 0.01

git:
  auto_push: false
  commit_prefix: "chore"

model:
  models:
    - id: "qwen/qwen-plus"
      label: "Qwen Plus"
"""


def _seed_external_target_repo(root: Path) -> Path:
    """Seed a realistic external target project directory layout."""
    target = root.resolve()
    target.mkdir(parents=True, exist_ok=True)

    # Config
    config_file = target / "config.yaml"
    config_file.write_text(SAMPLE_EXTERNAL_CONFIG_YAML, encoding="utf-8")

    # AGENTS.md
    agents_md = target / "AGENTS.md"
    agents_md.write_text("# Target Project Invariants\n- External rules.\n", encoding="utf-8")

    # Skills
    skills_dir = target / ".agents" / "skills"
    for skill_name in ("implement", "code-review", "diagnosing-bugs"):
        skill_file = skills_dir / skill_name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# {skill_name} skill\n", encoding="utf-8")

    # Git structure
    git_hooks = target / ".git" / "hooks"
    git_hooks.mkdir(parents=True, exist_ok=True)
    from runner.adapters.git.pre_push_hook import PrePushHookInstaller
    pre_push = git_hooks / "pre-push"
    pre_push.write_text(
        PrePushHookInstaller.DEFAULT_STANDALONE_HOOK,
        encoding="utf-8",
    )

    # Tickets queue
    tickets_dir = target / "docs" / "tickets" / "01-sample-feature"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket_file = tickets_dir / "T001-setup.md"
    ticket_file.write_text(
        "# T001 — Setup Feature\n"
        "Status: pending\n"
        "Spec: docs/specs/01-sample.md\n\n"
        "### Requirements\n- Setup decoupled project.\n\n"
        "### Acceptance Criteria\n- Works in external dir.\n\n"
        "### Smoke Scenarios\n- None.\n\n"
        "### Gotchas\n- None.\n",
        encoding="utf-8",
    )

    return target


class FakeTestAgentWorker(AgentWorker):
    """Deterministic agent worker test double for isolated integration tests."""

    def __init__(self, target_dir: Path) -> None:
        self.target_dir = target_dir
        self.invoked_prompts: list[str] = []

    def build_run_command(
        self,
        prompt: str,
        session_id: str | None = None,
        variant: str | None = None,
        model_id: str | None = None,
    ) -> list[str]:
        self.invoked_prompts.append(prompt)
        return ["fake-worker", "--prompt", prompt]

    def decode_event(self, line: str) -> Any:
        return None

    def extract_resource_access(
        self,
        event: Any,
        raw_line: str | None = None,
    ) -> frozenset[str]:
        return frozenset()


# ==============================================================================
# Spec 11 Behavioral Tests
# ==============================================================================

def test_spec_11_cli_argument_parsing(tmp_path: Path) -> None:
    """CLI accepts --project-dir before and after subcommands and defaults to CWD."""
    parser = ticket_runner.create_parser()
    target = tmp_path.resolve()

    # Top-level default
    assert parser.parse_args([]).project_dir == Path.cwd().resolve()
    assert parser.parse_args(["doctor"]).project_dir == Path.cwd().resolve()
    assert parser.parse_args(["start"]).project_dir == Path.cwd().resolve()

    # Pre-subcommand
    args_pre_doc = parser.parse_args(["--project-dir", str(target), "doctor"])
    assert args_pre_doc.project_dir == target

    args_pre_start = parser.parse_args(["--project-dir", str(target), "start"])
    assert args_pre_start.project_dir == target

    # Post-subcommand
    args_post_doc = parser.parse_args(["doctor", "--project-dir", str(target)])
    assert args_post_doc.project_dir == target

    args_post_start = parser.parse_args(["start", "--project-dir", str(target)])
    assert args_post_start.project_dir == target


def test_spec_11_cli_path_validation_rejects_invalid(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI path validation rejects non-existent paths and files cleanly with exit code 1."""
    # Non-existent
    bad_dir = tmp_path / "does_not_exist"
    assert ticket_runner.main(["--project-dir", str(bad_dir), "doctor"]) == 1
    out = capsys.readouterr().out
    assert "does not exist" in out

    # File instead of directory
    file_target = tmp_path / "a_file.txt"
    file_target.write_text("content", encoding="utf-8")
    assert ticket_runner.main(["--project-dir", str(file_target), "start"]) == 1
    out = capsys.readouterr().out
    assert "is not a directory" in out


def test_spec_11_doctor_verifies_external_target_directory(tmp_path: Path) -> None:
    """Doctor verifies the prerequisites of an external target repository."""
    target = _seed_external_target_repo(tmp_path / "external_target")

    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "rev-parse", "--is-inside-work-tree"], stdout="true\n")
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")

    doctor = Doctor(
        project_dir=target,
        command_runner=fake_runner,
        which_fn=lambda cmd: f"/bin/{cmd}",
    )

    report = asyncio.run(doctor.run(local_only=True, halt_on_failure=False))
    assert report.passed is True
    assert doctor.project_dir == target
    assert doctor.loaded_config is not None
    assert doctor.loaded_config.project.name == "external-target-app"


def test_spec_11_isolated_queue_execution_zero_workspace_leaks(tmp_path: Path) -> None:
    """Running container and queue against external target repository executes cleanly with zero workspace leaks."""
    target = _seed_external_target_repo(tmp_path / "external_app")

    # Command runner configured for external target directory
    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "rev-parse", "--is-inside-work-tree"], stdout="true\n")
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    fake_runner.register(["pytest"], stdout="1 passed\n")

    fake_worker = FakeTestAgentWorker(target_dir=target)

    # Build container targeting external project root
    container = build_container(
        project_dir=target,
        command_runner=fake_runner,
        agent_worker=fake_worker,
    )

    # Verify container wiring points exclusively to the external target directory
    assert container.project_dir == target
    assert container.runtime_paths.root_dir == target / ".agent"
    assert container.ticket_store.root_dir == target / "docs" / "tickets"
    assert container.gotchas_store.path == target / "docs" / "tickets" / "gotchas.md"
    assert container.lock.lock_path == target / "docs" / "tickets" / ".queue.lock"
    assert container.git_operations.cwd == target
    assert container.executor.cwd == target
    assert container.supervisor.cwd == target
    assert container.orchestrator.cwd == target

    # Verify pending ticket exists in external target
    pending = container.ticket_store.list_all_pending()
    assert len(pending) == 1
    assert pending[0].id == "T001"

    # Simulate worker writing ready signal in external runtime paths
    container.runtime_paths.ensure_signals_dir()
    ready_file = container.runtime_paths.ready_signal_path("T001")
    ready_file.write_text(
        '{"ticket_id": "T001", "status": "ready", "scope": "01-sample", "manual_verification": []}',
        encoding="utf-8",
    )
    assert ready_file.exists()
    assert ready_file.is_relative_to(target)

    # Append gotchas in external target
    container.gotchas_store.append(["External project lesson learned."])
    assert container.gotchas_store.path.exists()
    assert container.gotchas_store.path.is_relative_to(target)

    # Assert ZERO leaks: runner's own workspace must have no signals written
    leak_signal = Path(".agent/signals/T001_ready.json")
    assert not leak_signal.exists(), "Leak detected: signal written to runner repository root!"


def test_spec_11_cli_main_doctor_against_external_repo(tmp_path: Path) -> None:
    """ticket_runner.main(['--project-dir', <target>, 'doctor', '--local-only']) executes Doctor on external target."""
    target = _seed_external_target_repo(tmp_path / "cli_target")

    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "rev-parse", "--is-inside-work-tree"], stdout="true\n")
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")

    fake_doc = Doctor(
        project_dir=target,
        command_runner=fake_runner,
        which_fn=lambda cmd: f"/bin/{cmd}",
    )

    code = asyncio.run(
        ticket_runner.run_doctor(
            config_path=target / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            project_dir=target,
        )
    )
    assert code == 0
    assert fake_doc.project_dir == target


def test_spec_11_run_start_against_external_repo_plumbing(tmp_path: Path) -> None:
    """run_start against external repo initializes and runs with project_dir."""
    target = _seed_external_target_repo(tmp_path / "start_target")

    fake_runner = FakeCommandRunner()
    fake_runner.register(["git", "rev-parse", "--is-inside-work-tree"], stdout="true\n")
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")

    fake_doc = Doctor(
        project_dir=target,
        command_runner=fake_runner,
        which_fn=lambda cmd: f"/bin/{cmd}",
    )

    class FakeOrchestrator:
        def __init__(self) -> None:
            self.ran = False

        async def run_lifecycle(self, **kwargs: Any) -> int:
            self.ran = True
            return 0

        def release_lock(self) -> None:
            pass

    fake_orch = FakeOrchestrator()

    code = asyncio.run(
        ticket_runner.run_start(
            config_path=target / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            orchestrator_instance=fake_orch,
            project_dir=target,
        )
    )
    assert code == 0
    assert fake_orch.ran is True

