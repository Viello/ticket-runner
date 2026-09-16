"""Spec 01 Behavioral Test Suite: Doctor Pre-Flight and Git Operations.

Validates all 12 User Stories from docs/specs/01-doctor-and-git-ops.md:
  US 01: OpenCode CLI verification
  US 02: Working tree cleanliness inspection on startup
  US 03: Ticket queue validation (pending tickets exist)
  US 04: Configuration validation against required schema
  US 05: Pre-push hook guardrail inspection & installation
  US 06: Discord bot credentials verification on startup
  US 07: Local-only flag bypasses Discord connectivity checks
  US 08: Dedicated branch isolation ('agent/ticket-runner')
  US 09: Authoritative conventional commit authoring
  US 10: Commit SHA extraction and recording
  US 11: Pristine working tree reset on skipped tickets
  US 12: Actionable terminal remediation and non-zero exit without mutations
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.git.git_client import GitClient
from runner.adapters.git.pre_push_hook import PrePushHookInstaller
from runner.application.doctor import (
    CHECK_CONFIG,
    CHECK_DISCORD,
    CHECK_GIT,
    CHECK_HOOK,
    CHECK_OPENCODE,
    CHECK_QUEUE,
    Doctor,
)
from runner.application.git_operations import GitOperations
from runner.domain.exceptions import CommandNotFoundError, GitError
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner
import ticket_runner

SAMPLE_VALID_CONFIG_YAML = """
project:
  name: "ticket-runner-test"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "pytest"
  build_cmd: ""
  max_attempts: 3
  timeout_seconds: 300

tokens:
  warn: 120000
  handoff: 135000
  ceiling: 150000

presence:
  default_mode: "nearby"
  idle_escalation_minutes: 3

discord:
  enabled: true
  token_env: "DISCORD_BOT_TOKEN"
  channel_id: "123456789"

lifecycle:
  queue_completion: "standby"
  clean_slate: "interactive"

git:
  auto_push: false
  commit_prefix: "feat"
  enforce_pre_push_hook: true
""".strip()


def setup_workspace_environment(
    tmp_path: Path,
    with_pending_ticket: bool = True,
    with_valid_config: bool = True,
    with_hook: bool = True,
) -> tuple[Path, Path, Path, Path]:
    """Helper to scaffold a complete, isolated workspace environment."""
    # 1. Git hooks
    git_dir = tmp_path / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    if with_hook:
        PrePushHookInstaller.install(git_dir=git_dir)

    # 2. Tickets queue
    tickets_dir = tmp_path / "docs" / "tickets"
    spec_dir = tickets_dir / "01-spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    if with_pending_ticket:
        pending_file = spec_dir / "T001-test.md"
        pending_file.write_text("# T001\nStatus: pending\n", encoding="utf-8")

    # 3. Config
    config_path = tmp_path / "config.yaml"
    if with_valid_config:
        config_path.write_text(SAMPLE_VALID_CONFIG_YAML, encoding="utf-8")

    return tmp_path, git_dir, tickets_dir, config_path


def make_passing_command_runner() -> FakeCommandRunner:
    """Create a FakeCommandRunner scripted for a clean git repo on agent/ticket-runner."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=0, stdout="opencode 1.0.0\n")
    runner.register("git status --porcelain", exit_code=0, stdout="")
    runner.register("git symbolic-ref --short HEAD", exit_code=0, stdout="agent/ticket-runner\n")
    return runner


# ==============================================================================
# USER STORY 01: OpenCode CLI Verification
# ==============================================================================
@pytest.mark.anyio
async def test_us01_opencode_cli_verification_success(tmp_path: Path) -> None:
    """US1: Doctor verifies OpenCode CLI is installed and executable before starting."""
    runner = make_passing_command_runner()
    doctor = Doctor(command_runner=runner, cwd=tmp_path)

    result = await doctor.check_opencode()
    assert result.passed is True
    assert result.name == CHECK_OPENCODE
    assert "1.0.0" in result.message


@pytest.mark.anyio
async def test_us01_opencode_cli_verification_missing_binary(tmp_path: Path) -> None:
    """US1: Doctor halts immediately with diagnostic remediation if OpenCode binary is missing."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=127, stderr="opencode: command not found")
    doctor = Doctor(command_runner=runner, cwd=tmp_path)

    result = await doctor.check_opencode()
    assert result.passed is False
    assert result.name == CHECK_OPENCODE
    assert "127" in result.message
    assert result.remediation is not None
    assert "Install OpenCode CLI" in result.remediation


# ==============================================================================
# USER STORY 02: Working Tree Cleanliness Inspection
# ==============================================================================
@pytest.mark.anyio
async def test_us02_git_cleanliness_fails_when_uncommitted_changes_exist(tmp_path: Path) -> None:
    """US2: Doctor inspects git status on startup and fails if uncommitted changes exist."""
    runner = FakeCommandRunner()
    runner.register("git status --porcelain", exit_code=0, stdout=" M src/app.py\n?? untracked.txt\n")
    runner.register("git symbolic-ref --short HEAD", exit_code=0, stdout="agent/ticket-runner\n")

    doctor = Doctor(command_runner=runner, cwd=tmp_path)
    result = await doctor.check_git()

    assert result.passed is False
    assert result.name == CHECK_GIT
    assert "uncommitted" in result.message.lower()
    assert result.remediation is not None
    assert "Commit, stash, or clean" in result.remediation


@pytest.mark.anyio
async def test_us02_git_cleanliness_passes_when_pristine(tmp_path: Path) -> None:
    """US2: Doctor passes when working tree has zero uncommitted changes."""
    runner = make_passing_command_runner()
    doctor = Doctor(command_runner=runner, cwd=tmp_path)

    result = await doctor.check_git()
    assert result.passed is True
    assert result.name == CHECK_GIT


# ==============================================================================
# USER STORY 03: Ticket Queue Validation
# ==============================================================================
@pytest.mark.anyio
async def test_us03_queue_validation_fails_when_zero_pending_tickets(tmp_path: Path) -> None:
    """US3: Doctor verifies docs/tickets/ contains at least one pending ticket file."""
    _, _, tickets_dir, _ = setup_workspace_environment(tmp_path, with_pending_ticket=False)
    doctor = Doctor(tickets_dir=tickets_dir)

    result = await doctor.check_queue()
    assert result.passed is False
    assert result.name == CHECK_QUEUE
    assert "No pending tickets found" in result.message
    assert result.remediation is not None


@pytest.mark.anyio
async def test_us03_queue_validation_passes_with_pending_tickets(tmp_path: Path) -> None:
    """US3: Doctor succeeds when pending tickets exist in queue hierarchy."""
    _, _, tickets_dir, _ = setup_workspace_environment(tmp_path, with_pending_ticket=True)
    doctor = Doctor(tickets_dir=tickets_dir)

    result = await doctor.check_queue()
    assert result.passed is True
    assert result.name == CHECK_QUEUE
    assert "1 pending ticket(s)" in result.message


# ==============================================================================
# USER STORY 04: Configuration Schema Validation
# ==============================================================================
@pytest.mark.anyio
async def test_us04_config_validation_fails_on_missing_or_invalid_schema(tmp_path: Path) -> None:
    """US4: Doctor validates config.yaml against schema before launching, failing fast on invalid config."""
    bad_config = tmp_path / "config.yaml"
    bad_config.write_text("project: {}\n# Missing mandatory sections", encoding="utf-8")

    doctor = Doctor(config_loader=YamlConfigLoader(), config_path=bad_config)
    result = await doctor.check_config()

    assert result.passed is False
    assert result.name == CHECK_CONFIG
    assert "validation failed" in result.message.lower()
    assert result.remediation is not None


@pytest.mark.anyio
async def test_us04_config_validation_succeeds_on_valid_yaml(tmp_path: Path) -> None:
    """US4: Doctor validates valid config.yaml successfully."""
    _, _, _, config_path = setup_workspace_environment(tmp_path, with_valid_config=True)

    doctor = Doctor(config_loader=YamlConfigLoader(), config_path=config_path)
    result = await doctor.check_config()

    assert result.passed is True
    assert result.name == CHECK_CONFIG
    assert doctor.loaded_config is not None
    assert doctor.loaded_config.project.name == "ticket-runner-test"


# ==============================================================================
# USER STORY 05: Pre-Push Hook Guardrail Verification
# ==============================================================================
@pytest.mark.anyio
async def test_us05_pre_push_hook_verification_and_installation(tmp_path: Path) -> None:
    """US5: Doctor inspects .git/hooks/pre-push and verifies the blocking guardrail is installed."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir(parents=True)
    doctor = Doctor(git_dir=git_dir)

    # Initial check fails: hook missing
    missing_result = await doctor.check_hook()
    assert missing_result.passed is False
    assert missing_result.name == CHECK_HOOK
    assert missing_result.remediation is not None

    # Install hook via PrePushHookInstaller
    installed = PrePushHookInstaller.install(git_dir=git_dir)
    assert installed is True
    assert PrePushHookInstaller.is_installed(git_dir=git_dir) is True

    # Check passes after installation
    active_result = await doctor.check_hook()
    assert active_result.passed is True
    assert active_result.name == CHECK_HOOK


# ==============================================================================
# USER STORY 06: Discord Bot Credentials Verification
# ==============================================================================
@pytest.mark.anyio
async def test_us06_discord_credentials_verification_missing(tmp_path: Path) -> None:
    """US6: Doctor verifies Discord bot credentials on startup unless --local-only is specified."""
    _, _, _, config_path = setup_workspace_environment(tmp_path, with_valid_config=True)
    doctor = Doctor(config_path=config_path, env={})
    # Run config check first to load config
    await doctor.check_config()

    result = await doctor.check_discord(local_only=False)
    assert result.passed is False
    assert result.name == CHECK_DISCORD
    assert "DISCORD_BOT_TOKEN" in result.message
    assert result.remediation is not None


@pytest.mark.anyio
async def test_us06_discord_credentials_verification_present(tmp_path: Path) -> None:
    """US6: Doctor passes when token environment variable is set and non-empty."""
    _, _, _, config_path = setup_workspace_environment(tmp_path, with_valid_config=True)
    doctor = Doctor(
        config_path=config_path,
        env={"DISCORD_BOT_TOKEN": "bot-secret-token"},
    )
    await doctor.check_config()

    result = await doctor.check_discord(local_only=False)
    assert result.passed is True
    assert result.name == CHECK_DISCORD


# ==============================================================================
# USER STORY 07: Local-Only Flag Bypasses Discord Checks
# ==============================================================================
@pytest.mark.anyio
async def test_us07_local_only_flag_bypasses_discord(tmp_path: Path) -> None:
    """US7: Doctor supports --local-only flag to bypass Discord credentials checks."""
    _, _, _, config_path = setup_workspace_environment(tmp_path, with_valid_config=True)
    # Token is completely absent
    doctor = Doctor(config_path=config_path, env={})
    await doctor.check_config()

    result = await doctor.check_discord(local_only=True)
    assert result.passed is True
    assert result.name == CHECK_DISCORD
    assert "bypassed" in result.message.lower()


# ==============================================================================
# USER STORY 08: Dedicated Branch Isolation Enforcement
# ==============================================================================
@pytest.mark.anyio
async def test_us08_branch_isolation_doctor_check_fails_on_wrong_branch(tmp_path: Path) -> None:
    """US8: Doctor fails immediately if active branch is not agent/ticket-runner."""
    runner = FakeCommandRunner()
    runner.register("git status --porcelain", exit_code=0, stdout="")
    runner.register("git symbolic-ref --short HEAD", exit_code=0, stdout="main\n")

    doctor = Doctor(command_runner=runner, cwd=tmp_path)
    result = await doctor.check_git()

    assert result.passed is False
    assert result.name == CHECK_GIT
    assert "main" in result.message
    assert "agent/ticket-runner" in result.message


@pytest.mark.anyio
async def test_us08_ensure_branch_switches_or_creates_isolation_branch() -> None:
    """US8: GitOperations automatically switches to or creates agent/ticket-runner."""
    runner = FakeCommandRunner()
    runner.register("git status --porcelain", exit_code=0, stdout="")
    runner.register("git symbolic-ref --short HEAD", exit_code=0, stdout="main\n")
    runner.register("git checkout agent/ticket-runner", exit_code=0, stdout="Switched to branch\n")

    git_ops = GitOperations(runner=runner)
    await git_ops.ensure_branch("agent/ticket-runner")

    assert ["git", "checkout", "agent/ticket-runner"] in runner.commands


# ==============================================================================
# USER STORY 09: Authoritative Conventional Commit Formatting
# ==============================================================================
@pytest.mark.anyio
async def test_us09_authoritative_conventional_commits_formatting() -> None:
    """US9: Runner authors conventional commits without ticket numbers in title/scope."""
    runner = FakeCommandRunner()
    runner.register("git add .", exit_code=0)
    runner.register(
        "git commit -m feat(doctor): Implement pre-flight coordinator\n\n- Add Doctor interactor\n- Add CLI entry point",
        exit_code=0,
    )
    runner.register("git rev-parse HEAD", exit_code=0, stdout="a" * 40 + "\n")

    git_ops = GitOperations(runner=runner)
    sha = await git_ops.commit_ticket(
        scope="doctor",
        title="T005 — Implement pre-flight coordinator.",
        changes=["- Add Doctor interactor.", "- Add CLI entry point."],
        commit_prefix="feat",
    )

    assert len(sha) == 40
    # Confirm commit message has no ticket numbers
    commit_calls = [inv for inv in runner.invocations if inv.cmd[:2] == ["git", "commit"]]
    assert len(commit_calls) == 1
    msg = commit_calls[0].cmd[3]
    assert "T005" not in msg
    assert msg.startswith("feat(doctor): Implement pre-flight coordinator\n\n- Add Doctor interactor\n- Add CLI entry point")


# ==============================================================================
# USER STORY 10: Commit SHA Extraction
# ==============================================================================
@pytest.mark.anyio
async def test_us10_commit_sha_extracted_from_head() -> None:
    """US10: Commit SHA is extracted from git rev-parse HEAD upon commit."""
    runner = FakeCommandRunner()
    runner.register("git add .", exit_code=0)
    expected_sha = "0123456789abcdef0123456789abcdef01234567"
    runner.register("git rev-parse HEAD", exit_code=0, stdout=f"{expected_sha}\n")

    git_ops = GitOperations(runner=runner)
    sha = await git_ops.commit_ticket(
        scope="ports",
        title="Define command runner port",
        changes=["Add command runner protocol"],
    )

    assert sha == expected_sha


# ==============================================================================
# USER STORY 11: Working Tree Clean Reset on Skipped Tickets
# ==============================================================================
@pytest.mark.anyio
async def test_us11_working_tree_clean_reset_on_skip() -> None:
    """US11: Runner executes git reset --hard HEAD and git clean -fd when tickets are skipped."""
    runner = FakeCommandRunner()
    runner.register("git reset --hard HEAD", exit_code=0, stdout="HEAD is now at ...\n")
    runner.register("git clean -fd", exit_code=0, stdout="Removing untracked/\n")

    git_ops = GitOperations(runner=runner)
    await git_ops.reset_working_tree()

    assert ["git", "reset", "--hard", "HEAD"] in runner.commands
    assert ["git", "clean", "-fd"] in runner.commands


# ==============================================================================
# USER STORY 12: Actionable Remediation Messages & Non-Zero CLI Exit
# ==============================================================================
@pytest.mark.anyio
async def test_us12_doctor_remediation_messages_and_cli_exit(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """US12: Doctor failure displays clear diagnostic remediation messages and exits non-zero."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=1, stderr="Not found")

    doctor = Doctor(command_runner=runner, cwd=tmp_path)
    exit_code = await ticket_runner.run_doctor(
        config_path=tmp_path / "config.yaml",
        local_only=True,
        doctor_instance=doctor,
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Doctor pre-flight verification failed." in captured.out
    assert "Remediation:" in captured.out
    assert "Install OpenCode CLI" in captured.out


# ==============================================================================
# COMPREHENSIVE INTEGRATION & ACCEPTANCE CRITERIA
# ==============================================================================
@pytest.mark.anyio
async def test_doctor_all_prerequisites_satisfied_succeeds(tmp_path: Path) -> None:
    """Acceptance Criteria: Doctor succeeds when all prerequisites are satisfied."""
    _, git_dir, tickets_dir, config_path = setup_workspace_environment(tmp_path)

    runner = make_passing_command_runner()
    doctor = Doctor(
        command_runner=runner,
        cwd=tmp_path,
        config_path=config_path,
        tickets_dir=tickets_dir,
        git_dir=git_dir,
        env={"DISCORD_BOT_TOKEN": "valid_token"},
    )

    report = await doctor.run(local_only=False, halt_on_failure=True)
    assert report.passed is True
    assert len(report.checks) == 6
    assert all(c.passed for c in report.checks)


@pytest.mark.anyio
async def test_doctor_is_strictly_read_only_and_non_destructive(tmp_path: Path) -> None:
    """Gotcha: Doctor is strictly read-only and never auto-stashes, commits, or modifies files on failure."""
    # Write a dirty file
    dirty_file = tmp_path / "dirty.txt"
    dirty_file.write_text("Uncommitted work\n", encoding="utf-8")

    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=0, stdout="opencode 1.0.0\n")
    runner.register("git status --porcelain", exit_code=0, stdout=" M dirty.txt\n")
    runner.register("git symbolic-ref --short HEAD", exit_code=0, stdout="agent/ticket-runner\n")

    doctor = Doctor(command_runner=runner, cwd=tmp_path)
    report = await doctor.run(halt_on_failure=True)

    assert report.passed is False
    # Verify file content is identical and untouched
    assert dirty_file.read_text(encoding="utf-8") == "Uncommitted work\n"
    # Verify no mutating commands were called (no git stash, commit, reset, clean)
    for cmd in runner.commands:
        assert "stash" not in cmd
        assert "commit" not in cmd
        assert "reset" not in cmd
        assert "clean" not in cmd
