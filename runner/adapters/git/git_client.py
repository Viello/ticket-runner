"""Git client adapter wrapping git CLI commands through CommandRunner."""

from __future__ import annotations

from pathlib import Path

from runner.domain.exceptions import GitError
from runner.ports.command_runner import CommandResult, CommandRunner


class GitClient:
    """Adapter wrapping core Git CLI commands via the CommandRunner port."""

    def __init__(self, runner: CommandRunner, cwd: Path | None = None) -> None:
        self._runner = runner
        self._cwd = cwd

    @property
    def runner(self) -> CommandRunner:
        """Underlying CommandRunner port instance."""
        return self._runner

    @property
    def cwd(self) -> Path | None:
        """Configured working directory for Git commands."""
        return self._cwd

    async def _run(self, args: list[str], cwd: Path | None = None) -> CommandResult:
        target_cwd = cwd if cwd is not None else self._cwd
        return await self._runner.run(["git"] + args, cwd=target_cwd)

    async def status_porcelain(self, cwd: Path | None = None) -> CommandResult:
        """Run `git status --porcelain` to inspect working tree cleanliness."""
        return await self._run(["status", "--porcelain"], cwd=cwd)

    async def symbolic_ref(
        self,
        ref: str = "HEAD",
        short: bool = True,
        cwd: Path | None = None,
    ) -> CommandResult:
        """Run `git symbolic-ref` to resolve a symbolic ref."""
        args = ["symbolic-ref"]
        if short:
            args.append("--short")
        args.append(ref)
        return await self._run(args, cwd=cwd)

    async def get_current_branch(self, cwd: Path | None = None) -> str:
        """Get the active branch name via `git symbolic-ref --short HEAD`.

        Raises:
            GitError: If the command fails or HEAD is detached.
        """
        result = await self.symbolic_ref(ref="HEAD", short=True, cwd=cwd)
        if not result.success:
            err_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise GitError(f"Failed to get current branch: {err_msg}")
        return result.stdout.strip()

    async def checkout(self, branch: str, cwd: Path | None = None) -> CommandResult:
        """Run `git checkout <branch>` to switch to an existing branch."""
        return await self._run(["checkout", branch], cwd=cwd)

    async def checkout_new_branch(
        self,
        branch: str,
        cwd: Path | None = None,
    ) -> CommandResult:
        """Run `git checkout -b <branch>` to create and switch to a new branch from HEAD."""
        return await self._run(["checkout", "-b", branch], cwd=cwd)

    async def add_all(self, cwd: Path | None = None) -> CommandResult:
        """Run `git add .` to stage all modifications and untracked files."""
        return await self._run(["add", "."], cwd=cwd)

    async def commit(self, message: str, cwd: Path | None = None) -> CommandResult:
        """Run `git commit -m <message>` to author a commit."""
        return await self._run(["commit", "-m", message], cwd=cwd)

    async def rev_parse(
        self,
        ref: str = "HEAD",
        cwd: Path | None = None,
    ) -> CommandResult:
        """Run `git rev-parse <ref>` to resolve an object name."""
        return await self._run(["rev-parse", ref], cwd=cwd)

    async def get_head_sha(self, cwd: Path | None = None) -> str:
        """Get the 40-character commit SHA of current HEAD via `git rev-parse HEAD`.

        Raises:
            GitError: If HEAD cannot be resolved.
        """
        result = await self.rev_parse("HEAD", cwd=cwd)
        if not result.success:
            err_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise GitError(f"Failed to get HEAD commit SHA: {err_msg}")
        return result.stdout.strip()

    async def reset_hard(
        self,
        ref: str = "HEAD",
        cwd: Path | None = None,
    ) -> CommandResult:
        """Run `git reset --hard <ref>` to reset working tree and index."""
        return await self._run(["reset", "--hard", ref], cwd=cwd)

    async def clean(
        self,
        flags: str = "-fd",
        cwd: Path | None = None,
    ) -> CommandResult:
        """Run `git clean <flags>` to remove untracked files and directories."""
        return await self._run(["clean", flags], cwd=cwd)
