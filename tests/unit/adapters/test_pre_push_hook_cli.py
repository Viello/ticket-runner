"""Unit tests for the pre-push hook CLI."""

import os
from pathlib import Path
import stat
import subprocess
import sys
import pytest

from runner.adapters.git.pre_push_hook import PrePushHookInstaller


@pytest.fixture
def fake_git_dir(tmp_path: Path) -> Path:
    """Create a temporary fake .git directory."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir(parents=True)
    return git_dir


def test_cli_install_happy_path(fake_git_dir: Path, tmp_path: Path) -> None:
    """Happy path: python -m runner.adapters.git.pre_push_hook install --git-dir <tmpdir>/.git exits 0."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.adapters.git.pre_push_hook",
            "install",
            "--git-dir",
            str(fake_git_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    hook_file = fake_git_dir / "hooks" / "pre-push"
    assert hook_file.is_file()

    content = hook_file.read_text(encoding="utf-8")
    assert PrePushHookInstaller.BEGIN_SIGNATURE in content
    assert PrePushHookInstaller.END_SIGNATURE in content

    # Check executable permission
    mode = hook_file.stat().st_mode
    assert mode & stat.S_IXUSR or os.name == "nt"

    # Check success message
    assert "Installed pre-push guardrail into" in result.stdout
    assert str(hook_file) in result.stdout or hook_file.name in result.stdout


def test_cli_install_idempotent(fake_git_dir: Path, tmp_path: Path) -> None:
    """Idempotent re-run on an already-installed hook: exit 0, no overwrite of existing content."""
    # First install
    res1 = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.adapters.git.pre_push_hook",
            "install",
            "--git-dir",
            str(fake_git_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert res1.returncode == 0

    hook_file = fake_git_dir / "hooks" / "pre-push"
    initial_content = hook_file.read_text(encoding="utf-8")

    # Second install run
    res2 = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.adapters.git.pre_push_hook",
            "install",
            "--git-dir",
            str(fake_git_dir),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert res2.returncode == 0
    assert hook_file.read_text(encoding="utf-8") == initial_content


def test_cli_missing_git_dir_argument(tmp_path: Path) -> None:
    """Missing --git-dir argument: exit non-zero with a usage message."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.adapters.git.pre_push_hook",
            "install",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    stderr_lower = result.stderr.lower()
    assert "usage:" in stderr_lower or "error:" in stderr_lower
    assert "--git-dir" in result.stderr


def test_cli_non_existent_git_dir(tmp_path: Path) -> None:
    """Non-existent --git-dir: exit non-zero with a clear error."""
    non_existent = tmp_path / "does_not_exist" / ".git"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.adapters.git.pre_push_hook",
            "install",
            "--git-dir",
            str(non_existent),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "does not exist or is not a directory" in result.stderr.lower()


def test_cli_custom_template_path(fake_git_dir: Path, tmp_path: Path) -> None:
    """Custom --template-path is forwarded to installer."""
    custom_template = tmp_path / "custom_pre_push.sh"
    custom_template.write_text(
        "#!/bin/sh\n# custom template\n"
        f"{PrePushHookInstaller.GUARDRAIL_SNIPPET}\n"
        "exit 0\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "runner.adapters.git.pre_push_hook",
            "install",
            "--git-dir",
            str(fake_git_dir),
            "--template-path",
            str(custom_template),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    hook_file = fake_git_dir / "hooks" / "pre-push"
    assert hook_file.is_file()
    content = hook_file.read_text(encoding="utf-8")
    assert "# custom template" in content
