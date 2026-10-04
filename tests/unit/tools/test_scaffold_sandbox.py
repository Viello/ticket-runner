"""Unit tests for runner.tools.scaffold_sandbox."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import pytest

from runner.adapters.git.pre_push_hook import PrePushHookInstaller
from runner.tools.scaffold_sandbox import (
    DEFAULT_PREAMBLE,
    extract_curated_subset,
    get_default_target_dir,
    main,
    scaffold,
)


def test_get_default_target_dir() -> None:
    default_dir = get_default_target_dir()
    if sys.platform == "win32":
        assert default_dir == Path(r"D:\Sandbox\ticket-runner-live-target")
    else:
        assert default_dir == Path.home() / "Sandbox" / "ticket-runner-live-target"


def test_extract_curated_subset() -> None:
    sample_agents_md = """# AGENTS.md
Ticket Runner description.

## Implementation status
Specs 01-13 implemented.

## Read before designing
- ARCHITECTURE.md

## Invariants
- First invariant.
- Second invariant.

## Environment
- Windows/PowerShell.

## Development workflow
General workflow info.

### 1. Alignment & Design
- Grill me.

### 3. Execution (Interactive or Ticket Runner)
- Implement tickets.

## Agent skills
- .agents/skills/ implement.
"""
    curated = extract_curated_subset(sample_agents_md)
    assert "## Invariants" in curated
    assert "- First invariant." in curated
    assert "## Development workflow" in curated
    assert "### 1. Alignment & Design" in curated
    assert "## Agent skills" in curated
    assert "## Implementation status" not in curated
    assert "## Read before designing" not in curated
    assert "## Environment" not in curated


def test_scaffold_happy_path(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)

    # 1. .agent/ subdirs
    for sub in ("signals", "questions", "logs", "checkpoints", "evidence", "archive"):
        assert (target / ".agent" / sub).is_dir()

    # 2. .agents/skills
    for skill in ("implement", "code-review", "diagnosing-bugs", "handoff"):
        skill_file = target / ".agents" / "skills" / skill / "SKILL.md"
        assert skill_file.is_file()

    # 3. docs/tickets/00-welcome/T001-hello-world.md
    welcome_ticket = target / "docs" / "tickets" / "00-welcome" / "T001-hello-world.md"
    assert welcome_ticket.is_file()
    assert "Status: pending" in welcome_ticket.read_text(encoding="utf-8")

    # 4. src/sample_app/__init__.py and tests/test_smoke.py
    src_file = target / "src" / "sample_app" / "__init__.py"
    assert src_file.is_file()
    assert "def greet(name: str) -> str:" in src_file.read_text(encoding="utf-8")

    test_file = target / "tests" / "test_smoke.py"
    assert test_file.is_file()
    assert 'assert greet("world") == "hello, world!"' in test_file.read_text(encoding="utf-8")

    # 5. AGENTS.md
    agents_md = target / "AGENTS.md"
    assert agents_md.is_file()
    content = agents_md.read_text(encoding="utf-8")
    assert DEFAULT_PREAMBLE in content
    assert "<!-- mirrored from D:\\Projects/AGENTS.md on" in content
    assert "## Invariants" in content

    # 6. ticket-runner.yaml and .gitignore
    assert (target / "ticket-runner.yaml").is_file()
    assert (target / ".gitignore").is_file()

    # 7. Git repo checks
    assert (target / ".git").is_dir()
    branch_res = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert branch_res.stdout.strip() == "agent/ticket-runner"

    # Pre-push hook installed
    assert PrePushHookInstaller.is_installed(target / ".git")

    # Initial commit
    log_res = subprocess.run(
        ["git", "-C", str(target), "log", "-1", "--pretty=%B"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "chore(sandbox): initialize ticket-runner onboarding sandbox" in log_res.stdout


def test_scaffold_idempotent_preserves_existing_files(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)

    # Modify a file
    custom_text = "# Custom User Edit\n"
    (target / "AGENTS.md").write_text(custom_text, encoding="utf-8")

    # Re-run scaffold without force
    scaffold(target, force=False)

    # Check file was preserved
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == custom_text


def test_scaffold_force_wipes_and_regenerates_preserving_runtime_and_git(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)

    # Modify AGENTS.md
    (target / "AGENTS.md").write_text("# Modified", encoding="utf-8")

    # Add extra source file
    extra_file = target / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")

    # Add a runtime file inside .agent/
    runtime_file = target / ".agent" / "logs" / "runtime.log"
    runtime_file.write_text("runtime state", encoding="utf-8")

    # Run with force
    scaffold(target, force=True)

    # Extra source file wiped
    assert not extra_file.exists()

    # AGENTS.md regenerated
    assert "## Invariants" in (target / "AGENTS.md").read_text(encoding="utf-8")

    # .git preserved
    assert (target / ".git").is_dir()

    # .agent runtime state preserved
    assert runtime_file.is_file()
    assert runtime_file.read_text(encoding="utf-8") == "runtime state"


def test_scaffold_git_identity_auto_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "sandbox"
    # Ensure git config has empty or custom behavior by running in clean target
    scaffold(target, force=False)

    # Check that git user.name and user.email are set locally if not global
    name_res = subprocess.run(
        ["git", "-C", str(target), "config", "user.name"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert name_res.stdout.strip() != ""


def test_main_cli_surface(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "cli_sandbox"
    exit_code = main(["--target-dir", str(target), "--non-interactive"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "[scaffold]" in captured
    assert "Target directory:" in captured
    assert "Files created:" in captured
    assert "Hook installed:" in captured
    assert "Commit:" in captured
    assert "Verification:" in captured
