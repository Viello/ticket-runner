"""FakeSkillsClient test double for deterministic in-memory skills synchronization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runner.ports.skills_client import SkillsClient, SkillsSyncError, SkillsSyncResult


@dataclass(frozen=True)
class SkillsSyncInvocation:
    """Record of a skills synchronization invocation."""

    project_dir: Path
    repo: str
    ref: str
    force: bool


class FakeSkillsClient:
    """In-memory test double implementing SkillsClient protocol."""

    def __init__(
        self,
        canned_skills: dict[str, dict[str, str]] | None = None,
        canned_result: SkillsSyncResult | None = None,
        should_raise: Exception | None = None,
    ) -> None:
        self.calls: list[SkillsSyncInvocation] = []
        self.canned_skills = (
            canned_skills
            if canned_skills is not None
            else {
                "implement": {"SKILL.md": "# Implement\nInstructions for implementing tickets."},
                "code-review": {"SKILL.md": "# Code Review\nInstructions for review."},
            }
        )
        self.canned_result = canned_result
        self.should_raise = should_raise

    def sync_skills(
        self,
        project_dir: Path,
        repo: str = "Viello/agent-skills",
        ref: str = "main",
        force: bool = False,
    ) -> SkillsSyncResult:
        """Simulate skills synchronization deterministically in memory."""
        self.calls.append(
            SkillsSyncInvocation(
                project_dir=Path(project_dir),
                repo=repo,
                ref=ref,
                force=force,
            )
        )
        if self.should_raise is not None:
            raise self.should_raise

        if self.canned_result is not None:
            return self.canned_result

        target_project_dir = Path(project_dir)
        skills_dir = target_project_dir / ".agents" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        existing = {d.name for d in skills_dir.iterdir() if d.is_dir()}
        installed: list[str] = []
        updated: list[str] = []
        preserved: list[str] = []

        # Preserved custom skills (not in canned_skills catalog)
        for name in existing:
            if name not in self.canned_skills:
                preserved.append(name)

        for name, files in self.canned_skills.items():
            skill_target = skills_dir / name
            if name not in existing:
                skill_target.mkdir(parents=True, exist_ok=True)
                for fname, fcontent in files.items():
                    fpath = skill_target / fname
                    fpath.parent.mkdir(parents=True, exist_ok=True)
                    fpath.write_text(fcontent, encoding="utf-8")
                installed.append(name)
            else:
                # Check if modified locally
                modified = False
                for fname, fcontent in files.items():
                    fpath = skill_target / fname
                    if not fpath.exists() or fpath.read_text(encoding="utf-8") != fcontent:
                        modified = True
                        break

                if modified and not force:
                    preserved.append(name)
                else:
                    skill_target.mkdir(parents=True, exist_ok=True)
                    for fname, fcontent in files.items():
                        fpath = skill_target / fname
                        fpath.parent.mkdir(parents=True, exist_ok=True)
                        fpath.write_text(fcontent, encoding="utf-8")
                    updated.append(name)

        return SkillsSyncResult(
            installed_skills=tuple(sorted(installed)),
            updated_skills=tuple(sorted(updated)),
            preserved_skills=tuple(sorted(preserved)),
            errors=(),
        )
