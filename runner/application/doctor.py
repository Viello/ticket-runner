"""Doctor pre-flight verification coordinator interactor."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Mapping

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.git.pre_push_hook import PrePushHookInstaller
from runner.adapters.markdown.ticket_store import DirectoryTicketStore
from runner.application.git_operations import GitOperations
from runner.domain.config import RunnerConfig
from runner.domain.exceptions import CommandNotFoundError, ConfigError, GitError, TicketFormatError
from runner.ports.command_runner import CommandRunner
from runner.ports.config_loader import ConfigLoader
from runner.ports.ticket_repository import TicketRepository

CHECK_OPENCODE = "opencode"
CHECK_GIT = "git"
CHECK_QUEUE = "queue"
CHECK_CONFIG = "config"
CHECK_HOOK = "pre_push_hook"
CHECK_DISCORD = "discord"

DEFAULT_BRANCH = "agent/ticket-runner"
DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_TICKETS_DIR = Path("docs/tickets")


@dataclass(frozen=True)
class CheckResult:
    """Individual pre-flight check outcome."""

    name: str
    passed: bool
    message: str
    remediation: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    """Consolidated pre-flight verification report."""

    passed: bool
    checks: list[CheckResult]

    @property
    def failed_checks(self) -> list[CheckResult]:
        """List of all failed checks."""
        return [c for c in self.checks if not c.passed]

    @property
    def first_failure(self) -> CheckResult | None:
        """First failed check encountered, if any."""
        failed = self.failed_checks
        return failed[0] if failed else None


class Doctor:
    """Pre-flight verification coordinator inspecting workspace and runtime prerequisites."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        git_operations: GitOperations | None = None,
        config_loader: ConfigLoader | None = None,
        hook_installer: type[PrePushHookInstaller] | None = None,
        ticket_store: TicketRepository | None = None,
        cwd: Path | None = None,
        config_path: Path | str | None = None,
        tickets_dir: Path | str | None = None,
        git_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
        target_branch: str = DEFAULT_BRANCH,
    ) -> None:
        self._cwd = cwd
        self._command_runner = command_runner or SubprocessRunner()
        if git_operations is not None:
            self._git_operations = git_operations
        else:
            self._git_operations = GitOperations(runner=self._command_runner, cwd=self._cwd)

        self._config_loader = config_loader or YamlConfigLoader()
        self._hook_installer = hook_installer or PrePushHookInstaller

        if config_path is not None:
            self._config_path = Path(config_path)
        elif self._cwd:
            self._config_path = self._cwd / DEFAULT_CONFIG_PATH
        else:
            self._config_path = DEFAULT_CONFIG_PATH

        if tickets_dir is not None:
            self._tickets_dir = Path(tickets_dir)
        elif self._cwd:
            self._tickets_dir = self._cwd / DEFAULT_TICKETS_DIR
        else:
            self._tickets_dir = DEFAULT_TICKETS_DIR

        self._ticket_store = ticket_store or DirectoryTicketStore(root_dir=self._tickets_dir)

        if git_dir is not None:
            self._git_dir = Path(git_dir)
        elif self._cwd:
            self._git_dir = self._cwd / ".git"
        else:
            self._git_dir = Path(".git")

        self._env = env if env is not None else os.environ
        self._target_branch = target_branch
        self._loaded_config: RunnerConfig | None = None

    @property
    def loaded_config(self) -> RunnerConfig | None:
        """Loaded RunnerConfig after successful config check."""
        return self._loaded_config

    async def check_opencode(self) -> CheckResult:
        """Verify OpenCode CLI binary is available and executable."""
        try:
            result = await self._command_runner.run(["opencode", "--version"], cwd=self._cwd)
        except CommandNotFoundError:
            return CheckResult(
                name=CHECK_OPENCODE,
                passed=False,
                message="OpenCode CLI binary 'opencode' was not found in PATH.",
                remediation="Install OpenCode CLI and ensure 'opencode' is accessible in your PATH.",
            )
        except OSError as exc:
            return CheckResult(
                name=CHECK_OPENCODE,
                passed=False,
                message=f"Failed to execute 'opencode --version': {exc}",
                remediation="Install OpenCode CLI and verify system permissions.",
            )

        if not result.success:
            err_msg = result.stderr.strip() or result.stdout.strip() or "non-zero exit code"
            return CheckResult(
                name=CHECK_OPENCODE,
                passed=False,
                message=f"OpenCode CLI check failed (exit code {result.exit_code}): {err_msg}",
                remediation="Install OpenCode CLI and ensure 'opencode --version' runs successfully in your PATH.",
            )

        version_str = result.stdout.strip() or "version verified"
        return CheckResult(
            name=CHECK_OPENCODE,
            passed=True,
            message=f"OpenCode CLI available ({version_str}).",
            remediation=None,
        )

    async def check_git(self) -> CheckResult:
        """Verify git working tree cleanliness and checkout on designated isolation branch."""
        try:
            is_clean = await self._git_operations.check_clean_working_tree()
        except GitError as exc:
            return CheckResult(
                name=CHECK_GIT,
                passed=False,
                message=f"Git status check failed: {exc}",
                remediation="Ensure current directory is a valid git repository with commit history.",
            )

        if not is_clean:
            return CheckResult(
                name=CHECK_GIT,
                passed=False,
                message="Working tree has uncommitted modifications or untracked changes.",
                remediation="Commit, stash, or clean uncommitted changes before running tickets.",
            )

        try:
            current_branch = await self._git_operations.get_current_branch()
        except GitError as exc:
            return CheckResult(
                name=CHECK_GIT,
                passed=False,
                message=f"Failed to determine active git branch: {exc}",
                remediation=f"Ensure HEAD is checked out to branch '{self._target_branch}'.",
            )

        if current_branch != self._target_branch:
            return CheckResult(
                name=CHECK_GIT,
                passed=False,
                message=f"Active branch is '{current_branch}', expected '{self._target_branch}'.",
                remediation=f"Switch to the designated isolation branch with 'git checkout {self._target_branch}'.",
            )

        return CheckResult(
            name=CHECK_GIT,
            passed=True,
            message=f"Working tree clean on branch '{self._target_branch}'.",
            remediation=None,
        )

    async def check_queue(self) -> CheckResult:
        """Verify docs/tickets/ contains at least one pending ticket file."""
        if not self._ticket_store.exists():
            return CheckResult(
                name=CHECK_QUEUE,
                passed=False,
                message=f"Tickets directory '{self._tickets_dir}' does not exist.",
                remediation=f"Create '{self._tickets_dir}' and add at least one pending ticket specification.",
            )

        try:
            pending_tickets = self._ticket_store.list_all_pending()
        except TicketFormatError as exc:
            return CheckResult(
                name=CHECK_QUEUE,
                passed=False,
                message=f"Queue validation failed: Malformed ticket: {exc}",
                remediation=f"Fix the malformed ticket file or remove it from '{self._tickets_dir}'.",
            )

        if not pending_tickets:
            return CheckResult(
                name=CHECK_QUEUE,
                passed=False,
                message=f"Queue validation failed: No pending tickets found in '{self._tickets_dir}'.",
                remediation=f"Add at least one pending ticket file with 'Status: pending' to '{self._tickets_dir}/<spec-slug>/'.",
            )

        return CheckResult(
            name=CHECK_QUEUE,
            passed=True,
            message=f"Found {len(pending_tickets)} pending ticket(s) in queue.",
            remediation=None,
        )

    async def check_config(self) -> CheckResult:
        """Load and validate config.yaml using ConfigLoader."""
        try:
            self._loaded_config = self._config_loader.load(self._config_path)
            return CheckResult(
                name=CHECK_CONFIG,
                passed=True,
                message=f"Configuration valid: loaded from '{self._config_path}'.",
                remediation=None,
            )
        except (ConfigError, OSError, Exception) as exc:
            self._loaded_config = None
            remediation = f"Verify that '{self._config_path}' exists and satisfies the RunnerConfig schema."
            if "Configuration file not found" in str(exc):
                remediation = (
                    f"Configuration file '{self._config_path}' not found. "
                    "Copy the template configuration using 'cp config.example.yaml config.yaml' "
                    "(or PowerShell: 'Copy-Item config.example.yaml config.yaml') and customize your settings."
                )
            return CheckResult(
                name=CHECK_CONFIG,
                passed=False,
                message=f"Configuration validation failed: {exc}",
                remediation=remediation,
            )

    async def check_hook(self) -> CheckResult:
        """Verify pre-push hook guardrail is installed and active."""
        if not self._hook_installer.is_installed(git_dir=self._git_dir):
            return CheckResult(
                name=CHECK_HOOK,
                passed=False,
                message="Pre-push hook guardrail is not installed or lacks signature delimiters.",
                remediation="Install the pre-push hook guardrail in '.git/hooks/pre-push' to protect 'agent/ticket-runner'.",
            )

        return CheckResult(
            name=CHECK_HOOK,
            passed=True,
            message="Pre-push hook guardrail is active and verified.",
            remediation=None,
        )

    async def check_discord(self, local_only: bool = False) -> CheckResult:
        """Verify Discord bot credentials unless in local-only mode or discord is disabled."""
        if local_only:
            return CheckResult(
                name=CHECK_DISCORD,
                passed=True,
                message="Discord verification bypassed (--local-only mode).",
                remediation=None,
            )

        if self._loaded_config is not None and not self._loaded_config.discord.enabled:
            return CheckResult(
                name=CHECK_DISCORD,
                passed=True,
                message="Discord verification bypassed (discord.enabled is false in configuration).",
                remediation=None,
            )

        token_env_var = (
            self._loaded_config.discord.token_env
            if self._loaded_config is not None
            else "DISCORD_BOT_TOKEN"
        )
        token_value = self._env.get(token_env_var)

        if not token_value or not token_value.strip():
            return CheckResult(
                name=CHECK_DISCORD,
                passed=False,
                message=f"Discord token environment variable '{token_env_var}' is unset or empty.",
                remediation=f"Set the '{token_env_var}' environment variable with your Discord bot token, or use --local-only.",
            )

        return CheckResult(
            name=CHECK_DISCORD,
            passed=True,
            message=f"Discord token verified from environment variable '{token_env_var}'.",
            remediation=None,
        )

    async def run(self, local_only: bool = False, halt_on_failure: bool = True) -> DoctorReport:
        """Execute pre-flight checks in order, optionally halting on first failure.

        Args:
            local_only: Whether to bypass Discord connectivity checks.
            halt_on_failure: If True, halts execution on the first failing check.

        Returns:
            DoctorReport containing all executed check outcomes.
        """
        check_runners = [
            self.check_opencode,
            self.check_git,
            self.check_queue,
            self.check_config,
            self.check_hook,
            lambda: self.check_discord(local_only=local_only),
        ]

        results: list[CheckResult] = []
        for runner in check_runners:
            res = await runner()
            results.append(res)
            if not res.passed and halt_on_failure:
                break

        overall_passed = all(r.passed for r in results)
        return DoctorReport(passed=overall_passed, checks=results)
