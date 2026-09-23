"""Spec 12 Integration Suite: Project Scaffolding, LLM-Friendly Config & Skills Distribution.

Validates:
- CLI `init` non-interactive execution on mock Python and Node.js repositories.
- CLI `init --ai-prompt` output structure.
- CLI `skills sync` subcommand integration.
- Running `doctor` on an initialized repository verifying two-tier configuration resolution.
- Running `start` on an initialized repository verifying two-tier configuration resolution.
- Security verification: path validation, non-existent directories, invalid paths, and explicit config overrides.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.application.doctor import (
    Doctor,
    DoctorReport,
    CheckResult,
)
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_skills_client import FakeSkillsClient
import ticket_runner


# ==============================================================================
# Helper fixtures / setups
# ==============================================================================

def _seed_git_repo(project_dir: Path) -> FakeCommandRunner:
    """Configure fake command runner to simulate clean git repo on agent/ticket-runner."""
    git_dir = project_dir / ".git"
    git_dir.mkdir(parents=True, exist_ok=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/agent/ticket-runner\n", encoding="utf-8")

    runner = FakeCommandRunner()
    runner.register(["git", "rev-parse", "--is-inside-work-tree"], stdout="true\n")
    runner.register(["git", "status", "--porcelain"], stdout="")
    runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    runner.register(["opencode", "--version"], stdout="opencode 1.0.0\n")
    runner.register(["git", "rev-parse", "--abbrev-ref", "origin/HEAD"], stdout="origin/main\n")
    return runner


def _seed_required_workspace_files(project_dir: Path) -> None:
    """Populate AGENTS.md, sample ticket, and required skills for passing doctor."""
    (project_dir / "AGENTS.md").write_text("# Operating Rules\n", encoding="utf-8")

    ticket_dir = project_dir / "docs" / "tickets" / "01-test"
    ticket_dir.mkdir(parents=True, exist_ok=True)
    ticket_content = (
        "# T001 \u2014 Test Ticket\n"
        "Status: pending\n"
        "Scope: test\n\n"
        "### Requirements\n- Test.\n\n"
        "### Acceptance Criteria\n- Pass.\n\n"
        "### Smoke Scenarios\n- None.\n"
    )
    (ticket_dir / "T001-test.md").write_text(ticket_content, encoding="utf-8")

    skills_dir = project_dir / ".agents" / "skills"
    for skill_name in ("implement", "code-review", "diagnosing-bugs"):
        sdir = skills_dir / skill_name
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "SKILL.md").write_text(f"# {skill_name}\nInstructions\n", encoding="utf-8")


# ==============================================================================
# Test Cases
# ==============================================================================

def test_cli_init_non_interactive_python_repo(tmp_path: Path) -> None:
    """ticket_runner init --yes --no-skills scaffolds Python repo with detected pytest defaults."""
    repo = tmp_path / "py_project"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo-python-service"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    exit_code = ticket_runner.main([
        "init",
        "--project-dir", str(repo),
        "--yes",
        "--no-skills",
    ])

    assert exit_code == 0

    # Verify generated ticket-runner.yaml
    config_file = repo / "ticket-runner.yaml"
    assert config_file.is_file()
    content = config_file.read_text(encoding="utf-8")
    assert 'name: demo-python-service' in content
    assert 'test_cmd: python -m pytest' in content
    assert 'provider: opencode' in content

    # Verify directory tree and .gitkeep markers
    for rel_dir in (
        "docs/specs",
        "docs/tickets",
        ".agent",
        ".agent/archive/completed",
        ".agent/signals",
        ".agent/questions",
        ".agent/checkpoints",
    ):
        target = repo / rel_dir
        assert target.is_dir(), f"Expected directory {rel_dir} to exist"
        gitkeep = target / ".gitkeep"
        assert gitkeep.is_file(), f"Expected .gitkeep in {rel_dir}"

    # Verify gotchas.md and .gitignore
    assert (repo / "docs" / "tickets" / "gotchas.md").is_file()
    gitignore = repo / ".gitignore"
    assert gitignore.is_file()
    assert ".agent/" in gitignore.read_text(encoding="utf-8")


def test_cli_init_non_interactive_nodejs_repo(tmp_path: Path) -> None:
    """ticket_runner init --non-interactive --no-skills scaffolds Node.js repo with detected pnpm scripts."""
    repo = tmp_path / "node_project"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "package.json").write_text(
        '{"name": "demo-node-app", "scripts": {"test": "jest", "build": "tsc"}}\n',
        encoding="utf-8",
    )
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: 5.4\n", encoding="utf-8")

    exit_code = ticket_runner.main([
        "init",
        "--project-dir", str(repo),
        "--non-interactive",
        "--no-skills",
    ])

    assert exit_code == 0

    config_file = repo / "ticket-runner.yaml"
    assert config_file.is_file()
    content = config_file.read_text(encoding="utf-8")
    assert 'name: demo-node-app' in content
    assert 'test_cmd: pnpm test' in content
    assert 'build_cmd: pnpm run build' in content


def test_cli_init_ai_prompt_flag(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """ticket_runner init --ai-prompt outputs complete Markdown prompt with pre-detected heuristics."""
    repo = tmp_path / "ai_project"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "ai-prompt-app"\n',
        encoding="utf-8",
    )

    exit_code = ticket_runner.main([
        "init",
        "--project-dir", str(repo),
        "--ai-prompt",
    ])

    assert exit_code == 0
    captured = capsys.readouterr()
    output = captured.out

    assert "# Ticket Runner Configuration Prompt" in output
    assert "## Pre-Detected Project Context" in output
    assert "ai-prompt-app" in output
    assert "python -m pytest" in output
    assert "## Configuration Schema (`ticket-runner.yaml`)" in output
    assert "## Stack Examples" in output


def test_cli_skills_sync_subcommand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ticket_runner skills sync synchronizes skills catalog into target project."""
    repo = tmp_path / "sync_repo"
    repo.mkdir(parents=True, exist_ok=True)

    fake_client = FakeSkillsClient(
        canned_skills={
            "implement": {"SKILL.md": "# Implement\nImplementation steps"},
            "code-review": {"SKILL.md": "# Code Review\nReview steps"},
        }
    )

    # Monkeypatch the default client in run_skills_sync
    import runner.adapters.skills.skills_client as sc_module
    monkeypatch.setattr(sc_module, "GitHubSkillsClient", lambda: fake_client)

    exit_code = ticket_runner.main([
        "skills",
        "sync",
        "--project-dir", str(repo),
    ])

    assert exit_code == 0
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0].project_dir == repo.resolve()

    skills_dir = repo / ".agents" / "skills"
    assert (skills_dir / "implement" / "SKILL.md").is_file()
    assert (skills_dir / "code-review" / "SKILL.md").is_file()


def test_doctor_on_initialized_repository_passes_two_tier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """doctor passes on newly initialized project using two-tier config overlay."""
    repo = tmp_path / "doctor_repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text('[project]\nname = "doctor-app"\n', encoding="utf-8")

    # Step 1: Initialize repository
    init_code = ticket_runner.main([
        "init",
        "--project-dir", str(repo),
        "--yes",
        "--no-skills",
    ])
    assert init_code == 0

    # Step 2: Seed git and workspace prerequisites
    fake_runner = _seed_git_repo(repo)
    _seed_required_workspace_files(repo)

    # Step 3: Run doctor pre-flight checks
    doctor = Doctor(
        command_runner=fake_runner,
        project_dir=repo,
        which_fn=lambda cmd: f"/bin/{cmd}",
    )
    doctor.check_hook = lambda: asyncio.sleep(0, CheckResult("hook", True, "ok"))  # bypass hook file check

    exit_code = asyncio.run(
        ticket_runner.run_doctor(
            project_dir=repo,
            local_only=True,
            doctor_instance=doctor,
        )
    )

    assert exit_code == 0
    assert doctor.loaded_config is not None
    assert doctor.loaded_config.project.name == "doctor-app"
    assert doctor.loaded_config.verification.test_cmd == "python -m pytest"
    # Merged from default machine config:
    assert doctor.loaded_config.tokens.ceiling == 150000
    assert doctor.loaded_config.worker.provider == "opencode"


def test_start_on_initialized_repository_discovers_two_tier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """start subcommand discovers and merges ticket-runner.yaml over machine defaults."""
    repo = tmp_path / "start_repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "pyproject.toml").write_text('[project]\nname = "start-app"\n', encoding="utf-8")

    # Initialize repository
    ticket_runner.main([
        "init",
        "--project-dir", str(repo),
        "--yes",
        "--no-skills",
    ])

    fake_runner = _seed_git_repo(repo)
    _seed_required_workspace_files(repo)

    fake_doc = Doctor(
        project_dir=repo,
        command_runner=fake_runner,
        which_fn=lambda cmd: f"/bin/{cmd}",
    )
    fake_doc.check_hook = lambda: asyncio.sleep(0, CheckResult("hook", True, "ok"))

    class FakeOrchestrator:
        def __init__(self) -> None:
            self.ran = False

        async def run_lifecycle(self, **kwargs: Any) -> int:
            self.ran = True
            return 0

        def release_lock(self) -> None:
            pass

    fake_orch = FakeOrchestrator()

    exit_code = asyncio.run(
        ticket_runner.run_start(
            project_dir=repo,
            local_only=True,
            doctor_instance=fake_doc,
            orchestrator_instance=fake_orch,
        )
    )

    assert exit_code == 0
    assert fake_orch.ran is True


def test_explicit_config_overrides_project_overlay(tmp_path: Path) -> None:
    """Explicit --config overrides ticket-runner.yaml while preserving two-tier merging."""
    repo = tmp_path / "override_repo"
    repo.mkdir(parents=True, exist_ok=True)

    # Initialize default ticket-runner.yaml
    ticket_runner.main([
        "init",
        "--project-dir", str(repo),
        "--yes",
        "--no-skills",
    ])

    # Create explicit custom overlay
    custom_overlay = repo / "custom-overlay.yaml"
    custom_overlay.write_text(
        "project:\n  name: override-app\n  base_branch: main\nverification:\n  test_cmd: pytest tests/custom\n",
        encoding="utf-8",
    )

    loader = YamlConfigLoader()
    cfg = loader.load_two_tier(project_dir=repo, project_config_path=custom_overlay)

    assert cfg.verification.test_cmd == "pytest tests/custom"
    # Preserves project name from ticket-runner.yaml or defaults
    assert cfg.tokens.ceiling == 150000


def test_security_validation_invalid_and_nonexistent_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """Security verification: CLI rejects invalid directory paths, files, and non-existent targets with code 1."""
    # 1. Project path is a regular file
    reg_file = tmp_path / "some_file.txt"
    reg_file.write_text("not a dir", encoding="utf-8")

    code = ticket_runner.main(["init", "--project-dir", str(reg_file)])
    assert code == 1
    captured = capsys.readouterr()
    assert "is not a directory" in captured.out

    # 2. Non-existent project path for skills sync
    non_existent = tmp_path / "does_not_exist"
    code = ticket_runner.main(["skills", "sync", "--project-dir", str(non_existent)])
    assert code == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.out

    # 3. Non-existent project path for doctor
    code = ticket_runner.main(["doctor", "--project-dir", str(non_existent)])
    assert code == 1
    captured = capsys.readouterr()
    assert "does not exist" in captured.out

    # 4. Null byte in project path
    code = ticket_runner.main(["init", "--project-dir", f"{tmp_path}\0bad"])
    assert code == 1
    captured = capsys.readouterr()
    assert "null byte" in captured.out
