"""Concrete GitHubSkillsClient adapter for remote skills catalog synchronization."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import concurrent.futures
import inspect
import io
from pathlib import Path
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import Any

from runner.adapters.cli.subprocess_runner import SubprocessRunner
from runner.ports.command_runner import CommandResult, CommandRunner
from runner.ports.skills_client import SkillsClient, SkillsSyncError, SkillsSyncResult

REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_PATTERN = re.compile(r"^[A-Za-z0-9_./-]+$")


def _run_sync(coro_or_val: Any) -> Any:
    """Execute a coroutine synchronously, handling running event loops safely."""
    if not inspect.iscoroutine(coro_or_val):
        return coro_or_val

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro_or_val).result()
    return asyncio.run(coro_or_val)


def _default_download(url: str, timeout: float = 30.0) -> bytes:
    """Default HTTP download fetching remote content into memory."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TicketRunner-SkillsClient/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise urllib.error.HTTPError(
                url, resp.status, f"HTTP status {resp.status}", resp.headers, None
            )
        return resp.read()


def _are_dirs_identical(dir1: Path, dir2: Path) -> bool:
    """Check if two directory trees have identical file structures and contents."""
    files1 = {
        p.relative_to(dir1).as_posix(): p
        for p in dir1.rglob("*")
        if p.is_file() and not p.name.endswith(".pyc") and "__pycache__" not in p.parts
    }
    files2 = {
        p.relative_to(dir2).as_posix(): p
        for p in dir2.rglob("*")
        if p.is_file() and not p.name.endswith(".pyc") and "__pycache__" not in p.parts
    }

    if set(files1.keys()) != set(files2.keys()):
        return False

    for rel_path, p1 in files1.items():
        p2 = files2[rel_path]
        try:
            if p1.stat().st_size != p2.stat().st_size:
                return False
            if p1.read_bytes() != p2.read_bytes():
                return False
        except OSError:
            return False

    return True


class GitHubSkillsClient:
    """Concrete skills synchronization adapter downloading catalogs from GitHub."""

    def __init__(
        self,
        command_runner: CommandRunner | None = None,
        download_fn: Callable[[str], bytes] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._command_runner = command_runner or SubprocessRunner()
        self._timeout = timeout
        self._download_fn = download_fn or (lambda url: _default_download(url, timeout=self._timeout))

    def _extract_tar_safely(self, tar_bytes: bytes, target_dir: Path) -> None:
        """Inspect and safely extract a tar.gz archive into target_dir preventing Zip Slip."""
        try:
            tf = tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*")
        except Exception as exc:
            raise ValueError(f"Corrupted or invalid tar archive: {exc}") from exc

        resolved_target = target_dir.resolve()
        members = tf.getmembers()

        # Step 1: Security audit of all member paths (Zip Slip defense)
        for member in members:
            name = member.name
            # Check for absolute path or drive letter
            if name.startswith(("/", "\\")) or (len(name) > 1 and name[1] == ":"):
                raise SkillsSyncError(
                    f"Security: Path traversal detected in archive member '{name}': absolute path forbidden"
                )

            p = Path(name)
            if ".." in p.parts:
                raise SkillsSyncError(
                    f"Security: Path traversal detected in archive member '{name}': parent reference '..' forbidden"
                )

            if member.islnk() or member.issym():
                link = member.linkname
                if link.startswith(("/", "\\")) or ".." in Path(link).parts:
                    raise SkillsSyncError(
                        f"Security: Dangerous link detected in archive member '{name}' -> '{link}'"
                    )

            dest = (resolved_target / name).resolve()
            if not dest.is_relative_to(resolved_target):
                raise SkillsSyncError(
                    f"Security: Zip Slip detected in archive member '{name}' escaping target directory"
                )

        # Step 2: Extract regular files and directories safely
        for member in members:
            dest = resolved_target / member.name
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.isreg():
                dest.parent.mkdir(parents=True, exist_ok=True)
                f_in = tf.extractfile(member)
                if f_in is not None:
                    with f_in:
                        with dest.open("wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)

    def _clone_fallback(self, repo: str, ref: str, clone_dir: Path) -> None:
        """Fallback to git clone via CommandRunner if HTTP download fails."""
        cmd = [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            ref,
            f"https://github.com/{repo}.git",
            str(clone_dir),
        ]
        coro = self._command_runner.run(cmd)
        result: CommandResult = _run_sync(coro)
        if not result.success:
            raise RuntimeError(
                f"git clone failed ({result.exit_code}): {result.stderr or result.stdout}"
            )

    def _discover_skills(self, root: Path) -> dict[str, Path]:
        """Discover all skill directories containing a SKILL.md under root."""
        skills: dict[str, Path] = {}
        for skill_md in root.rglob("SKILL.md"):
            skill_dir = skill_md.parent
            if skill_dir.is_dir():
                skills[skill_dir.name] = skill_dir
        return skills

    def sync_skills(
        self,
        project_dir: Path,
        repo: str = "Viello/agent-skills",
        ref: str = "main",
        force: bool = False,
    ) -> SkillsSyncResult:
        """Synchronize remote skills catalog into <project_dir>/.agents/skills/."""
        target_dir = Path(project_dir).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            raise SkillsSyncError(
                f"Target project directory '{project_dir}' does not exist or is not a directory."
            )

        if not REPO_PATTERN.match(repo):
            raise SkillsSyncError(f"Invalid repository format '{repo}'. Expected 'owner/repo'.")

        if not REF_PATTERN.match(ref) or ref.startswith("-") or ".." in ref:
            raise SkillsSyncError(f"Invalid git ref format '{ref}'.")

        skills_dir = target_dir / ".agents" / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as td_str:
            temp_path = Path(td_str)
            staging_dir = temp_path / "incoming"
            staging_dir.mkdir(parents=True, exist_ok=True)

            url = f"https://github.com/{repo}/archive/refs/heads/{ref}.tar.gz"

            try:
                tar_bytes = self._download_fn(url)
                self._extract_tar_safely(tar_bytes, staging_dir)
            except SkillsSyncError:
                # Security violation (Zip Slip) — DO NOT FALLBACK, abort immediately!
                raise
            except Exception as http_err:
                # Network or archive error — attempt git clone fallback
                clone_dir = temp_path / "clone"
                try:
                    self._clone_fallback(repo=repo, ref=ref, clone_dir=clone_dir)
                    staging_dir = clone_dir
                except Exception as clone_err:
                    raise SkillsSyncError(
                        f"Failed to sync skills from {repo}@{ref}: HTTP download failed ({http_err}); "
                        f"git clone fallback failed ({clone_err})"
                    ) from clone_err

            incoming_skills = self._discover_skills(staging_dir)

            existing_skills = {
                d.name: d for d in skills_dir.iterdir()
                if d.is_dir()
            }

            installed: list[str] = []
            updated: list[str] = []
            preserved: list[str] = []
            errors: list[str] = []

            # 1. Custom skills not present in incoming catalog are preserved
            for name in existing_skills:
                if name not in incoming_skills:
                    preserved.append(name)

            # 2. Process incoming catalog skills
            for name, src_skill_dir in incoming_skills.items():
                dest_skill_dir = skills_dir / name
                try:
                    if name not in existing_skills:
                        shutil.copytree(src_skill_dir, dest_skill_dir)
                        installed.append(name)
                    else:
                        has_modifications = not _are_dirs_identical(src_skill_dir, dest_skill_dir)
                        if has_modifications and not force:
                            preserved.append(name)
                        else:
                            shutil.rmtree(dest_skill_dir)
                            shutil.copytree(src_skill_dir, dest_skill_dir)
                            updated.append(name)
                except OSError as err:
                    errors.append(f"Failed to synchronize skill '{name}': {err}")

        return SkillsSyncResult(
            installed_skills=tuple(sorted(installed)),
            updated_skills=tuple(sorted(updated)),
            preserved_skills=tuple(sorted(preserved)),
            errors=tuple(sorted(errors)),
        )
