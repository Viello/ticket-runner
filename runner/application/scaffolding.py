"""Application service for sniffing project heuristics and scaffolding configuration."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any

from runner.domain.scaffolding import ProjectHeuristics

__all__ = ["ProjectHeuristics", "ProjectSniffer"]


def _is_safe_file(path: Path, root: Path) -> bool:
    """Check if file exists, is a regular file, and resides strictly within root."""
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
        if not resolved.is_relative_to(resolved_root):
            return False
        return path.is_file()
    except (ValueError, OSError):
        return False


def _is_safe_dir(path: Path, root: Path) -> bool:
    """Check if directory exists, is a directory, and resides strictly within root."""
    try:
        resolved = path.resolve()
        resolved_root = root.resolve()
        if not resolved.is_relative_to(resolved_root):
            return False
        return path.is_dir()
    except (ValueError, OSError):
        return False


def _safe_read_text(path: Path, root: Path, max_bytes: int = 1_048_576) -> str | None:
    """Safely read text file content up to max_bytes without escaping root."""
    if not _is_safe_file(path, root):
        return None
    try:
        size = path.stat().st_size
        if size > max_bytes:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                return f.read(max_bytes)
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


class ProjectSniffer:
    """Pure application service that inspects a project directory for stack heuristics."""

    def sniff(self, project_dir: Path) -> ProjectHeuristics:
        """Inspect target project directory and return detected project heuristics."""
        target_dir = Path(project_dir)
        resolved_root = target_dir.resolve()
        dir_name = resolved_root.name.strip() if resolved_root.name.strip() else "project"

        detected_stack = "unknown"
        test_cmd = ""
        build_cmd = ""
        manifest_name: str | None = None

        # 1. Check Python
        pyproject_path = target_dir / "pyproject.toml"
        setup_py_path = target_dir / "setup.py"
        requirements_path = target_dir / "requirements.txt"

        if (
            _is_safe_file(pyproject_path, target_dir)
            or _is_safe_file(setup_py_path, target_dir)
            or _is_safe_file(requirements_path, target_dir)
        ):
            detected_stack = "python"
            test_cmd = "python -m pytest"
            build_cmd = ""

            pyproject_content = _safe_read_text(pyproject_path, target_dir)
            if pyproject_content:
                match = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', pyproject_content, re.MULTILINE)
                if match:
                    manifest_name = match.group(1).strip()

        # 2. Check Node.js
        elif _is_safe_file(target_dir / "package.json", target_dir):
            detected_stack = "node"

            # Detect package manager via lockfiles
            if _is_safe_file(target_dir / "pnpm-lock.yaml", target_dir):
                pm = "pnpm"
            elif _is_safe_file(target_dir / "yarn.lock", target_dir):
                pm = "yarn"
            elif (
                _is_safe_file(target_dir / "bun.lockb", target_dir)
                or _is_safe_file(target_dir / "bun.lock", target_dir)
            ):
                pm = "bun"
            else:
                pm = "npm"

            package_json_content = _safe_read_text(target_dir / "package.json", target_dir)
            package_data: dict[str, Any] = {}
            if package_json_content:
                try:
                    parsed = json.loads(package_json_content)
                    if isinstance(parsed, dict):
                        package_data = parsed
                except Exception:
                    package_data = {}

            pkg_name = package_data.get("name")
            if isinstance(pkg_name, str) and pkg_name.strip():
                manifest_name = pkg_name.strip()

            scripts = package_data.get("scripts")
            if not isinstance(scripts, dict):
                scripts = {}

            test_cmd = f"{pm} test"
            if "build" in scripts:
                if pm == "yarn":
                    build_cmd = "yarn build"
                else:
                    build_cmd = f"{pm} run build"
            else:
                build_cmd = ""

        # 3. Check Rust
        elif _is_safe_file(target_dir / "Cargo.toml", target_dir):
            detected_stack = "rust"
            test_cmd = "cargo test"
            build_cmd = "cargo build"

            cargo_content = _safe_read_text(target_dir / "Cargo.toml", target_dir)
            if cargo_content:
                match = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', cargo_content, re.MULTILINE)
                if match:
                    manifest_name = match.group(1).strip()

        # 4. Check Go
        elif _is_safe_file(target_dir / "go.mod", target_dir):
            detected_stack = "go"
            test_cmd = "go test ./..."
            build_cmd = ""

            go_mod_content = _safe_read_text(target_dir / "go.mod", target_dir)
            if go_mod_content:
                match = re.search(r'^\s*module\s+([^\s\r\n]+)', go_mod_content, re.MULTILINE)
                if match:
                    mod_path = match.group(1).strip()
                    manifest_name = mod_path.split("/")[-1]

        # Resolve project name
        project_name = manifest_name if manifest_name else dir_name

        # Detect git base branch
        base_branch = self._detect_git_base_branch(target_dir)

        return ProjectHeuristics(
            name=project_name,
            detected_stack=detected_stack,
            test_cmd=test_cmd,
            build_cmd=build_cmd,
            base_branch=base_branch,
            branch="agent/ticket-runner",
            provider="opencode",
        )

    def _detect_git_base_branch(self, target_dir: Path) -> str:
        """Detect git base branch ('main' or 'master') cleanly handling detached HEAD or empty repos."""
        git_dir = target_dir / ".git"
        if not _is_safe_dir(git_dir, target_dir):
            return "main"

        # 1. Direct filesystem inspection of .git/HEAD
        head_content = _safe_read_text(git_dir / "HEAD", target_dir)
        if head_content:
            head_str = head_content.strip()
            if head_str.startswith("ref: refs/heads/"):
                ref_name = head_str.split("ref: refs/heads/", 1)[1].strip()
                if ref_name in ("main", "master"):
                    return ref_name

        # Check local refs files if present
        if _is_safe_file(git_dir / "refs" / "heads" / "main", target_dir):
            return "main"
        if _is_safe_file(git_dir / "refs" / "heads" / "master", target_dir):
            return "master"

        # 2. Try git CLI with strict timeout if available
        try:
            # Check origin/HEAD
            res = subprocess.run(
                ["git", "-C", str(target_dir), "rev-parse", "--abbrev-ref", "origin/HEAD"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if res.returncode == 0:
                out = res.stdout.strip()
                if "/" in out:
                    out = out.split("/", 1)[1]
                if out in ("main", "master"):
                    return out

            # Check local branches (main vs master)
            res = subprocess.run(
                ["git", "-C", str(target_dir), "branch", "--list", "main", "master"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if res.returncode == 0:
                branches = [
                    b.strip().lstrip("* ").strip()
                    for b in res.stdout.splitlines()
                    if b.strip()
                ]
                if "main" in branches:
                    return "main"
                if "master" in branches:
                    return "master"

            # Check symbolic ref HEAD
            res = subprocess.run(
                ["git", "-C", str(target_dir), "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            if res.returncode == 0:
                branch = res.stdout.strip()
                if branch in ("main", "master"):
                    return branch
        except Exception:
            pass

        return "main"
