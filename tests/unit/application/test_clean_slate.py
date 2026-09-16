"""Unit tests for CleanSlateArchiver interactor."""

from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from runner.adapters.markdown.gotchas_store import DEFAULT_SKELETON, GotchasStore
from runner.application.clean_slate import CleanSlateArchiver, CleanSlateResult
from runner.application.git_operations import GitOperations
from runner.domain.config import LifecycleConfig
from runner.domain.exceptions import GitError
from tests.fakes.fake_command_runner import FakeCommandRunner


def _create_workspace(tmp_path: Path, spec_slug: str = "02-queue") -> dict[str, Path]:
    tickets_dir = tmp_path / "docs" / "tickets"
    spec_tickets = tickets_dir / spec_slug
    completed_dir = spec_tickets / "completed"
    completed_dir.mkdir(parents=True, exist_ok=True)

    t1 = completed_dir / "T001-setup.md"
    t1.write_text("# T001 — Setup\nStatus: completed\n", encoding="utf-8")
    t2 = completed_dir / "T002-feature.md"
    t2.write_text("# T002 — Feature\nStatus: completed\n", encoding="utf-8")

    specs_dir = tmp_path / "docs" / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    spec_file = specs_dir / f"{spec_slug}.md"
    spec_file.write_text(f"# Spec: {spec_slug}\n\nRequirements...", encoding="utf-8")

    gotchas_file = tickets_dir / "gotchas.md"
    gotchas_file.write_text(
        DEFAULT_SKELETON + "\n### Runtime Gotcha\n- **Problem**: P\n- **Solution**: S\n",
        encoding="utf-8",
    )

    archive_root = tmp_path / ".agent" / "archive"

    return {
        "root": tmp_path,
        "tickets": tickets_dir,
        "spec_tickets": spec_tickets,
        "completed": completed_dir,
        "specs": specs_dir,
        "spec_file": spec_file,
        "gotchas": gotchas_file,
        "archive_root": archive_root,
    }


@pytest.fixture
def fake_runner() -> FakeCommandRunner:
    runner = FakeCommandRunner()
    runner.register(["git", "rm", "-r", "docs/tickets/02-queue"], exit_code=0)
    runner.register(["git", "rm", "docs/specs/02-queue.md"], exit_code=0)
    runner.register(["git", "add", "."], exit_code=0)
    runner.register(["git", "commit", "-m"], exit_code=0)
    runner.register(["git", "rev-parse", "HEAD"], stdout="c" * 40 + "\n")
    return runner


def test_interactive_policy_confirmed_executes_full_flow(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    prompt_called = False

    def confirm_callback(prompt: str) -> bool:
        nonlocal prompt_called
        prompt_called = True
        return True

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        confirmation_callback=confirm_callback,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    result = asyncio.run(archiver.clean_slate("02-queue", policy="interactive"))

    assert prompt_called is True
    assert result.cleaned is True
    assert bool(result) is True
    assert result == True
    assert result.commit_sha == "c" * 40

    # 1. Archive copies exist under .agent/archive/02-queue/
    archive_spec = ws["archive_root"] / "02-queue"
    assert archive_spec.is_dir()
    assert (archive_spec / "completed" / "T001-setup.md").is_file()
    assert (archive_spec / "completed" / "T002-feature.md").is_file()
    assert (archive_spec / "02-queue.md").is_file()

    # 2. Git removal commands invoked
    assert ["git", "rm", "-r", "docs/tickets/02-queue"] in fake_runner.commands
    assert ["git", "rm", "docs/specs/02-queue.md"] in fake_runner.commands

    # 3. Gotchas reset to skeleton
    assert ws["gotchas"].read_text(encoding="utf-8") == DEFAULT_SKELETON

    # 4. Authored single chore commit
    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 1
    commit_msg = commit_invocations[0].cmd[3]
    assert commit_msg.startswith("chore(queue): Clean up 02-queue tickets, gotchas, and spec")
    assert "- Archive 02-queue tickets and spec to untracked storage" in commit_msg
    assert "T001" not in commit_msg
    assert "T002" not in commit_msg


def test_interactive_policy_declined_leaves_tree_untouched(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    original_gotchas = ws["gotchas"].read_text(encoding="utf-8")

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        confirmation_callback=lambda prompt: False,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    result = asyncio.run(archiver.clean_slate("02-queue", policy="interactive"))

    assert result.cleaned is False
    assert bool(result) is False
    assert result == False
    assert result.commit_sha is None

    # Working tree untouched
    assert not ws["archive_root"].exists()
    assert fake_runner.commands == []
    assert ws["gotchas"].read_text(encoding="utf-8") == original_gotchas


def test_always_policy_proceeds_without_prompt(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    prompt_called = False

    def confirm_callback(prompt: str) -> bool:
        nonlocal prompt_called
        prompt_called = True
        return False

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        confirmation_callback=confirm_callback,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    result = asyncio.run(archiver.clean_slate("02-queue", policy="always"))

    assert prompt_called is False
    assert result.cleaned is True
    assert (ws["archive_root"] / "02-queue").is_dir()
    assert ["git", "rm", "-r", "docs/tickets/02-queue"] in fake_runner.commands
    assert ws["gotchas"].read_text(encoding="utf-8") == DEFAULT_SKELETON


def test_never_policy_skips_silently(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        confirmation_callback=lambda prompt: True,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    result = asyncio.run(archiver.clean_slate("02-queue", policy="never"))

    assert result.cleaned is False
    assert not ws["archive_root"].exists()
    assert fake_runner.commands == []


def test_archive_precedes_git_removal_ordering(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    archive_existed_during_git_rm = False

    # Hook into runner to verify archive existence when git rm is called
    original_run = fake_runner.run

    async def custom_run(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None):
        nonlocal archive_existed_during_git_rm
        if cmd[:2] == ["git", "rm"]:
            archive_spec = ws["archive_root"] / "02-queue"
            if (archive_spec / "completed" / "T001-setup.md").is_file():
                archive_existed_during_git_rm = True
        return await original_run(cmd, cwd=cwd, env=env)

    fake_runner.run = custom_run  # type: ignore[method-assign]

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    result = asyncio.run(archiver.clean_slate("02-queue", policy="always"))
    assert result.cleaned is True
    assert archive_existed_during_git_rm is True


def test_git_rm_failure_raises_git_error_and_no_partial_deletion(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    # Fail git rm on tickets dir (e.g. untracked or dirty state)
    fake_runner.register(
        ["git", "rm", "-r", "docs/tickets/02-queue"],
        exit_code=128,
        stderr="fatal: pathspec 'docs/tickets/02-queue' did not match any files",
    )

    original_gotchas = ws["gotchas"].read_text(encoding="utf-8")

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    with pytest.raises(GitError, match="Failed to remove path 'docs/tickets/02-queue'"):
        asyncio.run(archiver.clean_slate("02-queue", policy="always"))

    # Gotchas was NOT modified
    assert ws["gotchas"].read_text(encoding="utf-8") == original_gotchas
    # No commits authored
    assert not any(cmd[:2] == ["git", "commit"] for cmd in fake_runner.commands)
    # But archive copy was safely saved before git rm was attempted
    assert (ws["archive_root"] / "02-queue" / "completed" / "T001-setup.md").is_file()


def test_missing_tickets_directory_raises_file_not_found(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        tickets_dir=tmp_path / "docs" / "tickets",
        specs_dir=tmp_path / "docs" / "specs",
        archive_root=tmp_path / ".agent" / "archive",
        cwd=tmp_path,
    )

    with pytest.raises(FileNotFoundError, match="Tickets directory not found"):
        asyncio.run(archiver.clean_slate("unknown-spec", policy="always"))


def test_unsupported_policy_raises_value_error(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    archiver = CleanSlateArchiver(git_operations=git_ops, cwd=tmp_path)

    with pytest.raises(ValueError, match="Unsupported clean slate policy"):
        asyncio.run(archiver.clean_slate("02-queue", policy="invalid_policy"))


def test_supports_lifecycle_config_object(
    tmp_path: Path,
    fake_runner: FakeCommandRunner,
) -> None:
    ws = _create_workspace(tmp_path, "02-queue")
    git_ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    gotchas_store = GotchasStore(path=ws["gotchas"])

    archiver = CleanSlateArchiver(
        git_operations=git_ops,
        archive_root=ws["archive_root"],
        tickets_dir=ws["tickets"],
        specs_dir=ws["specs"],
        gotchas_store=gotchas_store,
        cwd=tmp_path,
    )

    config = LifecycleConfig(clean_slate="always")
    result = asyncio.run(archiver.clean_slate("02-queue", policy=config))
    assert result.cleaned is True
