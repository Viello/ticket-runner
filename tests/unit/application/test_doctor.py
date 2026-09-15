"""Unit tests for the Doctor pre-flight verification coordinator."""

from __future__ import annotations

from pathlib import Path
import pytest

from runner.application.doctor import (
    CHECK_CONFIG,
    CHECK_DISCORD,
    CHECK_GIT,
    CHECK_HOOK,
    CHECK_OPENCODE,
    CHECK_QUEUE,
    CheckResult,
    Doctor,
    DoctorReport,
)
from runner.domain.exceptions import CommandNotFoundError, ConfigError, GitError
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner


class FakeGitOperations:
    """In-memory double for GitOperations."""

    def __init__(
        self,
        clean: bool = True,
        branch: str = "agent/ticket-runner",
        raise_status_error: bool = False,
        raise_branch_error: bool = False,
    ) -> None:
        self.clean = clean
        self.branch = branch
        self.raise_status_error = raise_status_error
        self.raise_branch_error = raise_branch_error

    async def check_clean_working_tree(self) -> bool:
        if self.raise_status_error:
            raise GitError("fatal: not a git repository")
        return self.clean

    async def get_current_branch(self) -> str:
        if self.raise_branch_error:
            raise GitError("fatal: ref HEAD is not a symbolic ref")
        return self.branch


class FakeConfigLoader:
    """In-memory double for ConfigLoader."""

    def __init__(self, config=None, error: Exception | None = None) -> None:
        self.config = config
        self.error = error

    def load(self, path: Path | str):
        if self.error:
            raise self.error
        return self.config


class FakeHookInstaller:
    """In-memory double for PrePushHookInstaller."""

    installed: bool = True

    @classmethod
    def is_installed(cls, git_dir: Path | None = None) -> bool:
        return cls.installed


def test_doctor_report_helpers() -> None:
    """Verify DoctorReport properties."""
    c1 = CheckResult(name="c1", passed=True, message="ok")
    c2 = CheckResult(name="c2", passed=False, message="failed", remediation="fix it")
    c3 = CheckResult(name="c3", passed=True, message="ok")

    report = DoctorReport(passed=False, checks=[c1, c2, c3])
    assert report.passed is False
    assert report.failed_checks == [c2]
    assert report.first_failure == c2

    passing_report = DoctorReport(passed=True, checks=[c1, c3])
    assert passing_report.passed is True
    assert passing_report.failed_checks == []
    assert passing_report.first_failure is None


@pytest.mark.anyio
async def test_check_opencode_success() -> None:
    """Verify check_opencode passes when opencode --version returns 0."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=0, stdout="opencode 0.4.1\n")

    doctor = Doctor(command_runner=runner)
    result = await doctor.check_opencode()

    assert result.passed is True
    assert result.name == CHECK_OPENCODE
    assert "0.4.1" in result.message
    assert result.remediation is None


@pytest.mark.anyio
async def test_check_opencode_nonzero_exit() -> None:
    """Verify check_opencode fails when binary exits non-zero."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=127, stderr="not executable")

    doctor = Doctor(command_runner=runner)
    result = await doctor.check_opencode()

    assert result.passed is False
    assert result.name == CHECK_OPENCODE
    assert "127" in result.message
    assert result.remediation is not None
    assert "Install OpenCode CLI" in result.remediation


@pytest.mark.anyio
async def test_check_opencode_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify check_opencode fails when binary cannot be invoked."""
    runner = FakeCommandRunner()

    async def raise_not_found(*args, **kwargs):
        raise CommandNotFoundError("opencode")

    monkeypatch.setattr(runner, "run", raise_not_found)

    doctor = Doctor(command_runner=runner)
    result = await doctor.check_opencode()

    assert result.passed is False
    assert result.name == CHECK_OPENCODE
    assert "not found" in result.message.lower()
    assert result.remediation is not None


@pytest.mark.anyio
async def test_check_git_clean_and_correct_branch() -> None:
    """Verify check_git passes when tree is clean on agent/ticket-runner."""
    git_ops = FakeGitOperations(clean=True, branch="agent/ticket-runner")
    doctor = Doctor(git_operations=git_ops)

    result = await doctor.check_git()
    assert result.passed is True
    assert result.name == CHECK_GIT
    assert "agent/ticket-runner" in result.message
    assert result.remediation is None


@pytest.mark.anyio
async def test_check_git_dirty_working_tree() -> None:
    """Verify check_git fails when working tree has uncommitted changes."""
    git_ops = FakeGitOperations(clean=False, branch="agent/ticket-runner")
    doctor = Doctor(git_operations=git_ops)

    result = await doctor.check_git()
    assert result.passed is False
    assert result.name == CHECK_GIT
    assert "uncommitted" in result.message.lower()
    assert result.remediation is not None


@pytest.mark.anyio
async def test_check_git_wrong_branch() -> None:
    """Verify check_git fails when current branch is not agent/ticket-runner."""
    git_ops = FakeGitOperations(clean=True, branch="main")
    doctor = Doctor(git_operations=git_ops)

    result = await doctor.check_git()
    assert result.passed is False
    assert result.name == CHECK_GIT
    assert "main" in result.message
    assert "agent/ticket-runner" in result.message
    assert result.remediation is not None


@pytest.mark.anyio
async def test_check_git_error() -> None:
    """Verify check_git handles GitError exceptions gracefully."""
    git_ops = FakeGitOperations(raise_status_error=True)
    doctor = Doctor(git_operations=git_ops)

    result = await doctor.check_git()
    assert result.passed is False
    assert result.name == CHECK_GIT
    assert "git status check failed" in result.message.lower()


@pytest.mark.anyio
async def test_check_queue_with_pending_tickets(tmp_path: Path) -> None:
    """Verify check_queue passes when pending ticket exists."""
    tickets_dir = tmp_path / "docs" / "tickets"
    spec_dir = tickets_dir / "01-spec"
    spec_dir.mkdir(parents=True)
    ticket_file = spec_dir / "T001-sample.md"
    ticket_file.write_text("# T001\nStatus: pending\n", encoding="utf-8")

    doctor = Doctor(tickets_dir=tickets_dir)
    result = await doctor.check_queue()

    assert result.passed is True
    assert result.name == CHECK_QUEUE
    assert "1 pending ticket(s)" in result.message


@pytest.mark.anyio
async def test_check_queue_missing_directory(tmp_path: Path) -> None:
    """Verify check_queue fails if tickets directory does not exist."""
    missing_dir = tmp_path / "does_not_exist"
    doctor = Doctor(tickets_dir=missing_dir)

    result = await doctor.check_queue()
    assert result.passed is False
    assert result.name == CHECK_QUEUE
    assert "does not exist" in result.message


@pytest.mark.anyio
async def test_check_queue_no_pending_tickets(tmp_path: Path) -> None:
    """Verify check_queue fails if directory has zero pending tickets."""
    tickets_dir = tmp_path / "docs" / "tickets"
    completed_dir = tickets_dir / "01-spec" / "completed"
    completed_dir.mkdir(parents=True)
    (completed_dir / "T001.md").write_text("Status: completed\n", encoding="utf-8")
    (tickets_dir / "gotchas.md").write_text("# Gotchas\n", encoding="utf-8")

    doctor = Doctor(tickets_dir=tickets_dir)
    result = await doctor.check_queue()

    assert result.passed is False
    assert result.name == CHECK_QUEUE
    assert "No pending tickets found" in result.message
    assert result.remediation is not None


@pytest.mark.anyio
async def test_check_config_success(tmp_path: Path) -> None:
    """Verify check_config passes with valid configuration."""
    from runner.adapters.config.yaml_config_loader import YamlConfigLoader

    config_file = tmp_path / "config.yaml"
    valid_yaml = (
        "project:\n  name: test\n  branch: agent/ticket-runner\n  base_branch: main\n"
        "worker:\n  execution_skill: .agents/skills/implement/SKILL.md\n"
        "verification:\n  test_cmd: pytest\n"
        "tokens:\n  warn: 120000\n  handoff: 135000\n  ceiling: 150000\n"
        "presence:\n  default_mode: nearby\n"
        "discord:\n  token_env: DISCORD_BOT_TOKEN\n"
        "lifecycle:\n  queue_completion: standby\n"
        "git:\n  commit_prefix: feat\n"
    )
    config_file.write_text(valid_yaml, encoding="utf-8")

    doctor = Doctor(config_loader=YamlConfigLoader(), config_path=config_file)
    result = await doctor.check_config()

    assert result.passed is True
    assert result.name == CHECK_CONFIG
    assert doctor.loaded_config is not None


@pytest.mark.anyio
async def test_check_config_failure(tmp_path: Path) -> None:
    """Verify check_config fails when configuration is invalid."""
    config_file = tmp_path / "bad_config.yaml"
    config_file.write_text("invalid: yaml: [", encoding="utf-8")

    doctor = Doctor(config_path=config_file)
    result = await doctor.check_config()

    assert result.passed is False
    assert result.name == CHECK_CONFIG
    assert result.remediation is not None
    assert doctor.loaded_config is None


@pytest.mark.anyio
async def test_check_config_missing_file_remediation(tmp_path: Path) -> None:
    """Verify check_config provides explicit copy template remediation when file is missing."""
    doctor = Doctor(config_path=tmp_path / "non_existent_config.yaml")
    result = await doctor.check_config()

    assert result.passed is False
    assert result.name == CHECK_CONFIG
    assert "Copy the template configuration using 'cp config.example.yaml config.yaml'" in (result.remediation or "")


@pytest.mark.anyio
async def test_check_hook_installed() -> None:
    """Verify check_hook passes when hook is installed."""
    class InstalledHook(FakeHookInstaller):
        installed = True

    doctor = Doctor(hook_installer=InstalledHook)
    result = await doctor.check_hook()

    assert result.passed is True
    assert result.name == CHECK_HOOK


@pytest.mark.anyio
async def test_check_hook_missing() -> None:
    """Verify check_hook fails when hook is not installed."""
    class MissingHook(FakeHookInstaller):
        installed = False

    doctor = Doctor(hook_installer=MissingHook)
    result = await doctor.check_hook()

    assert result.passed is False
    assert result.name == CHECK_HOOK
    assert result.remediation is not None


@pytest.mark.anyio
async def test_check_discord_local_only() -> None:
    """Verify check_discord passes when local_only=True without credentials."""
    doctor = Doctor(env={})
    result = await doctor.check_discord(local_only=True)

    assert result.passed is True
    assert result.name == CHECK_DISCORD
    assert "local-only" in result.message.lower()


@pytest.mark.anyio
async def test_check_discord_enabled_with_valid_token() -> None:
    """Verify check_discord passes when env var is present and non-empty."""
    doctor = Doctor(env={"DISCORD_BOT_TOKEN": "my-secret-token"})
    result = await doctor.check_discord(local_only=False)

    assert result.passed is True
    assert result.name == CHECK_DISCORD
    assert "verified" in result.message.lower()


@pytest.mark.anyio
async def test_check_discord_enabled_missing_token() -> None:
    """Verify check_discord fails when token env var is missing."""
    doctor = Doctor(env={})
    result = await doctor.check_discord(local_only=False)

    assert result.passed is False
    assert result.name == CHECK_DISCORD
    assert "unset or empty" in result.message.lower()
    assert result.remediation is not None


@pytest.mark.anyio
async def test_run_halts_on_first_failure(tmp_path: Path) -> None:
    """Verify run() halts on the first failed check when halt_on_failure=True."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=1, stderr="OpenCode missing")

    git_ops = FakeGitOperations(clean=True)
    doctor = Doctor(command_runner=runner, git_operations=git_ops)

    report = await doctor.run(halt_on_failure=True)

    assert report.passed is False
    # Stopped after the first check (opencode)
    assert len(report.checks) == 1
    assert report.checks[0].name == CHECK_OPENCODE


@pytest.mark.anyio
async def test_run_executes_all_when_halt_disabled(tmp_path: Path) -> None:
    """Verify run() executes all checks when halt_on_failure=False."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=1, stderr="OpenCode missing")

    git_ops = FakeGitOperations(clean=True)
    doctor = Doctor(
        command_runner=runner,
        git_operations=git_ops,
        tickets_dir=tmp_path / "empty_dir",
        config_path=tmp_path / "missing_config.yaml",
        env={},
    )

    report = await doctor.run(local_only=False, halt_on_failure=False)

    assert report.passed is False
    # All 6 checks executed
    assert len(report.checks) == 6
