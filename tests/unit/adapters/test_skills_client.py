"""Unit tests for GitHubSkillsClient and FakeSkillsClient."""

from __future__ import annotations

import io
from pathlib import Path
import tarfile
import urllib.error
import pytest

from runner.adapters.skills.skills_client import GitHubSkillsClient
from runner.ports.command_runner import CommandResult
from runner.ports.skills_client import SkillsClient, SkillsSyncError, SkillsSyncResult
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_skills_client import FakeSkillsClient


def _create_mock_tarball(
    files: dict[str, str],
    prefix: str = "agent-skills-main/",
) -> bytes:
    """Helper to create an in-memory tar.gz archive with specified files and prefix."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name, content in files.items():
            full_name = f"{prefix}{name}"
            data = content.encode("utf-8")
            ti = tarfile.TarInfo(name=full_name)
            ti.size = len(data)
            ti.mtime = 1700000000
            ti.mode = 0o644
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


class TestSkillsClientProtocolConformance:
    def test_github_skills_client_satisfies_protocol(self) -> None:
        client = GitHubSkillsClient()
        assert isinstance(client, SkillsClient)

    def test_fake_skills_client_satisfies_protocol(self) -> None:
        fake = FakeSkillsClient()
        assert isinstance(fake, SkillsClient)


class TestGitHubSkillsClientExtraction:
    def test_sync_skills_success_extracts_into_agents_skills(self, tmp_path: Path) -> None:
        tar_bytes = _create_mock_tarball({
            "README.md": "# Agent Skills Catalog",
            "LICENSE": "MIT License",
            "implement/SKILL.md": "# Implement Skill\nDiscipline.",
            "code-review/SKILL.md": "# Code Review Skill\nDiscipline.",
            "implement/references/ref.md": "Reference content",
        })

        client = GitHubSkillsClient(download_fn=lambda url: tar_bytes)
        result = client.sync_skills(project_dir=tmp_path)

        assert isinstance(result, SkillsSyncResult)
        assert result.installed_skills == ("code-review", "implement")
        assert result.updated_skills == ()
        assert result.preserved_skills == ()
        assert result.errors == ()

        skills_dir = tmp_path / ".agents" / "skills"
        assert (skills_dir / "implement" / "SKILL.md").read_text(encoding="utf-8") == "# Implement Skill\nDiscipline."
        assert (skills_dir / "implement" / "references" / "ref.md").read_text(encoding="utf-8") == "Reference content"
        assert (skills_dir / "code-review" / "SKILL.md").exists()
        # Top-level non-skill files like README.md should not be extracted as skills
        assert not (skills_dir / "README.md").exists()

    def test_preserve_custom_project_skills(self, tmp_path: Path) -> None:
        custom_dir = tmp_path / ".agents" / "skills" / "my-custom-tool"
        custom_dir.mkdir(parents=True)
        (custom_dir / "SKILL.md").write_text("# Custom Tool", encoding="utf-8")
        (custom_dir / "notes.txt").write_text("Custom notes", encoding="utf-8")

        tar_bytes = _create_mock_tarball({
            "implement/SKILL.md": "# Implement Skill",
        })

        client = GitHubSkillsClient(download_fn=lambda url: tar_bytes)
        result = client.sync_skills(project_dir=tmp_path)

        assert "my-custom-tool" in result.preserved_skills
        assert "implement" in result.installed_skills
        assert (custom_dir / "SKILL.md").read_text(encoding="utf-8") == "# Custom Tool"
        assert (custom_dir / "notes.txt").read_text(encoding="utf-8") == "Custom notes"

    def test_preserve_modified_existing_skill_when_force_false(self, tmp_path: Path) -> None:
        impl_dir = tmp_path / ".agents" / "skills" / "implement"
        impl_dir.mkdir(parents=True)
        local_content = "# Implement Skill with local modifications"
        (impl_dir / "SKILL.md").write_text(local_content, encoding="utf-8")

        tar_bytes = _create_mock_tarball({
            "implement/SKILL.md": "# Remote Implement Skill",
            "code-review/SKILL.md": "# Remote Code Review",
        })

        client = GitHubSkillsClient(download_fn=lambda url: tar_bytes)
        result = client.sync_skills(project_dir=tmp_path, force=False)

        assert "implement" in result.preserved_skills
        assert "code-review" in result.installed_skills
        assert "implement" not in result.updated_skills
        # Local content preserved
        assert (impl_dir / "SKILL.md").read_text(encoding="utf-8") == local_content

    def test_overwrite_modified_existing_skill_when_force_true(self, tmp_path: Path) -> None:
        impl_dir = tmp_path / ".agents" / "skills" / "implement"
        impl_dir.mkdir(parents=True)
        (impl_dir / "SKILL.md").write_text("# Old local version", encoding="utf-8")

        tar_bytes = _create_mock_tarball({
            "implement/SKILL.md": "# Remote Implement Skill",
        })

        client = GitHubSkillsClient(download_fn=lambda url: tar_bytes)
        result = client.sync_skills(project_dir=tmp_path, force=True)

        assert "implement" in result.updated_skills
        assert "implement" not in result.preserved_skills
        # Overwritten with remote content
        assert (impl_dir / "SKILL.md").read_text(encoding="utf-8") == "# Remote Implement Skill"

    def test_unmodified_existing_skill_is_updated_cleanly(self, tmp_path: Path) -> None:
        impl_dir = tmp_path / ".agents" / "skills" / "implement"
        impl_dir.mkdir(parents=True)
        (impl_dir / "SKILL.md").write_text("# Identical Skill Content", encoding="utf-8")

        tar_bytes = _create_mock_tarball({
            "implement/SKILL.md": "# Identical Skill Content",
        })

        client = GitHubSkillsClient(download_fn=lambda url: tar_bytes)
        result = client.sync_skills(project_dir=tmp_path, force=False)

        assert "implement" in result.updated_skills
        assert result.preserved_skills == ()


class TestGitHubSkillsClientSecurityZipSlip:
    def test_reject_zip_slip_with_parent_traversal(self, tmp_path: Path) -> None:
        # Malicious archive containing a member attempting to escape
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            data = b"malicious content"
            ti = tarfile.TarInfo(name="agent-skills-main/../../evil.txt")
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))

        client = GitHubSkillsClient(download_fn=lambda url: buf.getvalue())

        with pytest.raises(SkillsSyncError, match="Path traversal detected|Zip Slip detected"):
            client.sync_skills(project_dir=tmp_path)

        # Ensure no evil.txt was written anywhere
        assert not (tmp_path / "evil.txt").exists()
        assert not (tmp_path.parent / "evil.txt").exists()

    def test_reject_absolute_path_member(self, tmp_path: Path) -> None:
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            data = b"malicious content"
            ti = tarfile.TarInfo(name="/etc/cron.d/evil")
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))

        client = GitHubSkillsClient(download_fn=lambda url: buf.getvalue())

        with pytest.raises(SkillsSyncError, match="Path traversal detected|absolute path"):
            client.sync_skills(project_dir=tmp_path)


class TestGitHubSkillsClientFallbackAndErrors:
    def test_http_failure_triggers_git_clone_fallback(self, tmp_path: Path) -> None:
        def failing_download(url: str) -> bytes:
            raise urllib.error.URLError("Connection refused")

        cmd_runner = FakeCommandRunner()

        # When git clone is executed, create a simulated clone directory
        async def fake_run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> CommandResult:
            if cmd and cmd[0] == "git" and cmd[1] == "clone":
                target_clone = Path(cmd[-1])
                target_clone.mkdir(parents=True, exist_ok=True)
                skill_dir = target_clone / "implement"
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text("# Cloned Implement", encoding="utf-8")
                return CommandResult(exit_code=0, stdout="Cloning into...", stderr="")
            return CommandResult(exit_code=0, stdout="", stderr="")

        cmd_runner.run = fake_run  # type: ignore[assignment]

        client = GitHubSkillsClient(
            command_runner=cmd_runner,
            download_fn=failing_download,
        )

        result = client.sync_skills(project_dir=tmp_path)

        assert "implement" in result.installed_skills
        assert (tmp_path / ".agents" / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8") == "# Cloned Implement"

    def test_http_and_git_clone_both_fail_raises_skills_sync_error(self, tmp_path: Path) -> None:
        def failing_download(url: str) -> bytes:
            raise urllib.error.URLError("Network unreachable")

        cmd_runner = FakeCommandRunner(
            default_result=CommandResult(exit_code=128, stdout="", stderr="fatal: repository not found")
        )

        client = GitHubSkillsClient(
            command_runner=cmd_runner,
            download_fn=failing_download,
        )

        with pytest.raises(SkillsSyncError, match="Failed to sync skills"):
            client.sync_skills(project_dir=tmp_path)

    def test_invalid_project_dir_raises_skills_sync_error(self, tmp_path: Path) -> None:
        client = GitHubSkillsClient()
        non_existent = tmp_path / "does_not_exist"

        with pytest.raises(SkillsSyncError, match="does not exist"):
            client.sync_skills(project_dir=non_existent)

    def test_invalid_repo_name_raises_skills_sync_error(self, tmp_path: Path) -> None:
        client = GitHubSkillsClient()

        with pytest.raises(SkillsSyncError, match="Invalid repository"):
            client.sync_skills(project_dir=tmp_path, repo="bad;repo/injection")


class TestFakeSkillsClient:
    def test_fake_skills_client_installs_and_records(self, tmp_path: Path) -> None:
        fake = FakeSkillsClient(
            canned_skills={
                "implement": {"SKILL.md": "# Fake Implement"},
                "to-tickets": {"SKILL.md": "# Fake To Tickets"},
            }
        )

        res = fake.sync_skills(project_dir=tmp_path)

        assert res.installed_skills == ("implement", "to-tickets")
        assert len(fake.calls) == 1
        assert fake.calls[0].project_dir == tmp_path

        skills_dir = tmp_path / ".agents" / "skills"
        assert (skills_dir / "implement" / "SKILL.md").read_text(encoding="utf-8") == "# Fake Implement"

    def test_fake_skills_client_preserves_custom_and_respects_force(self, tmp_path: Path) -> None:
        fake = FakeSkillsClient(
            canned_skills={"implement": {"SKILL.md": "# Standard Implement"}}
        )

        custom = tmp_path / ".agents" / "skills" / "my-tool"
        custom.mkdir(parents=True)
        (custom / "SKILL.md").write_text("# My Tool", encoding="utf-8")

        res = fake.sync_skills(project_dir=tmp_path)
        assert "my-tool" in res.preserved_skills
        assert "implement" in res.installed_skills

        # Now modify implement
        (tmp_path / ".agents" / "skills" / "implement" / "SKILL.md").write_text("# Local Edit", encoding="utf-8")

        res_no_force = fake.sync_skills(project_dir=tmp_path, force=False)
        assert "implement" in res_no_force.preserved_skills
        assert (tmp_path / ".agents" / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8") == "# Local Edit"

        res_force = fake.sync_skills(project_dir=tmp_path, force=True)
        assert "implement" in res_force.updated_skills
        assert (tmp_path / ".agents" / "skills" / "implement" / "SKILL.md").read_text(encoding="utf-8") == "# Standard Implement"

    def test_fake_skills_client_raises_when_configured(self, tmp_path: Path) -> None:
        fake = FakeSkillsClient(should_raise=SkillsSyncError("Simulated failure"))

        with pytest.raises(SkillsSyncError, match="Simulated failure"):
            fake.sync_skills(project_dir=tmp_path)
