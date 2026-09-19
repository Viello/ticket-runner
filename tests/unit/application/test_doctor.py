"""Unit tests for the Doctor pre-flight verification coordinator."""

from __future__ import annotations

from pathlib import Path
import pytest

from runner.application.doctor import (
    CHECK_AGENTS_MD,
    CHECK_CONFIG,
    CHECK_DISCORD,
    CHECK_GIT,
    CHECK_HOOK,
    CHECK_MODEL,
    CHECK_OPENCODE,
    CHECK_QUEUE,
    CHECK_SKILLS,
    CHECK_TERMINAL_HOST,
    CHECK_VERIFICATION_COMMANDS,
    CANDIDATE_TERMINAL_HOSTS,
    CheckResult,
    Doctor,
    DoctorReport,
)
from runner.adapters.ui.terminal_prompts import TerminalHostPrompt
from runner.domain.config import RunnerConfig, UIConfig
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
        self.persisted_terminals: list[tuple[Path | str, str]] = []

    def load(self, path: Path | str):
        if self.error:
            raise self.error
        return self.config

    def persist_session_terminal(self, path: Path | str, session_terminal: str) -> None:
        self.persisted_terminals.append((path, session_terminal))
        if self.config is not None:
            import dataclasses

            new_ui = dataclasses.replace(self.config.ui, session_terminal=session_terminal)
            self.config = dataclasses.replace(self.config, ui=new_ui)


class FakeHookInstaller:
    """In-memory double for PrePushHookInstaller."""

    installed: bool = True

    @classmethod
    def is_installed(cls, git_dir: Path | None = None) -> bool:
        return cls.installed


def _make_config(
    test_cmd: str = "python -m pytest",
    build_cmd: str = "",
    execution_skill: str = ".agents/skills/implement/SKILL.md",
    model: ModelConfig | None = None,
    ui: UIConfig | None = None,
) -> RunnerConfig:
    """Construct a minimal valid RunnerConfig with scripted verification commands."""
    from runner.domain.config import (
        DiscordConfig,
        GitConfig,
        LifecycleConfig,
        ModelConfig,
        ModelEntry,
        PresenceConfig,
        ProjectConfig,
        TokenBudgetConfig,
        UIConfig,
        VerificationConfig,
        WorkerConfig,
    )

    if model is None:
        model = ModelConfig(
            models=(ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),),
            default_reasoning="",
        )

    if ui is None:
        ui = UIConfig(session_terminal="powershell.exe")

    return RunnerConfig(
        project=ProjectConfig(name="test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=execution_skill),
        verification=VerificationConfig(test_cmd=test_cmd, build_cmd=build_cmd),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(),
        git=GitConfig(),
        model=model,
        ui=ui,
    )



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
async def test_check_verification_commands_passes_when_resolvable() -> None:
    """Doctor passes when configured verification commands resolve on PATH."""
    doctor = Doctor(
        config_loader=FakeConfigLoader(config=_make_config(test_cmd="python -m pytest")),
        path_resolver=lambda token: rf"C:\tools\{token}.exe",
    )
    await doctor.check_config()

    result = await doctor.check_verification_commands()
    assert result.passed is True
    assert result.name == CHECK_VERIFICATION_COMMANDS
    assert result.remediation is None


@pytest.mark.anyio
async def test_check_verification_commands_fails_with_remediation() -> None:
    """Doctor fails with an actionable remediation when the leading token is unresolvable."""
    doctor = Doctor(
        config_loader=FakeConfigLoader(config=_make_config(test_cmd="pytest -q")),
        path_resolver=lambda token: None,
    )
    await doctor.check_config()

    result = await doctor.check_verification_commands()
    assert result.passed is False
    assert result.name == CHECK_VERIFICATION_COMMANDS
    assert "test_cmd" in result.message
    assert "pytest" in result.message
    assert "python -m pytest" in (result.remediation or "")


@pytest.mark.anyio
async def test_check_verification_commands_checks_build_cmd_too() -> None:
    """Doctor flags an unresolvable non-empty build_cmd as well as test_cmd."""
    doctor = Doctor(
        config_loader=FakeConfigLoader(config=_make_config(build_cmd="npm run build")),
        path_resolver=lambda token: None if token == "npm" else rf"C:\tools\{token}.exe",
    )
    await doctor.check_config()

    result = await doctor.check_verification_commands()
    assert result.passed is False
    assert "build_cmd" in result.message
    assert "npm" in result.message


@pytest.mark.anyio
async def test_check_verification_commands_skipped_without_config() -> None:
    """Doctor skips verification command resolution when configuration is not loaded."""
    doctor = Doctor(path_resolver=lambda token: None)
    result = await doctor.check_verification_commands()

    assert result.passed is True
    assert result.name == CHECK_VERIFICATION_COMMANDS
    assert "skipped" in result.message.lower()


@pytest.mark.anyio
async def test_check_model_passes_when_models_configured() -> None:
    """Doctor check_model passes when at least one model is configured."""
    from runner.domain.config import ModelConfig, ModelEntry

    config = _make_config(
        model=ModelConfig(
            models=(
                ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),
                ModelEntry(id="qwen/qwen-plus", label="Qwen Plus"),
            )
        )
    )
    doctor = Doctor(config_loader=FakeConfigLoader(config=config))
    await doctor.check_config()

    result = await doctor.check_model()
    assert result.passed is True
    assert result.name == CHECK_MODEL
    assert result.remediation is None
    assert "2 model(s)" in result.message


@pytest.mark.anyio
async def test_check_model_fails_when_models_empty() -> None:
    """Doctor check_model fails when models list is empty, naming model.models in message and remediation."""
    from runner.domain.config import ModelConfig

    config = _make_config(model=ModelConfig(models=()))
    doctor = Doctor(config_loader=FakeConfigLoader(config=config))
    await doctor.check_config()

    result = await doctor.check_model()
    assert result.passed is False
    assert result.name == CHECK_MODEL
    assert "model.models" in result.message
    assert result.remediation is not None
    assert "model:" in result.remediation
    assert "models:" in result.remediation
    assert "default_reasoning:" in result.remediation


@pytest.mark.anyio
async def test_check_model_skipped_without_config() -> None:
    """Doctor check_model skips gracefully when configuration is not loaded."""
    doctor = Doctor()
    result = await doctor.check_model()
    assert result.passed is True
    assert result.name == CHECK_MODEL
    assert "skipped" in result.message.lower()


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
    # All 11 checks executed
    assert len(report.checks) == 11



@pytest.mark.anyio
async def test_check_queue_with_injected_fake_repository() -> None:
    """Verify check_queue succeeds with an injected FakeTicketRepository."""
    from runner.domain.ticket import Ticket, TicketStatus
    from tests.fakes.fake_ticket_repository import FakeTicketRepository

    fake_repo = FakeTicketRepository(
        tickets=[
            Ticket(
                id="T001",
                title="Test Ticket",
                status=TicketStatus.PENDING,
                spec_path="docs/specs/01-spec.md",
                requirements=("Req 1",),
                acceptance_criteria=(),
                gotchas=(),
                path=Path("docs/tickets/01-spec/T001.md"),
            )
        ]
    )

    doctor = Doctor(ticket_store=fake_repo)
    result = await doctor.check_queue()

    assert result.passed is True
    assert result.name == CHECK_QUEUE
    assert "1 pending ticket(s)" in result.message


@pytest.mark.anyio
async def test_check_queue_with_injected_fake_repository_empty() -> None:
    """Verify check_queue fails when injected FakeTicketRepository has no pending tickets."""
    from tests.fakes.fake_ticket_repository import FakeTicketRepository

    fake_repo = FakeTicketRepository(tickets=[])
    doctor = Doctor(ticket_store=fake_repo)
    result = await doctor.check_queue()

    assert result.passed is False
    assert result.name == CHECK_QUEUE
    assert "No pending tickets found" in result.message


@pytest.mark.anyio
async def test_check_queue_with_injected_fake_repository_missing() -> None:
    """Verify check_queue fails when injected FakeTicketRepository exists() is False."""
    from tests.fakes.fake_ticket_repository import FakeTicketRepository

    fake_repo = FakeTicketRepository(exists_val=False)
    doctor = Doctor(ticket_store=fake_repo)
    result = await doctor.check_queue()

    assert result.passed is False
    assert result.name == CHECK_QUEUE
    assert "does not exist" in result.message


@pytest.mark.anyio
async def test_check_queue_handles_ticket_format_error() -> None:
    """Verify check_queue handles TicketFormatError gracefully with diagnostic remediation."""
    from runner.domain.exceptions import TicketFormatError
    from tests.fakes.fake_ticket_repository import FakeTicketRepository

    fake_repo = FakeTicketRepository(
        error=TicketFormatError("Malformed ticket header in 'docs/tickets/01-spec/T001.md'")
    )
    doctor = Doctor(ticket_store=fake_repo)
    result = await doctor.check_queue()

    assert result.passed is False
    assert result.name == CHECK_QUEUE
    assert "Malformed ticket" in result.message
    assert result.remediation is not None


@pytest.mark.anyio
async def test_check_agents_md_passes_when_present(tmp_path: Path) -> None:
    """Verify check_agents_md passes when AGENTS.md exists and is readable."""
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text("# AGENTS.md\n## Invariants\n- Test\n", encoding="utf-8")

    doctor = Doctor(cwd=tmp_path)
    result = await doctor.check_agents_md()

    assert result.passed is True
    assert result.name == CHECK_AGENTS_MD
    assert "AGENTS.md" in result.message
    assert result.remediation is None


@pytest.mark.anyio
async def test_check_agents_md_fails_when_missing(tmp_path: Path) -> None:
    """Verify check_agents_md fails with actionable remediation when AGENTS.md is missing."""
    doctor = Doctor(cwd=tmp_path)
    result = await doctor.check_agents_md()

    assert result.passed is False
    assert result.name == CHECK_AGENTS_MD
    assert "AGENTS.md" in result.message
    assert result.remediation is not None
    assert "AGENTS.md" in result.remediation


@pytest.mark.anyio
async def test_check_agents_md_custom_path(tmp_path: Path) -> None:
    """Verify check_agents_md respects injected agents_md_path override."""
    custom_file = tmp_path / "custom_agents.md"
    custom_file.write_text("# Rules\n", encoding="utf-8")

    doctor = Doctor(agents_md_path=custom_file)
    result = await doctor.check_agents_md()

    assert result.passed is True
    assert result.name == CHECK_AGENTS_MD


@pytest.mark.anyio
async def test_check_skills_passes_when_all_skills_present(tmp_path: Path) -> None:
    """Verify check_skills passes when execution skill and required review skills exist."""
    skills_dir = tmp_path / ".agents" / "skills"
    for name in ("implement", "code-review", "diagnosing-bugs"):
        skill_file = skills_dir / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# Skill {name}\n", encoding="utf-8")

    doctor = Doctor(cwd=tmp_path)
    result = await doctor.check_skills()

    assert result.passed is True
    assert result.name == CHECK_SKILLS
    assert "required skill files verified" in result.message
    assert result.remediation is None


@pytest.mark.anyio
async def test_check_skills_fails_when_all_skills_missing(tmp_path: Path) -> None:
    """Verify check_skills fails naming all missing skills when none exist."""
    doctor = Doctor(cwd=tmp_path)
    result = await doctor.check_skills()

    assert result.passed is False
    assert result.name == CHECK_SKILLS
    assert result.remediation is not None
    assert ".agents/skills/implement/SKILL.md" in result.remediation
    assert ".agents/skills/code-review/SKILL.md" in result.remediation
    assert ".agents/skills/diagnosing-bugs/SKILL.md" in result.remediation


@pytest.mark.anyio
async def test_check_skills_fails_naming_specifically_missing_skills(tmp_path: Path) -> None:
    """Verify check_skills failure specifically names only the absent skill files."""
    skills_dir = tmp_path / ".agents" / "skills"
    # Create implement and code-review, but omit diagnosing-bugs
    for name in ("implement", "code-review"):
        skill_file = skills_dir / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# Skill {name}\n", encoding="utf-8")

    doctor = Doctor(cwd=tmp_path)
    result = await doctor.check_skills()

    assert result.passed is False
    assert result.name == CHECK_SKILLS
    assert result.remediation is not None
    assert "diagnosing-bugs/SKILL.md" in result.remediation
    assert "code-review/SKILL.md" not in result.remediation
    assert "implement/SKILL.md" not in result.remediation


@pytest.mark.anyio
async def test_check_skills_respects_custom_configured_execution_skill(tmp_path: Path) -> None:
    """Verify check_skills checks custom configured worker.execution_skill."""
    skills_dir = tmp_path / ".agents" / "skills"
    for name in ("code-review", "diagnosing-bugs"):
        skill_file = skills_dir / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# Skill {name}\n", encoding="utf-8")

    custom_skill = "custom/skills/special-execution.md"
    config = _make_config(execution_skill=custom_skill)

    doctor = Doctor(cwd=tmp_path, config_loader=FakeConfigLoader(config=config))
    await doctor.check_config()

    result = await doctor.check_skills()
    assert result.passed is False
    assert result.name == CHECK_SKILLS
    assert result.remediation is not None
    assert custom_skill in result.remediation
    assert "code-review" not in result.remediation
    assert "diagnosing-bugs" not in result.remediation


@pytest.mark.anyio
async def test_doctor_run_includes_agents_md_and_skills_checks(tmp_path: Path) -> None:
    """Verify Doctor.run() includes both CHECK_AGENTS_MD and CHECK_SKILLS in report."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=0, stdout="opencode 1.0\n")
    git_ops = FakeGitOperations(clean=True, branch="agent/ticket-runner")

    tickets_dir = tmp_path / "docs" / "tickets" / "01-spec"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "T001.md").write_text("# T001\nStatus: pending\n", encoding="utf-8")

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    for name in ("implement", "code-review", "diagnosing-bugs"):
        skill_file = skills_dir / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# Skill {name}\n", encoding="utf-8")

    config = _make_config()

    doctor = Doctor(
        command_runner=runner,
        git_operations=git_ops,
        cwd=tmp_path,
        tickets_dir=tmp_path / "docs" / "tickets",
        config_loader=FakeConfigLoader(config=config),
        hook_installer=FakeHookInstaller,
    )

    report = await doctor.run(local_only=True, halt_on_failure=False)
    check_names = [c.name for c in report.checks]
    assert CHECK_AGENTS_MD in check_names
    assert CHECK_SKILLS in check_names


@pytest.mark.anyio
async def test_doctor_run_order_includes_model_after_config(tmp_path: Path) -> None:
    """Verify Doctor.run() includes CHECK_MODEL immediately after CHECK_CONFIG."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=0, stdout="opencode 1.0\n")
    git_ops = FakeGitOperations(clean=True, branch="agent/ticket-runner")

    tickets_dir = tmp_path / "docs" / "tickets" / "01-spec"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "T001.md").write_text("# T001\nStatus: pending\n", encoding="utf-8")

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    for name in ("implement", "code-review", "diagnosing-bugs"):
        skill_file = skills_dir / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# Skill {name}\n", encoding="utf-8")

    config = _make_config()

    doctor = Doctor(
        command_runner=runner,
        git_operations=git_ops,
        cwd=tmp_path,
        tickets_dir=tmp_path / "docs" / "tickets",
        config_loader=FakeConfigLoader(config=config),
        hook_installer=FakeHookInstaller,
    )

    report = await doctor.run(local_only=True, halt_on_failure=False)
    check_names = [c.name for c in report.checks]
    assert CHECK_MODEL in check_names
    config_idx = check_names.index(CHECK_CONFIG)
    model_idx = check_names.index(CHECK_MODEL)
    assert model_idx == config_idx + 1


@pytest.mark.anyio
async def test_doctor_run_order_includes_terminal_host_after_model(tmp_path: Path) -> None:
    """Verify Doctor.run() includes CHECK_TERMINAL_HOST immediately after CHECK_MODEL."""
    runner = FakeCommandRunner()
    runner.register("opencode --version", exit_code=0, stdout="opencode 1.0\n")
    git_ops = FakeGitOperations(clean=True, branch="agent/ticket-runner")

    tickets_dir = tmp_path / "docs" / "tickets" / "01-spec"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / "T001.md").write_text("# T001\nStatus: pending\n", encoding="utf-8")

    (tmp_path / "AGENTS.md").write_text("# AGENTS.md\n", encoding="utf-8")

    skills_dir = tmp_path / ".agents" / "skills"
    for name in ("implement", "code-review", "diagnosing-bugs"):
        skill_file = skills_dir / name / "SKILL.md"
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text(f"# Skill {name}\n", encoding="utf-8")

    config = _make_config()

    doctor = Doctor(
        command_runner=runner,
        git_operations=git_ops,
        cwd=tmp_path,
        tickets_dir=tmp_path / "docs" / "tickets",
        config_loader=FakeConfigLoader(config=config),
        hook_installer=FakeHookInstaller,
    )

    report = await doctor.run(local_only=True, halt_on_failure=False)
    check_names = [c.name for c in report.checks]
    assert CHECK_TERMINAL_HOST in check_names
    model_idx = check_names.index(CHECK_MODEL)
    terminal_idx = check_names.index(CHECK_TERMINAL_HOST)
    assert terminal_idx == model_idx + 1


@pytest.mark.anyio
async def test_check_terminal_host_skipped_without_config() -> None:
    """Doctor skips terminal host check when configuration is not loaded."""
    doctor = Doctor()
    result = await doctor.check_terminal_host()

    assert result.passed is True
    assert result.name == CHECK_TERMINAL_HOST
    assert "skipped" in result.message.lower()


@pytest.mark.anyio
async def test_check_terminal_host_passes_when_configured_binary_found() -> None:
    """Doctor passes when ui.session_terminal is set and discoverable on PATH."""
    config = _make_config(ui=UIConfig(session_terminal="wt.exe"))
    doctor = Doctor(
        config_loader=FakeConfigLoader(config=config),
        path_resolver=lambda name: r"C:\Users\AppData\Local\Microsoft\WindowsApps\wt.exe" if name == "wt.exe" else None,
    )
    await doctor.check_config()

    result = await doctor.check_terminal_host()
    assert result.passed is True
    assert result.name == CHECK_TERMINAL_HOST
    assert "wt.exe" in result.message
    assert result.remediation is None


@pytest.mark.anyio
async def test_check_terminal_host_fails_when_configured_binary_missing() -> None:
    """Doctor fails with actionable remediation when configured binary is not on PATH."""
    config = _make_config(ui=UIConfig(session_terminal="custom_term.exe"))
    doctor = Doctor(
        config_loader=FakeConfigLoader(config=config),
        path_resolver=lambda name: None,
    )
    await doctor.check_config()

    result = await doctor.check_terminal_host()
    assert result.passed is False
    assert result.name == CHECK_TERMINAL_HOST
    assert "custom_term.exe" in result.message
    assert result.remediation is not None
    assert "custom_term.exe" in result.remediation


@pytest.mark.anyio
async def test_check_terminal_host_fails_when_no_supported_hosts_detected() -> None:
    """Doctor fails when ui.session_terminal is empty and no candidate host exists."""
    config = _make_config(ui=UIConfig(session_terminal=""))
    doctor = Doctor(
        config_loader=FakeConfigLoader(config=config),
        path_resolver=lambda name: None,
    )
    await doctor.check_config()

    result = await doctor.check_terminal_host()
    assert result.passed is False
    assert result.name == CHECK_TERMINAL_HOST
    assert "No supported terminal host detected" in result.message
    assert result.remediation is not None
    assert "wt.exe" in result.remediation


@pytest.mark.anyio
async def test_check_terminal_host_auto_selects_single_detected_host() -> None:
    """Doctor auto-selects without prompting when exactly one host is detected."""
    config = _make_config(ui=UIConfig(session_terminal=""))
    config_loader = FakeConfigLoader(config=config)
    output_lines: list[str] = []

    prompt = TerminalHostPrompt(output_fn=output_lines.append, is_interactive=lambda: True)
    doctor = Doctor(
        config_loader=config_loader,
        path_resolver=lambda name: r"C:\Windows\System32\cmd.exe" if name == "cmd.exe" else None,
        terminal_prompt=prompt,
    )
    await doctor.check_config()

    result = await doctor.check_terminal_host()
    assert result.passed is True
    assert result.name == CHECK_TERMINAL_HOST
    assert "cmd.exe" in result.message
    assert output_lines == []  # No prompt shown for single detected host
    assert config_loader.persisted_terminals == [(doctor._config_path, "cmd.exe")]
    assert doctor.loaded_config.ui.session_terminal == "cmd.exe"


@pytest.mark.anyio
async def test_check_terminal_host_interactive_menu_selection() -> None:
    """Doctor presents interactive numbered menu when multiple hosts detected in interactive mode."""
    config = _make_config(ui=UIConfig(session_terminal=""))
    config_loader = FakeConfigLoader(config=config)
    output_lines: list[str] = []

    # Available hosts: wt.exe, powershell.exe, cmd.exe
    # User selects option 2 ("powershell.exe") and confirms with Enter
    keys = ["2", "\r"]
    key_iter = iter(keys)

    prompt = TerminalHostPrompt(
        read_key=lambda: next(key_iter),
        output_fn=output_lines.append,
        is_interactive=lambda: True,
    )

    doctor = Doctor(
        config_loader=config_loader,
        path_resolver=lambda name: rf"C:\tools\{name}" if name in ("wt.exe", "powershell.exe", "cmd.exe") else None,
        terminal_prompt=prompt,
    )
    await doctor.check_config()

    result = await doctor.check_terminal_host()
    assert result.passed is True
    assert "powershell.exe" in result.message
    assert len(output_lines) == 1
    assert "Select terminal host for interactive sessions:" in output_lines[0]
    assert config_loader.persisted_terminals == [(doctor._config_path, "powershell.exe")]
    assert doctor.loaded_config.ui.session_terminal == "powershell.exe"


@pytest.mark.anyio
async def test_check_terminal_host_non_interactive_fallback_highest_priority() -> None:
    """Doctor auto-selects highest-priority detected host in non-interactive environment."""
    config = _make_config(ui=UIConfig(session_terminal=""))
    config_loader = FakeConfigLoader(config=config)
    output_lines: list[str] = []

    # Available hosts: pwsh.exe, cmd.exe (highest priority is pwsh.exe)
    prompt = TerminalHostPrompt(
        output_fn=output_lines.append,
        is_interactive=lambda: False,
    )

    doctor = Doctor(
        config_loader=config_loader,
        path_resolver=lambda name: rf"C:\tools\{name}" if name in ("pwsh.exe", "cmd.exe") else None,
        terminal_prompt=prompt,
    )
    await doctor.check_config()

    result = await doctor.check_terminal_host()
    assert result.passed is True
    assert "pwsh.exe" in result.message
    assert output_lines == []  # Silently auto-selected
    assert config_loader.persisted_terminals == [(doctor._config_path, "pwsh.exe")]
    assert doctor.loaded_config.ui.session_terminal == "pwsh.exe"


