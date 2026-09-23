"""SkillsClient port protocol and result value objects."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


class SkillsSyncError(Exception):
    """Raised when skills synchronization fails due to network, extraction, or security errors."""


@dataclass(frozen=True)
class SkillsSyncResult:
    """Outcome of a skills catalog synchronization operation."""

    installed_skills: tuple[str, ...] = ()
    updated_skills: tuple[str, ...] = ()
    preserved_skills: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@runtime_checkable
class SkillsClient(Protocol):
    """Abstract protocol for synchronizing the remote skills catalog into a project."""

    def sync_skills(
        self,
        project_dir: Path,
        repo: str = "Viello/agent-skills",
        ref: str = "main",
        force: bool = False,
    ) -> SkillsSyncResult:
        """Synchronize remote skills catalog into <project_dir>/.agents/skills/.

        Args:
            project_dir: Target project root directory.
            repo: GitHub repository in 'owner/repo' format.
            ref: Git ref (branch name or commit SHA).
            force: Whether to overwrite existing skills that have local modifications.

        Returns:
            SkillsSyncResult summarizing installed, updated, preserved skills and any errors.

        Raises:
            SkillsSyncError: If synchronization fails unrecoverably.
        """
        ...
