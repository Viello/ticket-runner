"""Unit tests for GitOperations interactor using FakeCommandRunner."""

import asyncio
from pathlib import Path
import pytest

from runner.adapters.git.git_client import GitClient
from runner.application.git_operations import GitOperations
from runner.domain.exceptions import GitError
from tests.fakes.fake_command_runner import FakeCommandRunner


@pytest.fixture
def fake_runner() -> FakeCommandRunner:
    return FakeCommandRunner()


@pytest.fixture
def git_ops(fake_runner: FakeCommandRunner) -> GitOperations:
    return GitOperations(runner=fake_runner)


# --- check_clean_working_tree ---

def test_check_clean_working_tree_true_when_empty(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    assert asyncio.run(git_ops.check_clean_working_tree()) is True


def test_check_clean_working_tree_false_when_modified(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout=" M runner/application/git_operations.py\n")
    assert asyncio.run(git_ops.check_clean_working_tree()) is False


def test_check_clean_working_tree_false_when_untracked(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout="?? temp_file.txt\n")
    assert asyncio.run(git_ops.check_clean_working_tree()) is False


def test_check_clean_working_tree_raises_on_git_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], exit_code=128, stderr="fatal: not a git repository")
    with pytest.raises(GitError, match="status"):
        asyncio.run(git_ops.check_clean_working_tree())


# --- get_current_branch ---

def test_get_current_branch(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")
    assert asyncio.run(git_ops.get_current_branch()) == "agent/ticket-runner"


# --- ensure_branch ---

def test_ensure_branch_fails_fast_on_dirty_tree(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout=" M dirty_file.py\n")

    with pytest.raises(GitError, match="dirty|uncommitted"):
        asyncio.run(git_ops.ensure_branch("agent/ticket-runner"))

    # Only status was called, no checkout was attempted
    assert fake_runner.commands == [["git", "status", "--porcelain"]]


def test_ensure_branch_already_on_target_branch(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="agent/ticket-runner\n")

    asyncio.run(git_ops.ensure_branch("agent/ticket-runner"))

    assert fake_runner.commands == [
        ["git", "status", "--porcelain"],
        ["git", "symbolic-ref", "--short", "HEAD"],
    ]


def test_ensure_branch_switches_to_existing_branch(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="main\n")
    fake_runner.register(["git", "checkout", "agent/ticket-runner"], exit_code=0)

    asyncio.run(git_ops.ensure_branch("agent/ticket-runner"))

    assert fake_runner.commands == [
        ["git", "status", "--porcelain"],
        ["git", "symbolic-ref", "--short", "HEAD"],
        ["git", "checkout", "agent/ticket-runner"],
    ]


def test_ensure_branch_creates_new_branch_from_head(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="main\n")
    fake_runner.register(
        ["git", "checkout", "agent/ticket-runner"],
        exit_code=1,
        stderr="error: pathspec 'agent/ticket-runner' did not match any file(s) known to git",
    )
    fake_runner.register(["git", "checkout", "-b", "agent/ticket-runner"], exit_code=0)

    asyncio.run(git_ops.ensure_branch("agent/ticket-runner"))

    assert fake_runner.commands == [
        ["git", "status", "--porcelain"],
        ["git", "symbolic-ref", "--short", "HEAD"],
        ["git", "checkout", "agent/ticket-runner"],
        ["git", "checkout", "-b", "agent/ticket-runner"],
    ]


def test_ensure_branch_raises_when_checkout_and_create_fail(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    fake_runner.register(["git", "symbolic-ref", "--short", "HEAD"], stdout="main\n")
    fake_runner.register(["git", "checkout", "agent/ticket-runner"], exit_code=1, stderr="checkout error")
    fake_runner.register(["git", "checkout", "-b", "agent/ticket-runner"], exit_code=1, stderr="fatal: git error")

    with pytest.raises(GitError, match="Failed to checkout or create branch"):
        asyncio.run(git_ops.ensure_branch("agent/ticket-runner"))


# --- commit_ticket ---

def test_commit_ticket_authors_conventional_commit_and_returns_sha(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=0)
    expected_msg = (
        "feat(adapters): Implement GitClient adapter\n\n"
        "- Add GitClient adapter wrapping core git CLI commands\n"
        "- Add unit tests using FakeCommandRunner"
    )
    fake_runner.register(["git", "commit", "-m", expected_msg], exit_code=0)
    fake_runner.register(
        ["git", "rev-parse", "HEAD"],
        stdout="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855\n",
    )

    sha = asyncio.run(
        git_ops.commit_ticket(
            scope="adapters",
            title="Implement GitClient adapter",
            changes=[
                "Add GitClient adapter wrapping core git CLI commands",
                "Add unit tests using FakeCommandRunner.",
            ],
        )
    )

    assert sha == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert fake_runner.commands == [
        ["git", "add", "."],
        ["git", "commit", "-m", expected_msg],
        ["git", "rev-parse", "HEAD"],
    ]


def test_commit_ticket_strips_ticket_numbers_from_title_and_body(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=0)
    fake_runner.register(
        ["git", "rev-parse", "HEAD"],
        stdout="abcdef1234567890abcdef1234567890abcdef12\n",
    )

    # Title has T003 prefix, changes have ticket references and trailing periods
    asyncio.run(
        git_ops.commit_ticket(
            scope="application",
            title="T003 — Git operations adapter and working tree isolation",
            changes=[
                "- Implement T003 GitOperations interactor.",
                "Enforce branch isolation on agent/ticket-runner (T003)",
            ],
        )
    )

    # Inspect commit invocation
    commit_inv = [inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]][0]
    commit_msg = commit_inv.cmd[3]

    assert "T003" not in commit_msg
    assert "feat(application): Git operations adapter and working tree isolation" in commit_msg
    assert "- Implement GitOperations interactor" in commit_msg
    assert "- Enforce branch isolation on agent/ticket-runner" in commit_msg
    assert not any(line.endswith(".") for line in commit_msg.splitlines() if line.startswith("- "))


def test_commit_ticket_rejects_ticket_number_as_scope(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    with pytest.raises(GitError, match="scope"):
        asyncio.run(
            git_ops.commit_ticket(
                scope="T003",
                title="Something",
                changes=["Some change"],
            )
        )


def test_commit_ticket_custom_prefix(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=0)
    expected_msg = "fix(git): Fix branch detection\n\n- Correct ref check"
    fake_runner.register(["git", "commit", "-m", expected_msg], exit_code=0)
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="1234567890123456789012345678901234567890\n")

    sha = asyncio.run(
        git_ops.commit_ticket(
            scope="git",
            title="Fix branch detection",
            changes=["Correct ref check"],
            commit_prefix="fix",
        )
    )
    assert sha == "1234567890123456789012345678901234567890"


def test_commit_ticket_raises_on_add_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=1, stderr="fatal: error adding files")
    with pytest.raises(GitError, match="git add"):
        asyncio.run(git_ops.commit_ticket(scope="git", title="Title", changes=["Change"]))


def test_commit_ticket_raises_on_commit_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=0)
    fake_runner.register(["git", "commit", "-m", "feat(git): Title\n\n- Change"], exit_code=1, stderr="pre-commit hook failed")
    with pytest.raises(GitError, match="git commit"):
        asyncio.run(git_ops.commit_ticket(scope="git", title="Title", changes=["Change"]))


# --- reset_working_tree ---

def test_reset_working_tree_dispatches_reset_and_clean(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "reset", "--hard", "HEAD"], exit_code=0)
    fake_runner.register(["git", "clean", "-fd"], exit_code=0)

    asyncio.run(git_ops.reset_working_tree())

    assert fake_runner.commands == [
        ["git", "reset", "--hard", "HEAD"],
        ["git", "clean", "-fd"],
    ]


def test_reset_working_tree_raises_on_reset_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "reset", "--hard", "HEAD"], exit_code=1, stderr="fatal: reset error")

    with pytest.raises(GitError, match="reset"):
        asyncio.run(git_ops.reset_working_tree())


def test_reset_working_tree_raises_on_clean_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "reset", "--hard", "HEAD"], exit_code=0)
    fake_runner.register(["git", "clean", "-fd"], exit_code=1, stderr="fatal: clean error")

    with pytest.raises(GitError, match="clean"):
        asyncio.run(git_ops.reset_working_tree())


# --- Composition with GitClient ---

def test_git_operations_with_git_client(
    fake_runner: FakeCommandRunner,
) -> None:
    client = GitClient(runner=fake_runner)
    ops = GitOperations(runner=client)

    fake_runner.register(["git", "status", "--porcelain"], stdout="")
    assert asyncio.run(ops.check_clean_working_tree()) is True


# --- remove_path ---

def test_remove_path_success(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "rm", "-r", "docs/tickets/02-queue"], exit_code=0)
    asyncio.run(git_ops.remove_path("docs/tickets/02-queue", recursive=True))

    assert fake_runner.commands == [["git", "rm", "-r", "docs/tickets/02-queue"]]


def test_remove_path_normalizes_absolute_path_within_cwd(
    fake_runner: FakeCommandRunner,
    tmp_path: Path,
) -> None:
    ops = GitOperations(runner=fake_runner, cwd=tmp_path)
    target = tmp_path / "docs" / "specs" / "spec.md"

    fake_runner.register(["git", "rm", "docs/specs/spec.md"], exit_code=0)
    asyncio.run(ops.remove_path(target, recursive=False))

    assert fake_runner.commands == [["git", "rm", "docs/specs/spec.md"]]


def test_remove_path_raises_on_git_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(
        ["git", "rm", "-r", "docs/tickets/unknown"],
        exit_code=128,
        stderr="fatal: pathspec 'docs/tickets/unknown' did not match any files",
    )

    with pytest.raises(GitError, match="Failed to remove path"):
        asyncio.run(git_ops.remove_path("docs/tickets/unknown", recursive=True))


# --- commit_chore ---

def test_commit_chore_authors_chore_commit(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "add", "."], exit_code=0)
    fake_runner.register(["git", "commit", "-m"], exit_code=0)
    fake_runner.register(["git", "rev-parse", "HEAD"], stdout="c" * 40 + "\n")

    sha = asyncio.run(
        git_ops.commit_chore(
            scope="queue",
            title="Clean up 02-queue-and-tickets tickets, gotchas, and spec",
            changes=[
                "Archive 02-queue-and-tickets tickets and spec to untracked storage",
                "Remove tickets and spec from git tracking",
                "Reset gotchas to skeleton",
            ],
        )
    )

    assert sha == "c" * 40
    commit_invocations = [
        inv for inv in fake_runner.invocations if inv.cmd[:2] == ["git", "commit"]
    ]
    assert len(commit_invocations) == 1
    commit_msg = commit_invocations[0].cmd[3]
    assert commit_msg.startswith("chore(queue): Clean up 02-queue-and-tickets tickets, gotchas, and spec")
    assert "- Archive 02-queue-and-tickets tickets and spec to untracked storage" in commit_msg
    assert "- Reset gotchas to skeleton" in commit_msg
    assert not any(line.endswith(".") for line in commit_msg.splitlines() if line.startswith("- "))


# --- status_porcelain ---

def test_status_porcelain_returns_stdout(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], stdout=" M runner/application/git_operations.py\n")
    stdout = asyncio.run(git_ops.status_porcelain())

    assert stdout == " M runner/application/git_operations.py\n"
    assert fake_runner.commands == [["git", "status", "--porcelain"]]


def test_status_porcelain_raises_on_git_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "status", "--porcelain"], exit_code=128, stderr="fatal: not a git repository")
    with pytest.raises(GitError, match="status"):
        asyncio.run(git_ops.status_porcelain())


# --- diff_stat ---

def test_diff_stat_returns_stdout(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "diff", "--stat"], stdout=" file.py | 2 +-\n 1 file changed\n")
    stdout = asyncio.run(git_ops.diff_stat())

    assert stdout == " file.py | 2 +-\n 1 file changed\n"
    assert fake_runner.commands == [["git", "diff", "--stat"]]


def test_diff_stat_raises_on_git_failure(
    git_ops: GitOperations,
    fake_runner: FakeCommandRunner,
) -> None:
    fake_runner.register(["git", "diff", "--stat"], exit_code=128, stderr="fatal: git diff failed")
    with pytest.raises(GitError, match="diff"):
        asyncio.run(git_ops.diff_stat())
