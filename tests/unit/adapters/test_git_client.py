"""Unit tests for GitClient adapter using FakeCommandRunner."""

import asyncio
from pathlib import Path
import pytest

from runner.adapters.git.git_client import GitClient
from runner.domain.exceptions import GitError
from runner.ports.command_runner import CommandResult
from tests.fakes.fake_command_runner import FakeCommandRunner


@pytest.fixture
def fake_runner() -> FakeCommandRunner:
    return FakeCommandRunner()


@pytest.fixture
def git_client(fake_runner: FakeCommandRunner) -> GitClient:
    return GitClient(runner=fake_runner)


def test_git_client_status_porcelain(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout=" M file.py\n?? new.txt\n")
    result = asyncio.run(git_client.status_porcelain())

    assert result.success is True
    assert "file.py" in result.stdout
    assert fake_runner.commands == [["git", "status", "--porcelain"]]


def test_git_client_symbolic_ref(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    result = asyncio.run(git_client.symbolic_ref(ref="HEAD", short=True))

    assert result.success is True
    assert result.stdout.strip() == "agent/ticket-runner"
    assert fake_runner.commands == [["git", "symbolic-ref", "--short", "HEAD"]]


def test_git_client_symbolic_ref_full(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "symbolic-ref", "HEAD"], stdout="refs/heads/main\n")
    result = asyncio.run(git_client.symbolic_ref(ref="HEAD", short=False))

    assert result.success is True
    assert result.stdout.strip() == "refs/heads/main"
    assert fake_runner.commands == [["git", "symbolic-ref", "HEAD"]]


def test_git_client_get_current_branch_success(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    branch = asyncio.run(git_client.get_current_branch())

    assert branch == "agent/ticket-runner"


def test_git_client_get_current_branch_failure(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(
        ["git", "symbolic-ref", "--short", "HEAD"],
        exit_code=128,
        stderr="fatal: ref HEAD is not a symbolic ref",
    )
    with pytest.raises(GitError, match="Failed to get current branch"):
        asyncio.run(git_client.get_current_branch())


def test_git_client_checkout(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "checkout", "agent/ticket-runner"], exit_code=0)
    result = asyncio.run(git_client.checkout("agent/ticket-runner"))

    assert result.success is True
    assert fake_runner.commands == [["git", "checkout", "agent/ticket-runner"]]


def test_git_client_checkout_new_branch(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "checkout", "-b", "agent/ticket-runner"], exit_code=0)
    result = asyncio.run(git_client.checkout_new_branch("agent/ticket-runner"))

    assert result.success is True
    assert fake_runner.commands == [["git", "checkout", "-b", "agent/ticket-runner"]]


def test_git_client_add_all(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=0)
    result = asyncio.run(git_client.add_all())

    assert result.success is True
    assert fake_runner.commands == [["git", "add", "."]]


def test_git_client_commit(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    commit_msg = "feat(git): Add GitClient adapter\n\n- Add GitClient"
    fake_runner.register(["git", "commit", "-m", commit_msg], exit_code=0)
    result = asyncio.run(git_client.commit(commit_msg))

    assert result.success is True
    assert fake_runner.commands == [["git", "commit", "-m", commit_msg]]


def test_git_client_rev_parse(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(
        ["git", "rev-parse", "HEAD"],
        stdout="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n",
    )
    result = asyncio.run(git_client.rev_parse("HEAD"))

    assert result.success is True
    assert "e3b0c442" in result.stdout


def test_git_client_get_head_sha_success(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    expected_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout=f"{expected_sha}\n")
    sha = asyncio.run(git_client.get_head_sha())

    assert sha == expected_sha


def test_git_client_get_head_sha_failure(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(
        ["git", "rev-parse", "HEAD"],
        exit_code=128,
        stderr="fatal: ambiguous argument 'HEAD': unknown revision",
    )
    with pytest.raises(GitError, match="Failed to get HEAD commit SHA"):
        asyncio.run(git_client.get_head_sha())


def test_git_client_reset_hard(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "reset", "--hard", "HEAD"], exit_code=0)
    result = asyncio.run(git_client.reset_hard())

    assert result.success is True
    assert fake_runner.commands == [["git", "reset", "--hard", "HEAD"]]


def test_git_client_clean(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "clean", "-fd"], exit_code=0)
    result = asyncio.run(git_client.clean())

    assert result.success is True
    assert fake_runner.commands == [["git", "clean", "-fd"]]


def test_git_client_respects_cwd(
    fake_runner: FakeCommandRunner,
    tmp_path: Path,
) -> None:
    client = GitClient(runner=fake_runner, cwd=tmp_path)
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    asyncio.run(client.status_porcelain())

    assert len(fake_runner.invocations) == 1
    assert fake_runner.invocations[0].cwd == tmp_path


def test_git_client_rm_file(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "rm", "docs/specs/02-queue.md"], exit_code=0)
    result = asyncio.run(git_client.rm("docs/specs/02-queue.md"))

    assert result.success is True
    assert fake_runner.commands == [["git", "rm", "docs/specs/02-queue.md"]]


def test_git_client_rm_recursive(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "rm", "-r", "docs/tickets/02-queue"], exit_code=0)
    result = asyncio.run(git_client.rm("docs/tickets/02-queue", recursive=True))

    assert result.success is True
    assert fake_runner.commands == [["git", "rm", "-r", "docs/tickets/02-queue"]]


def test_git_client_rm_recursive_force(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "rm", "-r", "-f", "docs/tickets/02-queue"], exit_code=0)
    result = asyncio.run(git_client.rm("docs/tickets/02-queue", recursive=True, force=True))

    assert result.success is True
    assert fake_runner.commands == [["git", "rm", "-r", "-f", "docs/tickets/02-queue"]]


def test_git_client_diff_stat(
    git_client: GitClient,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "diff", "--stat"], stdout=" 1 file changed, 1 insertion(+)\n")
    result = asyncio.run(git_client.diff_stat())

    assert result.success is True
    assert "1 file changed" in result.stdout
    assert fake_runner.commands == [["git", "diff", "--stat"]]
