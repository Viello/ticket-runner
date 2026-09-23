"""Unit tests for ProjectScaffolder CLI adapter (T104)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch
import pytest
import yaml

from runner.adapters.cli.scaffolder import ProjectScaffolder, ScaffoldReport
from runner.domain.scaffolding import ProjectHeuristics
from tests.fakes.fake_skills_client import FakeSkillsClient


class FakeSniffer:
    """Configurable test double for ProjectSniffer."""

    def __init__(self, heuristics: ProjectHeuristics | None = None) -> None:
        self.heuristics = (
            heuristics
            if heuristics is not None
            else ProjectHeuristics(
                name="test-repo",
                detected_stack="python",
                test_cmd="python -m pytest",
                build_cmd="",
                base_branch="main",
                branch="agent/ticket-runner",
                provider="opencode",
            )
        )

    def sniff(self, project_dir: Path) -> ProjectHeuristics:
        return self.heuristics


def test_non_interactive_scaffolding_creates_complete_directory_tree(tmp_path: Path) -> None:
    fake_skills = FakeSkillsClient()
    fake_sniffer = FakeSniffer()
    scaffolder = ProjectScaffolder(sniffer=fake_sniffer, skills_client=fake_skills)

    report = scaffolder.scaffold(project_dir=tmp_path, interactive=False, sync_skills=False)

    assert isinstance(report, ScaffoldReport)
    assert report.project_dir == tmp_path
    assert report.gitignore_updated is True
    assert report.skills_sync_result is None

    # Required directory markers
    expected_markers = [
        tmp_path / "docs" / "specs" / ".gitkeep",
        tmp_path / "docs" / "tickets" / ".gitkeep",
        tmp_path / "docs" / "tickets" / "gotchas.md",
        tmp_path / ".agent" / ".gitkeep",
        tmp_path / ".agent" / "archive" / "completed" / ".gitkeep",
        tmp_path / ".agent" / "signals" / ".gitkeep",
        tmp_path / ".agent" / "questions" / ".gitkeep",
        tmp_path / ".agent" / "checkpoints" / ".gitkeep",
    ]
    for marker in expected_markers:
        assert marker.is_file(), f"Expected marker missing: {marker}"

    # Verify gotchas template content
    gotchas_content = (tmp_path / "docs" / "tickets" / "gotchas.md").read_text(encoding="utf-8")
    assert "Global Gotchas & Lessons Learned" in gotchas_content

    # Verify .gitignore content
    gitignore_content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".agent/" in gitignore_content.splitlines()

    # Verify generated ticket-runner.yaml
    config_file = tmp_path / "ticket-runner.yaml"
    assert config_file.is_file()
    assert report.config_path == config_file

    config_data = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    assert config_data == {
        "project": {
            "name": "test-repo",
            "base_branch": "main",
            "branch": "agent/ticket-runner",
        },
        "verification": {
            "test_cmd": "python -m pytest",
            "build_cmd": "",
        },
        "worker": {
            "provider": "opencode",
        },
    }


def test_gotchas_file_preserved_if_already_present(tmp_path: Path) -> None:
    gotchas_dir = tmp_path / "docs" / "tickets"
    gotchas_dir.mkdir(parents=True)
    existing_gotchas = gotchas_dir / "gotchas.md"
    existing_gotchas.write_text("# Existing Gotchas\nCustom notes here.", encoding="utf-8")

    scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient())
    report = scaffolder.scaffold(project_dir=tmp_path, interactive=False, sync_skills=False)

    assert existing_gotchas.read_text(encoding="utf-8") == "# Existing Gotchas\nCustom notes here."
    assert existing_gotchas not in report.created_files


def test_gitignore_not_duplicated_when_already_ignoring_agent(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("node_modules/\n.agent/\n*.log\n", encoding="utf-8")

    scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient())
    report = scaffolder.scaffold(project_dir=tmp_path, interactive=False, sync_skills=False)

    assert report.gitignore_updated is False
    content = gitignore.read_text(encoding="utf-8")
    assert content.count(".agent/") == 1


def test_gitignore_appends_cleanly_when_missing_trailing_newline(tmp_path: Path) -> None:
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("build", encoding="utf-8")  # No trailing newline

    scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient())
    report = scaffolder.scaffold(project_dir=tmp_path, interactive=False, sync_skills=False)

    assert report.gitignore_updated is True
    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines == ["build", ".agent/"]


def test_interactive_mode_prompts_and_accepts_overrides(tmp_path: Path) -> None:
    fake_sniffer = FakeSniffer()
    scaffolder = ProjectScaffolder(sniffer=fake_sniffer, skills_client=FakeSkillsClient())

    answers = {
        "Project name": "custom-app",
        "Base branch": "master",
        "Agent branch": "agent/custom",
        "Verification test command": "npm test",
        "Verification build command (optional)": "npm run build",
        "Worker provider": "antigravity",
    }

    def fake_prompt_ask(prompt_msg: str, default: str = "", **kwargs: object) -> str:
        for key, val in answers.items():
            if key in prompt_msg:
                return val
        return default

    with (
        patch("runner.adapters.cli.scaffolder.Prompt.ask", side_effect=fake_prompt_ask),
        patch("runner.adapters.cli.scaffolder.Confirm.ask", return_value=False),
    ):
        report = scaffolder.scaffold(project_dir=tmp_path, interactive=True, sync_skills=True)

    config_data = yaml.safe_load(report.config_path.read_text(encoding="utf-8"))
    assert config_data == {
        "project": {
            "name": "custom-app",
            "base_branch": "master",
            "branch": "agent/custom",
        },
        "verification": {
            "test_cmd": "npm test",
            "build_cmd": "npm run build",
        },
        "worker": {
            "provider": "antigravity",
        },
    }
    assert report.skills_sync_result is None


def test_interactive_mode_accepts_defaults(tmp_path: Path) -> None:
    fake_sniffer = FakeSniffer()
    scaffolder = ProjectScaffolder(sniffer=fake_sniffer, skills_client=FakeSkillsClient())

    def fake_prompt_ask(prompt_msg: str, default: str = "", **kwargs: object) -> str:
        return default

    with (
        patch("runner.adapters.cli.scaffolder.Prompt.ask", side_effect=fake_prompt_ask),
        patch("runner.adapters.cli.scaffolder.Confirm.ask", return_value=False),
    ):
        report = scaffolder.scaffold(project_dir=tmp_path, interactive=True, sync_skills=True)

    config_data = yaml.safe_load(report.config_path.read_text(encoding="utf-8"))
    assert config_data["project"]["name"] == "test-repo"
    assert config_data["verification"]["test_cmd"] == "python -m pytest"
    assert config_data["worker"]["provider"] == "opencode"


def test_skills_sync_triggered_when_requested(tmp_path: Path) -> None:
    fake_skills = FakeSkillsClient()
    scaffolder = ProjectScaffolder(skills_client=fake_skills)

    report = scaffolder.scaffold(project_dir=tmp_path, interactive=False, sync_skills=True)

    assert len(fake_skills.calls) == 1
    assert fake_skills.calls[0].project_dir == tmp_path
    assert report.skills_sync_result is not None
    assert "implement" in report.skills_sync_result.installed_skills
    assert (tmp_path / ".agents" / "skills" / "implement" / "SKILL.md").is_file()


def test_skills_sync_skipped_when_sync_skills_false(tmp_path: Path) -> None:
    fake_skills = FakeSkillsClient()
    scaffolder = ProjectScaffolder(skills_client=fake_skills)

    report = scaffolder.scaffold(project_dir=tmp_path, interactive=False, sync_skills=False)

    assert len(fake_skills.calls) == 0
    assert report.skills_sync_result is None


def test_security_rejects_regular_file_as_project_dir(tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("hello", encoding="utf-8")

    scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient())
    with pytest.raises(ValueError, match="Project directory must be a directory"):
        scaffolder.scaffold(project_dir=file_path, interactive=False, sync_skills=False)


def test_security_rejects_symlink_traversal_outside_root(tmp_path: Path) -> None:
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    # Create symlink pointing outside project directory
    docs_link = project_dir / "docs"
    try:
        docs_link.symlink_to(outside_dir, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation not permitted in this host environment")

    scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient())
    with pytest.raises(ValueError, match="Security:.*escapes project directory|Security: Symlink.*points outside"):
        scaffolder.scaffold(project_dir=project_dir, interactive=False, sync_skills=False)


def test_security_rejects_existing_symlink_config_file(tmp_path: Path) -> None:
    outside_file = tmp_path / "outside.yaml"
    outside_file.write_text("outside", encoding="utf-8")

    project_dir = tmp_path / "project"
    project_dir.mkdir()

    config_link = project_dir / "ticket-runner.yaml"
    try:
        config_link.symlink_to(outside_file)
    except OSError:
        pytest.skip("Symlink creation not permitted in this host environment")

    scaffolder = ProjectScaffolder(skills_client=FakeSkillsClient())
    with pytest.raises(ValueError, match="Security: Target path '.*' is an unsafe symlink"):
        scaffolder.scaffold(project_dir=project_dir, interactive=False, sync_skills=False)
