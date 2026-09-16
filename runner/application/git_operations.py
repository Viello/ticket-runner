"""GitOperations interactor managing working tree isolation and commits."""

from __future__ import annotations

from pathlib import Path
import re

from runner.adapters.git.git_client import GitClient
from runner.domain.exceptions import GitError
from runner.ports.command_runner import CommandRunner


class GitOperations:
    """Application interactor orchestrating Git isolation workflows."""

    def __init__(
        self,
        runner: CommandRunner | GitClient,
        commit_prefix: str = "feat",
        cwd: Path | None = None,
    ) -> None:
        if isinstance(runner, GitClient):
            self._client = runner
            self._cwd = runner.cwd or cwd
        else:
            self._cwd = cwd
            self._client = GitClient(runner=runner, cwd=cwd)
        self._commit_prefix = commit_prefix

    @property
    def client(self) -> GitClient:
        """Underlying GitClient adapter instance."""
        return self._client

    @property
    def runner(self) -> CommandRunner:
        """Underlying CommandRunner port instance."""
        return self._client.runner

    @property
    def cwd(self) -> Path | None:
        """Target working directory."""
        return self._cwd

    @property
    def commit_prefix(self) -> str:
        """Default conventional commit prefix."""
        return self._commit_prefix

    async def status_porcelain(self, cwd: Path | None = None) -> str:
        """Run `git status --porcelain` and return raw stdout.

        Returns:
            The raw stdout output of `git status --porcelain`.

        Raises:
            GitError: If the status command fails (e.g. not a git repository).
        """
        target_cwd = cwd if cwd is not None else self._cwd
        result = await self._client.status_porcelain(cwd=target_cwd)
        if not result.success:
            err_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise GitError(f"Failed to run git status --porcelain: {err_msg}")
        return result.stdout

    async def diff_stat(self, cwd: Path | None = None) -> str:
        """Run `git diff --stat` and return raw stdout.

        Returns:
            The raw stdout output of `git diff --stat`.

        Raises:
            GitError: If the diff command fails.
        """
        target_cwd = cwd if cwd is not None else self._cwd
        result = await self._client.diff_stat(cwd=target_cwd)
        if not result.success:
            err_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise GitError(f"Failed to run git diff --stat: {err_msg}")
        return result.stdout

    async def check_clean_working_tree(self) -> bool:
        """Check if the git working tree is clean with zero uncommitted changes.

        Returns:
            True if `git status --porcelain` produces empty output, False otherwise.

        Raises:
            GitError: If the status command fails (e.g. not a git repository).
        """
        stdout = await self.status_porcelain()
        return len(stdout.strip()) == 0

    async def get_current_branch(self) -> str:
        """Get the name of the currently checked out branch.

        Raises:
            GitError: If resolving HEAD symbolic ref fails.
        """
        return await self._client.get_current_branch(cwd=self._cwd)

    async def ensure_branch(self, branch_name: str = "agent/ticket-runner") -> None:
        """Ensure the repository is checked out to the designated isolation branch.

        Strictly verifies that the working tree is clean first. If already on
        branch_name, does nothing. Otherwise, attempts to checkout existing branch
        or creates it from current HEAD.

        Args:
            branch_name: Target branch name (default "agent/ticket-runner").

        Raises:
            GitError: If the working tree is dirty or switching branch fails.
        """
        is_clean = await self.check_clean_working_tree()
        if not is_clean:
            raise GitError(
                f"Working tree has uncommitted or untracked changes. "
                f"Cannot ensure clean branch '{branch_name}'."
            )

        current_branch = await self.get_current_branch()
        if current_branch == branch_name:
            return

        checkout_res = await self._client.checkout(branch_name, cwd=self._cwd)
        if checkout_res.success:
            return

        create_res = await self._client.checkout_new_branch(branch_name, cwd=self._cwd)
        if not create_res.success:
            err_msg = create_res.stderr.strip() or create_res.stdout.strip() or "unknown error"
            raise GitError(f"Failed to checkout or create branch '{branch_name}': {err_msg}")

    async def commit_ticket(
        self,
        scope: str,
        title: str,
        changes: list[str],
        commit_prefix: str | None = None,
    ) -> str:
        """Stage modified files, author conventional commit, and return commit SHA.

        Enforces that no ticket numbers appear in the commit title or body,
        and that changes are formatted as imperative bullet points without trailing periods.

        Args:
            scope: Architectural layer or subsystem (e.g. 'adapters', 'domain').
            title: Imperative commit title describing the change.
            changes: List of bulleted change descriptions.
            commit_prefix: Optional override for the conventional commit type (e.g. 'fix').

        Returns:
            The full 40-character commit SHA of the authored commit.

        Raises:
            GitError: If scope is invalid, staging fails, or committing fails.
        """
        clean_scope = scope.strip()
        if re.match(r"^T\d{3,4}$", clean_scope, flags=re.IGNORECASE):
            raise GitError(
                f"Invalid scope '{scope}': scope must name an architectural layer or "
                f"subsystem, never a ticket number."
            )

        # Sanitize title: strip leading ticket ID prefixes like 'T003 — ' or 'T003: '
        clean_title = re.sub(r"^(?:#\s*)?(?:T\d{3,4}|#\d+)\s*[-—:]*\s*", "", title.strip())
        # Remove any remaining ticket references (e.g. 'T003')
        clean_title = re.sub(r"\bT\d{3,4}\b", "", clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r"\s+", " ", clean_title).strip().rstrip(".")

        # Sanitize bulleted changes
        formatted_changes: list[str] = []
        for change in changes:
            c = re.sub(r"\bT\d{3,4}\b", "", change, flags=re.IGNORECASE)
            c = re.sub(r"\(\s*\)", "", c)
            c = c.strip().lstrip("-* ").rstrip(".")
            c = re.sub(r"\s+", " ", c).strip()
            if c:
                formatted_changes.append(f"- {c}")

        prefix = commit_prefix or self._commit_prefix
        header = f"{prefix}({clean_scope}): {clean_title}"

        if formatted_changes:
            commit_message = f"{header}\n\n" + "\n".join(formatted_changes)
        else:
            commit_message = header

        add_res = await self._client.add_all(cwd=self._cwd)
        if not add_res.success:
            err_msg = add_res.stderr.strip() or add_res.stdout.strip() or "unknown error"
            raise GitError(f"Failed to stage files with git add .: {err_msg}")

        commit_res = await self._client.commit(commit_message, cwd=self._cwd)
        if not commit_res.success:
            err_msg = commit_res.stderr.strip() or commit_res.stdout.strip() or "unknown error"
            raise GitError(f"Failed to author git commit: {err_msg}")

        return await self._client.get_head_sha(cwd=self._cwd)

    async def reset_working_tree(self) -> None:
        """Reset working tree and remove untracked files back to pristine state.

        Executes `git reset --hard HEAD` and `git clean -fd`.

        Raises:
            GitError: If either reset or clean command fails.
        """
        reset_res = await self._client.reset_hard("HEAD", cwd=self._cwd)
        if not reset_res.success:
            err_msg = reset_res.stderr.strip() or reset_res.stdout.strip() or "unknown error"
            raise GitError(f"Failed to reset working tree with git reset --hard HEAD: {err_msg}")

        clean_res = await self._client.clean("-fd", cwd=self._cwd)
        if not clean_res.success:
            err_msg = clean_res.stderr.strip() or clean_res.stdout.strip() or "unknown error"
            raise GitError(f"Failed to clean working tree with git clean -fd: {err_msg}")

    async def remove_path(
        self,
        path: str | Path,
        recursive: bool = False,
        force: bool = False,
    ) -> None:
        """Remove a path from the working tree and git index via git rm.

        Args:
            path: Path to file or directory to remove.
            recursive: Remove directories recursively (-r).
            force: Override up-to-date checks (-f).

        Raises:
            GitError: If git rm command fails (e.g. path is untracked or dirty).
        """
        p = Path(path)
        if self._cwd is not None and p.is_absolute():
            try:
                clean_path = p.relative_to(self._cwd).as_posix()
            except ValueError:
                clean_path = p.as_posix()
        else:
            clean_path = p.as_posix()

        result = await self._client.rm(clean_path, recursive=recursive, force=force, cwd=self._cwd)
        if not result.success:
            err_msg = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise GitError(f"Failed to remove path '{clean_path}' from git: {err_msg}")

    async def commit_chore(
        self,
        scope: str,
        title: str,
        changes: list[str] | None = None,
    ) -> str:
        """Stage modified files, author conventional chore commit, and return commit SHA.

        Enforces conventional commit format 'chore(<scope>): <clean_title>' without ticket numbers.

        Args:
            scope: Architectural layer or subsystem (e.g. 'queue').
            title: Imperative title of the chore commit.
            changes: Optional list of bulleted change descriptions.

        Returns:
            The full 40-character commit SHA of the authored chore commit.

        Raises:
            GitError: If scope is invalid, staging fails, or committing fails.
        """
        return await self.commit_ticket(
            scope=scope,
            title=title,
            changes=list(changes) if changes is not None else [],
            commit_prefix="chore",
        )
