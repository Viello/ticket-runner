"""Project scaffolding coordinator and interactive CLI adapter (T104)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from runner.application.scaffolding import ProjectSniffer
from runner.domain.config import VALID_WORKER_PROVIDERS
from runner.domain.scaffolding import ProjectHeuristics, ScaffoldReport
from runner.ports.skills_client import SkillsClient, SkillsSyncResult

__all__ = ["ProjectScaffolder", "ScaffoldReport"]

GOTCHAS_TEMPLATE = """# Global Gotchas & Lessons Learned

A chronological record of runtime quirks, platform pitfalls, and architectural lessons discovered during ticket implementations. Subsequent ticket sessions ingest these lessons to prevent recurring mistakes.
"""

REQUIRED_DIRECTORIES = (
    "docs/specs",
    "docs/tickets",
    ".agent",
    ".agent/archive/completed",
    ".agent/signals",
    ".agent/questions",
    ".agent/checkpoints",
)


def _safe_resolve_target(project_dir: Path, rel_path: str | Path) -> Path:
    """Resolve target path safely within project directory, guarding against path and symlink traversal."""
    resolved_root = project_dir.resolve()
    raw_target = resolved_root / rel_path

    # Prevent writing through or creating onto an existing symlink directly
    if raw_target.is_symlink():
        raise ValueError(f"Security: Target path '{raw_target}' is an unsafe symlink")

    target = raw_target.resolve()
    if not target.is_relative_to(resolved_root):
        raise ValueError(
            f"Security: Target path '{rel_path}' escapes project directory '{project_dir}'"
        )

    # Check target and its parent chain within resolved_root for symlink traversal
    current = target
    while current != resolved_root:
        if current.is_symlink():
            link_target = current.resolve()
            if not link_target.is_relative_to(resolved_root):
                raise ValueError(
                    f"Security: Symlink '{current}' points outside project directory: '{link_target}'"
                )
        current = current.parent

    return target


class ProjectScaffolder:
    """Coordinates directory creation, .gitignore configuration, heuristic detection, and project setup."""

    def __init__(
        self,
        sniffer: ProjectSniffer | None = None,
        skills_client: SkillsClient | None = None,
        console: Console | None = None,
    ) -> None:
        self.sniffer = sniffer if sniffer is not None else ProjectSniffer()
        self._skills_client = skills_client
        self.console = console if console is not None else Console()

    @property
    def skills_client(self) -> SkillsClient:
        """Lazy-load GitHubSkillsClient if not injected."""
        if self._skills_client is None:
            from runner.adapters.skills.skills_client import GitHubSkillsClient

            self._skills_client = GitHubSkillsClient()
        return self._skills_client

    def scaffold(
        self,
        project_dir: Path,
        interactive: bool = True,
        sync_skills: bool = True,
    ) -> ScaffoldReport:
        """Scaffold project directories, .gitignore, ticket-runner.yaml, and optionally sync skills.

        Args:
            project_dir: Target project directory to initialize.
            interactive: Whether to prompt the user with detected defaults.
            sync_skills: Whether to offer/execute skills synchronization.

        Returns:
            ScaffoldReport detailing created paths and actions.

        Raises:
            ValueError: If project_dir is not a directory or security violations are detected.
        """
        target_dir = Path(project_dir)
        if target_dir.exists() and not target_dir.is_dir():
            raise ValueError(f"Project directory must be a directory: '{project_dir}'")

        if target_dir.is_symlink():
            resolved_target = target_dir.resolve()
            if not resolved_target.is_dir():
                raise ValueError(f"Project directory symlink target must be a directory: '{resolved_target}'")

        target_dir.mkdir(parents=True, exist_ok=True)
        resolved_root = target_dir.resolve()

        created_dirs: list[Path] = []
        created_files: list[Path] = []

        # 1. Scaffold directory tree and .gitkeep markers
        for rel_dir in REQUIRED_DIRECTORIES:
            dir_path = _safe_resolve_target(target_dir, rel_dir)
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                created_dirs.append(dir_path)

            gitkeep_path = _safe_resolve_target(target_dir, f"{rel_dir}/.gitkeep")
            if not gitkeep_path.exists():
                gitkeep_path.write_text("", encoding="utf-8")
                created_files.append(gitkeep_path)

        # 2. Initialize docs/tickets/gotchas.md if missing
        gotchas_path = _safe_resolve_target(target_dir, "docs/tickets/gotchas.md")
        if not gotchas_path.exists():
            gotchas_path.write_text(GOTCHAS_TEMPLATE, encoding="utf-8")
            created_files.append(gotchas_path)

        # 3. Ensure .agent/ is ignored in .gitignore without duplicating entries
        gitignore_path = _safe_resolve_target(target_dir, ".gitignore")
        gitignore_updated = False
        if not gitignore_path.exists():
            gitignore_path.write_text(".agent/\n", encoding="utf-8")
            created_files.append(gitignore_path)
            gitignore_updated = True
        else:
            content = gitignore_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.splitlines()]
            if ".agent/" not in lines and ".agent" not in lines:
                prefix = (
                    ""
                    if (not content or content.endswith("\n") or content.endswith("\r\n"))
                    else "\n"
                )
                gitignore_path.write_text(content + prefix + ".agent/\n", encoding="utf-8")
                gitignore_updated = True

        # 4. Detect heuristics
        heuristics: ProjectHeuristics = self.sniffer.sniff(target_dir)

        # 5. Determine settings (interactive prompting vs non-interactive defaults)
        if not interactive:
            name = heuristics.name
            base_branch = heuristics.base_branch
            branch = heuristics.branch
            test_cmd = heuristics.test_cmd
            build_cmd = heuristics.build_cmd
            provider = heuristics.provider
        else:
            self.console.print(
                Panel(
                    f"[bold green]Ticket Runner Scaffolding[/bold green]\n"
                    f"Target: [cyan]{resolved_root}[/cyan]\n"
                    f"Detected Stack: [yellow]{heuristics.detected_stack}[/yellow]",
                    title="Project Setup",
                )
            )
            name = Prompt.ask("Project name", default=heuristics.name, console=self.console)
            base_branch = Prompt.ask("Base branch", default=heuristics.base_branch, console=self.console)
            branch = Prompt.ask("Agent branch", default=heuristics.branch, console=self.console)
            test_cmd = Prompt.ask(
                "Verification test command", default=heuristics.test_cmd, console=self.console
            )
            build_cmd = Prompt.ask(
                "Verification build command (optional)",
                default=heuristics.build_cmd,
                console=self.console,
            )
            provider = Prompt.ask(
                "Worker provider",
                choices=list(sorted(VALID_WORKER_PROVIDERS)),
                default=heuristics.provider,
                console=self.console,
            )
            if sync_skills:
                sync_skills = Confirm.ask(
                    "Synchronize standard skills catalog from GitHub?",
                    default=True,
                    console=self.console,
                )

        # 6. Write ticket-runner.yaml
        config_path = _safe_resolve_target(target_dir, "ticket-runner.yaml")
        config_dict = {
            "project": {
                "name": name,
                "base_branch": base_branch,
                "branch": branch,
            },
            "verification": {
                "test_cmd": test_cmd,
                "build_cmd": build_cmd,
            },
            "worker": {
                "provider": provider,
            },
        }
        yaml_content = (
            "# ticket-runner.yaml\n"
            "# Project overlay configuration for Ticket Runner\n\n"
            + yaml.dump(config_dict, sort_keys=False)
        )
        config_path.write_text(yaml_content, encoding="utf-8")
        if config_path not in created_files:
            created_files.append(config_path)

        # 7. Skills synchronization
        sync_result: SkillsSyncResult | None = None
        if sync_skills:
            sync_result = self.skills_client.sync_skills(project_dir=target_dir)

        return ScaffoldReport(
            project_dir=target_dir,
            created_dirs=tuple(created_dirs),
            created_files=tuple(created_files),
            config_path=config_path,
            gitignore_updated=gitignore_updated,
            skills_sync_result=sync_result,
        )
