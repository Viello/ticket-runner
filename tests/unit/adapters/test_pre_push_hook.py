"""Unit tests for PrePushHookInstaller adapter."""

import os
from pathlib import Path
import stat
import subprocess
import pytest

from runner.adapters.git.pre_push_hook import PrePushHookInstaller


@pytest.fixture
def fake_git_dir(tmp_path: Path) -> Path:
    """Create a temporary fake .git directory with a hooks folder."""
    git_dir = tmp_path / ".git"
    git_dir.mkdir(parents=True)
    return git_dir


def test_is_installed_returns_false_when_hook_missing(fake_git_dir: Path) -> None:
    """is_installed should return False when .git/hooks/pre-push does not exist."""
    installer = PrePushHookInstaller()
    assert installer.is_installed(fake_git_dir) is False


def test_is_installed_returns_false_when_signature_missing(fake_git_dir: Path) -> None:
    """is_installed should return False when pre-push hook exists without guardrail signature."""
    hooks_dir = fake_git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_push_file = hooks_dir / "pre-push"
    pre_push_file.write_text("#!/bin/sh\necho 'custom user hook'\n", encoding="utf-8")

    installer = PrePushHookInstaller()
    assert installer.is_installed(fake_git_dir) is False


def test_install_creates_hook_when_absent(fake_git_dir: Path) -> None:
    """install should create .git/hooks/pre-push with executable permissions if absent."""
    installer = PrePushHookInstaller()
    result = installer.install(fake_git_dir)

    assert result is True
    hook_path = fake_git_dir / "hooks" / "pre-push"
    assert hook_path.exists()
    assert installer.is_installed(fake_git_dir) is True

    content = hook_path.read_text(encoding="utf-8")
    assert installer.BEGIN_SIGNATURE in content
    assert installer.END_SIGNATURE in content
    assert 'current_branch="agent/ticket-runner"' in content or 'agent/ticket-runner' in content

    # Check executable permission bit
    mode = hook_path.stat().st_mode
    assert mode & stat.S_IXUSR or os.name == "nt"


def test_install_appends_non_destructively_to_existing_hook(fake_git_dir: Path) -> None:
    """install should preserve existing user code and append guardrail block."""
    hooks_dir = fake_git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    pre_push_file = hooks_dir / "pre-push"
    user_script = "#!/bin/sh\n# User custom pre-push checks\npytest tests/\n"
    pre_push_file.write_text(user_script, encoding="utf-8")

    installer = PrePushHookInstaller()
    result = installer.install(fake_git_dir)

    assert result is True
    assert installer.is_installed(fake_git_dir) is True

    content = pre_push_file.read_text(encoding="utf-8")
    assert content.startswith(user_script)
    assert installer.BEGIN_SIGNATURE in content
    assert installer.END_SIGNATURE in content


def test_install_is_idempotent(fake_git_dir: Path) -> None:
    """install should not duplicate guardrail blocks when executed repeatedly."""
    installer = PrePushHookInstaller()
    installer.install(fake_git_dir)

    hook_path = fake_git_dir / "hooks" / "pre-push"
    initial_content = hook_path.read_text(encoding="utf-8")

    # Second install run
    installer.install(fake_git_dir)
    subsequent_content = hook_path.read_text(encoding="utf-8")

    assert subsequent_content == initial_content
    assert subsequent_content.count(installer.BEGIN_SIGNATURE) == 1
    assert subsequent_content.count(installer.END_SIGNATURE) == 1


def test_is_installed_callable_as_class_or_instance_method(fake_git_dir: Path) -> None:
    """is_installed and install should work as both instance and class/static methods."""
    assert PrePushHookInstaller.is_installed(fake_git_dir) is False
    PrePushHookInstaller.install(fake_git_dir)
    assert PrePushHookInstaller.is_installed(fake_git_dir) is True


def test_guardrail_script_execution_blocks_agent_branch(fake_git_dir: Path, tmp_path: Path) -> None:
    """Simulate execution of the guardrail hook to verify it blocks agent/ticket-runner."""
    # Find sh if available in environment (e.g. Git for Windows sh.exe)
    import shutil
    sh_path = shutil.which("sh")
    if not sh_path:
        for candidate in [
            r"C:\Program Files\Git\bin\sh.exe",
            r"C:\Program Files\Git\usr\bin\sh.exe",
            r"C:\Program Files (x86)\Git\bin\sh.exe",
            r"C:\Program Files (x86)\Git\usr\bin\sh.exe",
        ]:
            if os.path.isfile(candidate):
                sh_path = candidate
                break

    if not sh_path:
        pytest.skip("POSIX sh interpreter not found on system PATH")

    installer = PrePushHookInstaller()
    installer.install(fake_git_dir)
    hook_path = fake_git_dir / "hooks" / "pre-push"

    # Run in a dummy repo context or simulate git symbolic-ref
    # We can test by running sh with a mock git or checking git symbolic-ref
    test_sh = (
        f'git() {{ echo "agent/ticket-runner"; }}; '
        f'export -f git 2>/dev/null || true; '
        f'. "{hook_path.as_posix()}"'
    )
    # Use sh to execute a script that overrides git symbolic-ref output
    script = f'''
git() {{
    if [ "$1" = "symbolic-ref" ]; then
        echo "agent/ticket-runner"
        return 0
    fi
    command git "$@"
}}
. "{hook_path.as_posix()}"
'''
    proc = subprocess.run(
        [sh_path, "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "Direct git push is blocked on agent/ticket-runner branch" in proc.stderr


def test_guardrail_script_execution_allows_other_branches(fake_git_dir: Path) -> None:
    """Verify that the guardrail hook allows pushing on other branches like main."""
    import shutil
    sh_path = shutil.which("sh")
    if not sh_path:
        for candidate in [
            r"C:\Program Files\Git\bin\sh.exe",
            r"C:\Program Files\Git\usr\bin\sh.exe",
            r"C:\Program Files (x86)\Git\bin\sh.exe",
            r"C:\Program Files (x86)\Git\usr\bin\sh.exe",
        ]:
            if os.path.isfile(candidate):
                sh_path = candidate
                break

    if not sh_path:
        pytest.skip("POSIX sh interpreter not found on system PATH")

    installer = PrePushHookInstaller()
    installer.install(fake_git_dir)
    hook_path = fake_git_dir / "hooks" / "pre-push"

    script = f'''
git() {{
    if [ "$1" = "symbolic-ref" ]; then
        echo "main"
        return 0
    fi
    command git "$@"
}}
. "{hook_path.as_posix()}"
'''
    proc = subprocess.run(
        [sh_path, "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0

