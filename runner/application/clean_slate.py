"""CleanSlateArchiver interactor orchestrating ephemeral queue archival, removal, and chore commits."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
import inspect
from pathlib import Path
import shutil
from typing import Any

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.adapters.markdown.gotchas_store import DEFAULT_GOTCHAS_PATH, GotchasStore
from runner.application.git_operations import GitOperations
from runner.domain.config import (
    VALID_CLEAN_SLATE_POLICIES,
    LifecycleConfig,
    RunnerConfig,
)
from runner.domain.exceptions import CleanSlateError, GitError

DEFAULT_TICKETS_DIR = Path("docs/tickets")
DEFAULT_SPECS_DIR = Path("docs/specs")
DEFAULT_ARCHIVE_ROOT = Path(".agent/archive")


def default_terminal_confirmation(prompt: str) -> bool:
    """Default interactive terminal prompt honoring [Y/n] conventions."""
    try:
        response = input(prompt).strip().lower()
        return response in ("y", "yes", "")
    except (EOFError, KeyboardInterrupt, OSError):
        return False


@dataclass(frozen=True)
class CleanSlateResult:
    """Outcome of a clean-slate archival execution."""

    cleaned: bool
    commit_sha: str | None = None
    archive_dir: Path | None = None

    def __bool__(self) -> bool:
        return self.cleaned

    def __eq__(self, other: object) -> bool:
        if isinstance(other, bool):
            return self.cleaned == other
        return super().__eq__(other)


class CleanSlateArchiver:
    """Interactor coordinating archival, git removal, gotchas reset, and chore commits."""

    def __init__(
        self,
        git_operations: GitOperations | None = None,
        confirmation_callback: Callable[[str], bool | Awaitable[bool]] | None = None,
        archive_root: Path | str | None = None,
        tickets_dir: Path | str | None = None,
        specs_dir: Path | str | None = None,
        gotchas_store: GotchasStore | None = None,
        cwd: Path | None = None,
        printer: Callable[[str], None] = print,
    ) -> None:
        self._cwd = cwd
        self._git_operations = git_operations or GitOperations(
            runner=SubprocessRunner(), cwd=self._cwd
        )
        self._confirmation_callback = (
            confirmation_callback
            if confirmation_callback is not None
            else default_terminal_confirmation
        )

        if archive_root is not None:
            self._archive_root = Path(archive_root)
        elif self._cwd:
            self._archive_root = self._cwd / DEFAULT_ARCHIVE_ROOT
        else:
            self._archive_root = DEFAULT_ARCHIVE_ROOT

        if tickets_dir is not None:
            self._tickets_dir = Path(tickets_dir)
        elif self._cwd:
            self._tickets_dir = self._cwd / DEFAULT_TICKETS_DIR
        else:
            self._tickets_dir = DEFAULT_TICKETS_DIR

        if specs_dir is not None:
            self._specs_dir = Path(specs_dir)
        elif self._cwd:
            self._specs_dir = self._cwd / DEFAULT_SPECS_DIR
        else:
            self._specs_dir = DEFAULT_SPECS_DIR

        if gotchas_store is not None:
            self._gotchas_store = gotchas_store
        elif self._cwd:
            self._gotchas_store = GotchasStore(path=self._cwd / DEFAULT_GOTCHAS_PATH)
        else:
            self._gotchas_store = GotchasStore(path=DEFAULT_GOTCHAS_PATH)

        self._printer = printer

    @property
    def git_operations(self) -> GitOperations:
        """Underlying GitOperations interactor."""
        return self._git_operations

    @property
    def archive_root(self) -> Path:
        """Target untracked archive root directory (.agent/archive)."""
        return self._archive_root

    @property
    def tickets_dir(self) -> Path:
        """Root tickets queue directory (docs/tickets)."""
        return self._tickets_dir

    @property
    def specs_dir(self) -> Path:
        """Root specs directory (docs/specs)."""
        return self._specs_dir

    @property
    def gotchas_store(self) -> GotchasStore:
        """Backing gotchas store."""
        return self._gotchas_store

    @property
    def confirmation_callback(self) -> Callable[[str], bool | Awaitable[bool]]:
        """Injected confirmation callback seam."""
        return self._confirmation_callback

    def _resolve_spec_paths(
        self, spec_slug: str, spec_path: Path | str | None = None
    ) -> tuple[Path, Path]:
        """Resolve paths for tickets folder and spec file."""
        spec_tickets_dir = self._tickets_dir / spec_slug
        if spec_path is not None:
            spec_file = Path(spec_path)
            if not spec_file.is_absolute() and self._cwd:
                spec_file = self._cwd / spec_file
        else:
            spec_file = self._specs_dir / f"{spec_slug}.md"
        return spec_tickets_dir, spec_file

    def archive_spec(
        self,
        spec_slug: str,
        spec_path: Path | str | None = None,
    ) -> Path:
        """Back up completed tickets and spec file to untracked .agent/archive/<spec-slug>/.

        Args:
            spec_slug: Target specification identifier (e.g. '02-queue-and-tickets').
            spec_path: Optional explicit path to spec file.

        Returns:
            Path to the populated archive directory.

        Raises:
            FileNotFoundError: If tickets directory does not exist on disk.
        """
        spec_tickets_dir, spec_file = self._resolve_spec_paths(spec_slug, spec_path)
        if not spec_tickets_dir.exists():
            raise FileNotFoundError(
                f"Tickets directory not found for spec slug '{spec_slug}': {spec_tickets_dir}"
            )

        dest_dir = self._archive_root / spec_slug
        dest_dir.parent.mkdir(parents=True, exist_ok=True)

        # Copy all tickets (including completed/)
        shutil.copytree(spec_tickets_dir, dest_dir, dirs_exist_ok=True)

        # Copy spec file if it exists
        if spec_file.is_file():
            shutil.copy2(spec_file, dest_dir / spec_file.name)

        return dest_dir

    async def clean_slate(
        self,
        spec_slug: str,
        policy: str | LifecycleConfig | RunnerConfig = "interactive",
        spec_path: Path | str | None = None,
        printer: Callable[[str], None] | None = None,
    ) -> CleanSlateResult:
        """Execute the ephemeral clean-slate archival and chore commit flow.

        Honors lifecycle.clean_slate policy:
          - 'never': Silently skip, leave working tree untouched.
          - 'always': Proceed with backup, removal, and commit without prompting.
          - 'interactive': Prompt [Y/n] via confirmation callback. Proceed if confirmed.

        Args:
            spec_slug: Target spec identifier (e.g. '02-queue-and-tickets').
            policy: Clean slate policy ('interactive', 'always', 'never', or config object).
            spec_path: Optional explicit path to spec file.
            printer: Optional output display callback.

        Returns:
            CleanSlateResult indicating whether clean-slate was executed.

        Raises:
            ValueError: If policy is unrecognized.
            FileNotFoundError: If target tickets directory does not exist.
            GitError: If git removal or committing fails.
            TicketFormatError: If gotchas reset fails.
        """
        out = printer or self._printer

        if isinstance(policy, RunnerConfig):
            active_policy = policy.lifecycle.clean_slate
        elif isinstance(policy, LifecycleConfig):
            active_policy = policy.clean_slate
        elif isinstance(policy, str):
            active_policy = policy.strip().lower()
        else:
            raise ValueError(f"Unsupported clean slate policy type: {type(policy)}")

        if active_policy not in VALID_CLEAN_SLATE_POLICIES:
            raise ValueError(
                f"Unsupported clean slate policy: '{active_policy}'. "
                f"Must be one of {sorted(VALID_CLEAN_SLATE_POLICIES)}"
            )

        if active_policy == "never":
            return CleanSlateResult(cleaned=False)

        if active_policy == "interactive":
            prompt = (
                f"\n[CleanSlate] Spec queue '{spec_slug}' is complete.\n"
                f"Wipe completed tickets and spec for a clean slate? [Y/n]: "
            )
            if inspect.iscoroutinefunction(self._confirmation_callback):
                confirmed = await self._confirmation_callback(prompt)
            else:
                res = self._confirmation_callback(prompt)
                if asyncio.iscoroutine(res):
                    confirmed = await res
                else:
                    confirmed = bool(res)

            if not confirmed:
                out(f"[CleanSlate] Clean slate declined for '{spec_slug}'. Preserving working tree.")
                return CleanSlateResult(cleaned=False)

        # 1. Back up before removing (an interruption must not lose history)
        spec_tickets_dir, spec_file = self._resolve_spec_paths(spec_slug, spec_path)
        out(f"[CleanSlate] Backing up '{spec_slug}' to untracked '{self._archive_root / spec_slug}'...")
        archive_dir = self.archive_spec(spec_slug=spec_slug, spec_path=spec_path)

        # 2. Remove tickets and spec from git tracking via git rm
        out(f"[CleanSlate] Removing '{spec_slug}' tickets and spec from git tracking...")
        await self._git_operations.remove_path(spec_tickets_dir, recursive=True)
        if spec_file.is_file():
            await self._git_operations.remove_path(spec_file, recursive=False)

        # 3. Reset gotchas.md to its skeleton in the same commit
        out("[CleanSlate] Resetting gotchas.md to initial skeleton...")
        self._gotchas_store.reset_to_skeleton()

        # 4. Author exactly one chore commit
        title = f"Clean up {spec_slug} tickets, gotchas, and spec"
        changes = [
            f"Archive {spec_slug} tickets and spec to untracked storage",
            f"Remove {spec_slug} tickets and spec from git tracking",
            "Reset global gotchas to skeleton",
        ]
        commit_sha = await self._git_operations.commit_chore(
            scope="queue",
            title=title,
            changes=changes,
        )
        out(f"[CleanSlate] Authored chore commit: chore(queue): {title}")

        return CleanSlateResult(
            cleaned=True,
            commit_sha=commit_sha,
            archive_dir=archive_dir,
        )

    async def archive_and_clean(
        self,
        spec_slug: str,
        policy: str | LifecycleConfig | RunnerConfig = "interactive",
        spec_path: Path | str | None = None,
        printer: Callable[[str], None] | None = None,
    ) -> CleanSlateResult:
        """Alias for clean_slate method."""
        return await self.clean_slate(
            spec_slug=spec_slug,
            policy=policy,
            spec_path=spec_path,
            printer=printer,
        )
