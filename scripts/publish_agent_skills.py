#!/usr/bin/env python3
"""Repeatable publication and synchronization script for Viello/agent-skills repository.

Publishes the canonical reusable agent skills catalog to the remote GitHub
repository (Viello/agent-skills), generating an indexed README catalog and MIT license,
while enforcing security audits and preventing credential leaks.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from typing import Any

import yaml


FORBIDDEN_FILE_PATTERNS = [
    r"^\.env.*$",
    r"^.*\.pem$",
    r"^.*\.key$",
    r"^.*\.token$",
    r"^id_rsa.*$",
    r"^credentials\.json$",
    r"^.*\.pyc$",
    r"^\.DS_Store$",
]

SECRET_PATTERNS = [
    (r"ghp_[A-Za-z0-9_]{36,}", "GitHub personal access token (ghp)"),
    (r"gho_[A-Za-z0-9_]{36,}", "GitHub OAuth token (gho)"),
    (r"github_pat_[A-Za-z0-9_]{80,}", "GitHub fine-grained personal access token"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", "Private key block"),
    (r"(?:api[_-]?key|secret|password|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{20,}['\"]", "API credential assignment"),
]


@dataclasses.dataclass(frozen=True)
class SkillMetadata:
    name: str
    description: str
    path: pathlib.Path
    triggers: list[str] = dataclasses.field(default_factory=list)


def parse_skill_metadata(skill_dir: pathlib.Path) -> SkillMetadata:
    """Extract metadata from SKILL.md YAML frontmatter."""
    skill_md = skill_dir / "SKILL.md"
    name = skill_dir.name
    description = ""
    triggers: list[str] = []

    if skill_md.is_file():
        content = skill_md.read_text(encoding="utf-8")
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                try:
                    data = yaml.safe_load(parts[1])
                    if isinstance(data, dict):
                        name = str(data.get("name", name))
                        description = str(data.get("description", "")).strip()
                        raw_triggers = data.get("triggers", [])
                        if isinstance(raw_triggers, list):
                            triggers = [str(t) for t in raw_triggers]
                except Exception:
                    pass

    return SkillMetadata(name=name, description=description, path=skill_dir, triggers=triggers)


def load_all_skills(skills_dir: pathlib.Path) -> list[SkillMetadata]:
    """Load all skills found under skills_dir."""
    if not skills_dir.is_dir():
        return []

    skills: list[SkillMetadata] = []
    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and (item / "SKILL.md").is_file():
            skills.append(parse_skill_metadata(item))

    return skills


def generate_catalog_readme(skills: list[SkillMetadata]) -> str:
    """Generate comprehensive README.md index for the skills repository."""
    lines: list[str] = [
        "# Agent Skills Catalog",
        "",
        "A canonical, agent-agnostic catalog of high-leverage software engineering skills and quality guardrails designed for AI coding agents (OpenCode, Antigravity CLI, Claude Code) orchestrated by [Ticket Runner](https://github.com/Viello/ticket-runner).",
        "",
        "---",
        "",
        "## Overview",
        "",
        "Skills encapsulate disciplined development workflows, architectural constraints, diagnostic procedures, and review standards. Each skill is self-contained within its own directory containing a standard `SKILL.md` instruction manual with structured YAML frontmatter.",
        "",
        "## Installation & Synchronization",
        "",
        "### Via Ticket Runner (Recommended)",
        "Ticket Runner automatically provisions and synchronizes this catalog into any project workspace:",
        "",
        "```bash",
        "# Initialize project and synchronize canonical skills catalog",
        "ticket-runner init",
        "",
        "# Synchronize or update skills into an existing project (.agents/skills/)",
        "ticket-runner skills sync",
        "```",
        "",
        "### Manual Download",
        "Download the latest canonical catalog tarball directly:",
        "",
        "```bash",
        "curl -sL https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz | tar -xz",
        "```",
        "",
        "---",
        "",
        "## Canonical Skills Index",
        "",
        f"This repository currently distributes **{len(skills)}** canonical skills:",
        "",
        "| Skill | Description |",
        "| :--- | :--- |",
    ]

    for skill in sorted(skills, key=lambda s: s.name):
        clean_desc = skill.description.replace("\n", " ").replace("|", "\\|")
        lines.append(f"| [{skill.name}]({skill.name}/SKILL.md) | {clean_desc} |")

    lines.extend([
        "",
        "---",
        "",
        "## Skill Directory Anatomy",
        "",
        "Each skill conforms to the standard agent skill specification:",
        "",
        "```text",
        "<skill-name>/",
        "├── SKILL.md            # Instruction manual with YAML frontmatter (name, description)",
        "├── scripts/            # (Optional) Deterministic automation or validation scripts",
        "└── references/         # (Optional) Deep architectural references, schemas, or templates",
        "```",
        "",
        "## Contributing",
        "",
        "1. Ensure all skills contain valid YAML frontmatter with `name` and `description`.",
        "2. Keep instructions actionable, deterministic, and test-first.",
        "3. Never commit API keys, personal access tokens, or project-specific secrets.",
        "",
        "## License",
        "",
        "Distributed under the [MIT License](LICENSE).",
    ])

    return "\n".join(lines) + "\n"


def generate_license() -> str:
    """Generate standard MIT License text."""
    return (
        "MIT License\n\n"
        "Copyright (c) 2026 Viello\n\n"
        "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
        "of this software and associated documentation files (the \"Software\"), to deal\n"
        "in the Software without restriction, including without limitation the rights\n"
        "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
        "copies of the Software, and to permit persons to whom the Software is\n"
        "furnished to do so, subject to the following conditions:\n\n"
        "The above copyright notice and this permission notice shall be included in all\n"
        "copies or substantial portions of the Software.\n\n"
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
        "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
        "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
        "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
        "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
        "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
        "SOFTWARE.\n"
    )


def audit_files_for_secrets(directory: pathlib.Path) -> list[str]:
    """Scan files in directory for forbidden file patterns and potential secret leaks."""
    findings: list[str] = []

    for root, dirs, files in os.walk(directory):
        # Exclude .git directory
        if ".git" in dirs:
            dirs.remove(".git")

        for file_name in files:
            file_path = pathlib.Path(root) / file_name
            rel_path = file_path.relative_to(directory).as_posix()

            for pattern in FORBIDDEN_FILE_PATTERNS:
                if re.match(pattern, file_name, re.IGNORECASE):
                    findings.append(f"Forbidden file pattern '{file_name}' matched at {rel_path}")

            # Read text and check regex
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for secret_regex, label in SECRET_PATTERNS:
                    if re.search(secret_regex, content):
                        findings.append(f"Potential secret detected ({label}) in {rel_path}")
            except Exception:
                pass

    return findings


def sanitize_and_copy_skills(
    source_dir: pathlib.Path,
    target_dir: pathlib.Path,
    ignored_dir_names: tuple[str, ...] = ("__pycache__", ".git", ".pytest_cache", ".agent"),
) -> list[str]:
    """Safely copy skill directories while excluding cache, runtime, and secret files."""
    copied_skills: list[str] = []

    for item in sorted(source_dir.iterdir()):
        if not item.is_dir() or not (item / "SKILL.md").is_file():
            continue

        skill_name = item.name
        dest_skill_dir = target_dir / skill_name
        dest_skill_dir.mkdir(parents=True, exist_ok=True)

        for src_path in item.rglob("*"):
            rel = src_path.relative_to(item)
            # Skip ignored directories
            if any(part in ignored_dir_names for part in rel.parts):
                continue

            target_path = dest_skill_dir / rel
            if src_path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            elif src_path.is_file():
                # Check forbidden file names
                if any(re.match(p, src_path.name, re.IGNORECASE) for p in FORBIDDEN_FILE_PATTERNS):
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, target_path)

        copied_skills.append(skill_name)

    return copied_skills


def _run(cmd: list[str], cwd: pathlib.Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Execute a subprocess command returning completed process."""
    res = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    if check and res.returncode != 0:
        raise RuntimeError(
            f"Command failed ({res.returncode}): {' '.join(cmd)}\nStdout: {res.stdout}\nStderr: {res.stderr}"
        )
    return res


def check_gh_status() -> tuple[bool, str]:
    """Check if GitHub CLI is installed and authenticated."""
    gh_bin = shutil.which("gh")
    if not gh_bin:
        return False, "GitHub CLI ('gh') is not installed or not found in PATH."

    res = _run(["gh", "auth", "status"], check=False)
    if res.returncode != 0:
        return False, f"GitHub CLI is not authenticated: {res.stderr or res.stdout}"

    return True, res.stdout or res.stderr


def ensure_remote_repo(repo: str = "Viello/agent-skills", is_public: bool = True) -> None:
    """Ensure remote repository exists on GitHub, creating it if absent."""
    view_res = _run(["gh", "repo", "view", repo, "--json", "name,isPrivate,defaultBranchRef"], check=False)
    if view_res.returncode == 0:
        print(f"Remote repository '{repo}' already exists.")
        return

    print(f"Remote repository '{repo}' not found. Creating public repository via GitHub CLI...")
    args = ["gh", "repo", "create", repo, "--public" if is_public else "--private"]
    create_res = _run(args, check=True)
    print(f"Repository created successfully:\n{create_res.stdout.strip()}")


def verify_tarball_endpoint(repo: str, branch: str = "main") -> int:
    """Verify that the remote tarball archive endpoint is operational and contains skills."""
    url = f"https://github.com/{repo}/archive/refs/heads/{branch}.tar.gz"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "TicketRunner-SkillsPublisher/1.0"},
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Tarball endpoint returned HTTP status {resp.status}")
        data = resp.read()

    tf = tarfile.open(fileobj=io.BytesIO(data))
    names = tf.getnames()
    assert any("implement/SKILL.md" in n for n in names), (
        "Tarball does not contain canonical skill 'implement/SKILL.md'"
    )
    return len(names)


def publish_skills(
    source_dir: pathlib.Path,
    repo: str = "Viello/agent-skills",
    branch: str = "main",
    dry_run: bool = False,
    commit_msg: str = "feat: publish canonical agent skills catalog",
) -> dict[str, Any]:
    """Publish skills from source directory to remote GitHub repository."""
    if not source_dir.is_dir():
        raise ValueError(f"Source skills directory '{source_dir}' does not exist.")

    skills = load_all_skills(source_dir)
    if not skills:
        raise ValueError(f"No skills found in '{source_dir}'.")

    print(f"Discovered {len(skills)} canonical skills in '{source_dir}'.")

    # Step 1: Preflight GitHub CLI auth check
    if not dry_run:
        ok, msg = check_gh_status()
        if not ok:
            raise RuntimeError(f"GitHub CLI preflight failed: {msg}")

        # Step 2: Ensure remote repository exists
        ensure_remote_repo(repo=repo, is_public=True)

    # Step 3: Stage into a clean, isolated temporary directory
    with tempfile.TemporaryDirectory() as td_str:
        staging_dir = pathlib.Path(td_str)
        print(f"Staging skills into clean isolated directory: {staging_dir}")

        copied = sanitize_and_copy_skills(source_dir, staging_dir)
        print(f"Copied {len(copied)} sanitized skill directories.")

        readme_content = generate_catalog_readme(skills)
        (staging_dir / "README.md").write_text(readme_content, encoding="utf-8")

        license_content = generate_license()
        (staging_dir / "LICENSE").write_text(license_content, encoding="utf-8")

        # Step 4: Security audit
        findings = audit_files_for_secrets(staging_dir)
        if findings:
            for f in findings:
                print(f"SECURITY ALERT: {f}", file=sys.stderr)
            raise RuntimeError(f"Security audit failed with {len(findings)} finding(s). Aborting publication.")

        if dry_run:
            print("Dry-run requested; skipping git initialization, commit, push, and tarball check.")
            return {
                "dry_run": True,
                "skills_count": len(skills),
                "staged_skills": copied,
                "findings": findings,
            }

        # Step 5: Git operations in staging directory
        remote_url = f"https://github.com/{repo}.git"
        _run(["git", "init", "-b", branch], cwd=staging_dir)
        _run(["git", "remote", "add", "origin", remote_url], cwd=staging_dir)

        # Try fetching remote to preserve history if it exists
        fetch_res = _run(["git", "fetch", "origin", branch], cwd=staging_dir, check=False)
        if fetch_res.returncode == 0:
            _run(["git", "reset", "--mixed", f"origin/{branch}"], cwd=staging_dir, check=False)

        _run(["git", "add", "-A"], cwd=staging_dir)
        status_res = _run(["git", "status", "--porcelain"], cwd=staging_dir)
        if not status_res.stdout.strip():
            print("Remote repository is already completely up to date. No changes to commit.")
        else:
            # Set local git identity if not configured
            _run(["git", "config", "user.name", "Viello"], cwd=staging_dir, check=False)
            _run(["git", "config", "user.email", "admin@viello.dev"], cwd=staging_dir, check=False)
            _run(["git", "commit", "-m", commit_msg], cwd=staging_dir)
            print(f"Pushing updates to {repo} on branch '{branch}'...")
            _run(["git", "push", "-u", "origin", branch, "--force"], cwd=staging_dir)
            print("Push succeeded.")

    # Step 6: Verify tarball endpoint
    print("Verifying remote tarball archive endpoint...")
    archive_entries = verify_tarball_endpoint(repo=repo, branch=branch)
    print(f"PASS: Tarball verified with {archive_entries} archive entries.")

    return {
        "repo": repo,
        "branch": branch,
        "skills_count": len(skills),
        "archive_entries": archive_entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish canonical skills catalog to Viello/agent-skills.")
    parser.add_argument(
        "--source-dir",
        type=pathlib.Path,
        default=pathlib.Path(".agents/skills"),
        help="Path to source skills directory (default: .agents/skills)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default="Viello/agent-skills",
        help="GitHub repository name (default: Viello/agent-skills)",
    )
    parser.add_argument(
        "--branch",
        type=str,
        default="main",
        help="Default branch (default: main)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform staging and security audit without creating repo or pushing",
    )
    args = parser.parse_args()

    try:
        publish_skills(
            source_dir=args.source_dir,
            repo=args.repo,
            branch=args.branch,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
