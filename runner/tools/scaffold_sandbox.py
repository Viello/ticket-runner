"""Scaffold external sandbox directory tree for Ticket Runner onboarding."""

from __future__ import annotations

import argparse
import datetime
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

DEFAULT_PREAMBLE: str = (
    "# Ticket Runner Onboarding Sandbox\n"
    "This sandbox demonstrates Ticket Runner queue execution against a runnable Python application.\n"
    "Verify environment prerequisites by running: python ticket_runner.py --project-dir <target> doctor\n"
    "Tickets are queued under docs/tickets/00-welcome/ and executed autonomously on agent/ticket-runner.\n"
    "Scaffold entry point is runner.tools.scaffold_sandbox; reset with --force --non-interactive."
)

INCLUDED_HEADINGS: tuple[str, ...] = (
    "## Invariants",
    "## Development workflow",
    "## Agent skills",
)

STAMP_PATTERN = re.compile(
    r"<!--\s*mirrored from .*? on (\d{4}-\d{2}-\d{2})\s*-->"
)

WELCOME_TICKET_CONTENT: str = """# T001 — Hello World Welcome Ticket
**Type:** wayfinder:task (AFK)
Status: pending
Spec: docs/specs/00-welcome.md
Blocked by: none
Reasoning: low

### Question
Verify that Ticket Runner executes this welcome ticket against sample_app.

### Why this matters
Proves end-to-end autonomous queue execution in the onboarding sandbox.

### Requirements
- Verify `src/sample_app/__init__.py` has `greet(name: str) -> str`.
- Verify `tests/test_smoke.py` passes under `pytest`.

### Acceptance Criteria
- Smoke test passes.
- Welcome ticket can be processed by Ticket Runner worker and gatekeeper.

### Smoke Scenarios
- Run `pytest` to assert `greet("world") == "hello, world!"`.

### Gotchas
- None.
"""

SAMPLE_APP_INIT: str = '''"""Sample application package."""


def greet(name: str) -> str:
    """Return a greeting message."""
    return f"hello, {name}!"
'''

SAMPLE_APP_TEST: str = """from src.sample_app import greet


def test_greet() -> None:
    assert greet("world") == "hello, world!"
"""

GITIGNORE_CONTENT: str = """.agent/
docs/tickets/.queue.lock
__pycache__/
*.pyc
.pytest_cache/
"""

TICKET_RUNNER_YAML: str = """project:
  name: "ticket-runner-live-target"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  provider: "antigravity"
  execution_skill: ".agents/skills/implement/SKILL.md"

verification:
  test_cmd: "python -m pytest"
  build_cmd: ""
  max_attempts: 3
  timeout_seconds: 300
  silence_window_seconds: 60
  per_test_timeout_seconds: 0
  isolation_cmd: ""
  bug_escalation_at: 1

tokens:
  warn: 120000
  handoff: 135000
  ceiling: 150000

presence:
  default_mode: "nearby"
  idle_escalation_minutes: 3

discord:
  enabled: false

lifecycle:
  queue_completion: "standby"
  clean_slate: "interactive"
  poll_interval: 5.0

git:
  auto_push: false
  commit_prefix: "feat"
  enforce_pre_push_hook: true

ui:
  session_terminal: "auto"
"""


def get_default_target_dir() -> Path:
    """Return default target directory based on OS platform."""
    if platform.system() == "Windows":
        return Path(r"D:\Sandbox\ticket-runner-live-target")
    return Path.home() / "Sandbox" / "ticket-runner-live-target"


def extract_curated_subset(text: str) -> str:
    """Extract invariant-bearing curated sections from upstream AGENTS.md."""
    lines = text.splitlines()
    sections: list[str] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            heading = line.split("\n")[0].strip()
            if current_heading and any(current_heading.startswith(h) for h in INCLUDED_HEADINGS):
                sections.append("\n".join(current_lines).strip())
            current_heading = heading
            current_lines = [line]
        else:
            if current_heading:
                current_lines.append(line)

    if current_heading and any(current_heading.startswith(h) for h in INCLUDED_HEADINGS):
        sections.append("\n".join(current_lines).strip())

    return "\n\n".join(sections).strip()


def format_sandbox_agents_md(preamble: str, stamp_date: str, curated_subset: str) -> str:
    """Format the complete sandbox AGENTS.md content."""
    clean_preamble = preamble.strip()
    clean_subset = curated_subset.strip()
    return f"{clean_preamble}\n\n<!-- mirrored from D:\\Projects/AGENTS.md on {stamp_date} -->\n\n{clean_subset}\n"


def parse_sandbox_agents_md(text: str) -> tuple[str, str, str]:
    """Parse preamble, sync stamp date, and curated subset from sandbox AGENTS.md."""
    match = STAMP_PATTERN.search(text)
    if match:
        preamble = text[: match.start()].strip()
        stamp_date = match.group(1)
        curated_subset = text[match.end() :].strip()
        return preamble, stamp_date, curated_subset
    return DEFAULT_PREAMBLE, "", text.strip()


def _resolve_source_skills_dir(override: Path | None = None) -> Path | None:
    """Locate source .agents/skills directory with fallback logic."""
    if override is not None and override.is_dir():
        return override

    candidates = [
        Path(__file__).resolve().parents[2] / ".agents" / "skills",
        Path(r"D:\Projects\.agents\skills"),
        Path.cwd() / ".agents" / "skills",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def _resolve_upstream_agents_md(override: Path | None = None) -> Path | None:
    """Locate upstream AGENTS.md file with fallback logic."""
    if override is not None and override.is_file():
        return override

    candidates = [
        Path(__file__).resolve().parents[2] / "AGENTS.md",
        Path(r"D:\Projects\AGENTS.md"),
        Path.cwd() / "AGENTS.md",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def scaffold(
    target_dir: Path,
    *,
    force: bool = False,
    source_skills_dir: Path | None = None,
    upstream_agents_md: Path | None = None,
) -> None:
    """Scaffold onboarding sandbox tree to target_dir.

    Args:
        target_dir: Root directory for the target sandbox.
        force: If True, wipes existing source-tree files before regenerating.
               Preserves .git/ and .agent/ runtime state.
        source_skills_dir: Optional override for source skills catalog directory.
        upstream_agents_md: Optional override for upstream AGENTS.md file.
    """
    target = target_dir.resolve()
    created_count = 0

    if force and target.exists():
        for item in target.iterdir():
            if item.name in (".git", ".agent"):
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    target.mkdir(parents=True, exist_ok=True)

    # 1. .agent/ runtime directories
    for sub in ("signals", "questions", "logs", "checkpoints", "evidence", "archive"):
        (target / ".agent" / sub).mkdir(parents=True, exist_ok=True)

    # 2. .agents/skills/{implement,code-review,diagnosing-bugs,handoff}/SKILL.md
    skills_src = _resolve_source_skills_dir(source_skills_dir)
    target_skills_dir = target / ".agents" / "skills"
    for skill_name in ("implement", "code-review", "diagnosing-bugs", "handoff"):
        dest_file = target_skills_dir / skill_name / "SKILL.md"
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if not dest_file.exists() or force:
            src_file = skills_src / skill_name / "SKILL.md" if skills_src else None
            if src_file and src_file.is_file():
                dest_file.write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                dest_file.write_text(
                    f"---\nname: {skill_name}\ndescription: {skill_name} skill\n---\n# {skill_name}\n",
                    encoding="utf-8",
                )
            created_count += 1

    # 3. docs/tickets/00-welcome/T001-hello-world.md
    welcome_ticket = target / "docs" / "tickets" / "00-welcome" / "T001-hello-world.md"
    welcome_ticket.parent.mkdir(parents=True, exist_ok=True)
    if not welcome_ticket.exists() or force:
        welcome_ticket.write_text(WELCOME_TICKET_CONTENT, encoding="utf-8")
        created_count += 1

    # 4. src/sample_app/__init__.py
    sample_init = target / "src" / "sample_app" / "__init__.py"
    sample_init.parent.mkdir(parents=True, exist_ok=True)
    if not sample_init.exists() or force:
        sample_init.write_text(SAMPLE_APP_INIT, encoding="utf-8")
        created_count += 1

    # 5. tests/test_smoke.py
    smoke_test = target / "tests" / "test_smoke.py"
    smoke_test.parent.mkdir(parents=True, exist_ok=True)
    if not smoke_test.exists() or force:
        smoke_test.write_text(SAMPLE_APP_TEST, encoding="utf-8")
        created_count += 1

    # 6. AGENTS.md
    agents_file = target / "AGENTS.md"
    if not agents_file.exists() or force:
        upstream_file = _resolve_upstream_agents_md(upstream_agents_md)
        if upstream_file and upstream_file.is_file():
            curated_subset = extract_curated_subset(upstream_file.read_text(encoding="utf-8"))
        else:
            curated_subset = (
                "## Invariants\n"
                "- All automated work happens on agent/ticket-runner.\n"
                "- Commit format: <type>(<scope>): <Title>.\n"
                "- Worker executes tickets via configured worker.execution_skill.\n\n"
                "## Development workflow\n"
                "### 3. Execution (Interactive or Ticket Runner)\n"
                "- Implement tickets using TDD at pre-agreed seams.\n\n"
                "## Agent skills\n"
                "- .agents/skills/ vendors skill catalog."
            )
        today = datetime.date.today().isoformat()
        agents_content = format_sandbox_agents_md(DEFAULT_PREAMBLE, today, curated_subset)
        agents_file.write_text(agents_content, encoding="utf-8")
        created_count += 1

    # 7. ticket-runner.yaml
    config_file = target / "ticket-runner.yaml"
    if not config_file.exists() or force:
        config_file.write_text(TICKET_RUNNER_YAML, encoding="utf-8")
        created_count += 1

    # 8. .gitignore
    gitignore_file = target / ".gitignore"
    if not gitignore_file.exists() or force:
        gitignore_file.write_text(GITIGNORE_CONTENT, encoding="utf-8")
        created_count += 1

    # 9. Git repository initialization & branch
    git_dir = target / ".git"
    if not git_dir.is_dir():
        try:
            init_res = subprocess.run(
                ["git", "init", "-b", "main"],
                cwd=target,
                capture_output=True,
                text=True,
            )
            if init_res.returncode != 0:
                subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
                subprocess.run(["git", "checkout", "-b", "main"], cwd=target, check=True, capture_output=True)
        except Exception:
            subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
            subprocess.run(["git", "checkout", "-b", "main"], cwd=target, check=True, capture_output=True)

        subprocess.run(["git", "checkout", "-b", "agent/ticket-runner"], cwd=target, check=True, capture_output=True)
    else:
        # If git already exists, ensure we are on agent/ticket-runner
        try:
            branch_check = subprocess.run(
                ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
            )
            if branch_check.stdout.strip() != "agent/ticket-runner":
                branch_list = subprocess.run(
                    ["git", "-C", str(target), "branch", "--list", "agent/ticket-runner"],
                    capture_output=True,
                    text=True,
                )
                if "agent/ticket-runner" in branch_list.stdout:
                    subprocess.run(["git", "-C", str(target), "checkout", "agent/ticket-runner"], check=True, capture_output=True)
                else:
                    subprocess.run(["git", "-C", str(target), "checkout", "-b", "agent/ticket-runner"], check=True, capture_output=True)
        except Exception:
            pass

    # 10. Install pre-push hook
    hook_cmd = [
        sys.executable,
        "-m",
        "runner.adapters.git.pre_push_hook",
        "install",
        "--git-dir",
        str(git_dir),
    ]
    hook_res = subprocess.run(hook_cmd, capture_output=True, text=True)
    if hook_res.returncode != 0:
        raise RuntimeError(f"Failed to install pre-push hook: {hook_res.stderr or hook_res.stdout}")

    # 11. Auto-configure git identity locally if missing
    name_res = subprocess.run(
        ["git", "-C", str(target), "config", "user.name"],
        capture_output=True,
        text=True,
    )
    if name_res.returncode != 0 or not name_res.stdout.strip():
        subprocess.run(
            ["git", "-C", str(target), "config", "user.name", "ticket-runner-scaffold"],
            check=True,
            capture_output=True,
        )

    email_res = subprocess.run(
        ["git", "-C", str(target), "config", "user.email"],
        capture_output=True,
        text=True,
    )
    if email_res.returncode != 0 or not email_res.stdout.strip():
        subprocess.run(
            ["git", "-C", str(target), "config", "user.email", "noreply@local"],
            check=True,
            capture_output=True,
        )

    # 12. Author initial commit if there are staged/uncommitted changes
    subprocess.run(["git", "-C", str(target), "add", "-A"], check=True, capture_output=True)
    status_res = subprocess.run(
        ["git", "-C", str(target), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    commit_sha = "unchanged"
    if status_res.stdout.strip():
        subprocess.run(
            [
                "git",
                "-C",
                str(target),
                "commit",
                "-m",
                "chore(sandbox): initialize ticket-runner onboarding sandbox",
            ],
            check=True,
            capture_output=True,
        )

    rev_res = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    if rev_res.returncode == 0:
        commit_sha = rev_res.stdout.strip()

    # 13. 5-line summary log
    hook_file = git_dir / "hooks" / "pre-push"
    print(f"[scaffold] Target directory: {target}")
    print(f"[scaffold] Files created: {created_count} file(s) generated")
    print(f"[scaffold] Hook installed: {hook_file} active")
    print(f"[scaffold] Commit: {commit_sha} chore(sandbox): initialize ticket-runner onboarding sandbox")
    print(f"[scaffold] Verification: python ticket_runner.py --project-dir {target} doctor")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for scaffolding sandbox."""
    parser = argparse.ArgumentParser(
        prog="runner.tools.scaffold_sandbox",
        description="Scaffold an onboarding Target Project sandbox for Ticket Runner.",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=get_default_target_dir(),
        help="Target sandbox directory path",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Wipe and regenerate sandbox files",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Skip confirmation prompt on --force",
    )

    args = parser.parse_args(argv)
    target_dir: Path = args.target_dir.resolve()

    if args.force and not args.non_interactive and target_dir.exists():
        response = input(f"Warning: --force will wipe non-runtime files in '{target_dir}'. Proceed? [y/N]: ")
        if response.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    scaffold(target_dir, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
