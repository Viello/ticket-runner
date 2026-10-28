"""Scaffold external sandbox directory tree for Ticket Runner onboarding."""

from __future__ import annotations

import argparse
import datetime
import io
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
from typing import Literal
import urllib.error
import urllib.request

from runner.tools.sanitize import apply_sanitization

DEFAULT_PREAMBLE: str = (
    "Welcome to your Ticket Runner sandbox — a runnable demo target at `D:\\Sandbox\\ticket-runner-live-target\\`.\n"
    "First stop: run `ticket-runner --project-dir . doctor` to confirm the sandbox is wired.\n"
    "Tickets live in `docs/tickets/00-welcome/`.\n"
    "The scaffold entry point is `python -m runner.tools.scaffold_sandbox`.\n"
    "Reset with `--force` to wipe and regenerate this tree from the upstream layout lock (T005)."
)

INCLUDED_HEADINGS: tuple[str, ...] = (
    "## Invariants",
    "## Environment",
    "## Agent skills",
)

# Bullet-trim markers (substring prefix on bullet text after "- ").
# Per T005c resolution: each bullet is matched by its starting text, not by
# index, so upstream additions don't silently break the trim. Unrecognized
# bullets are dropped by default (conservative: extra content in the sandbox
# would confuse first-time users).

ENV_BULLETS_KEEP_PREFIXES: tuple[str, ...] = (
    "Target platform is Windows/PowerShell",
)

AGENT_BULLETS_KEEP_PREFIXES_DEFAULT: tuple[str, ...] = (
    "`.agents/skills/handoff/SKILL.md` is load-bearing",
    "`.agents/skills/implement-ticket-runner/SKILL.md` defines",
    "`.agents/skills/implement/SKILL.md` defines",
)

AGENT_BULLETS_KEEP_PREFIXES_ALL: tuple[str, ...] = (
    "`.agents/skills/` vendors the user's global skill catalog",
    "`.agents/skills/handoff/SKILL.md` is load-bearing",
    "`.agents/skills/implement-ticket-runner/SKILL.md` defines",
    "`.agents/skills/implement/SKILL.md` defines",
    "`.agents/skills/security-review/SKILL.md` defines",
)

SkillsMode = Literal["default", "all"]

CURATED_SKILLS: tuple[str, ...] = (
    "implement-ticket-runner",
    "code-review",
    "diagnosing-bugs",
    "handoff",
)

PUBLIC_SKILLS_REPO_URL: str = "https://github.com/Viello/agent-skills"
PUBLIC_SKILLS_TARBALL_URL: str = "https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz"


def fetch_public_skills_catalog(
    url: str = PUBLIC_SKILLS_TARBALL_URL,
    timeout: float = 15.0,
) -> dict[str, str]:
    """Fetch and extract skill catalog from upstream GitHub tarball.

    Returns:
        Mapping of skill_name -> SKILL.md content.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ticket-runner-scaffold"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        tar_bytes = resp.read()

    skills: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            parts = member.name.split("/")
            if len(parts) == 3 and parts[2] == "SKILL.md":
                skill_name = parts[1]
                f = tar.extractfile(member)
                if f is not None:
                    skills[skill_name] = f.read().decode("utf-8")

    if not skills:
        raise ValueError(f"No skills found in tarball from {url}")
    return skills

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

TICKET_RUNNER_YAML_TEMPLATE: str = """project:
  name: "ticket-runner-live-target"
  branch: "agent/ticket-runner"
  base_branch: "main"

worker:
  provider: "antigravity"
  execution_skill: ".agents/skills/implement-ticket-runner/SKILL.md"

sandbox:
  # Flip + re-run sync_agents_md.py --write --skills <default|all> to apply.
  skills: "{skills_mode}"

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
  token_env: "DISCORD_BOT_TOKEN"

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


def build_ticket_runner_yaml(skills_mode: SkillsMode = "default") -> str:
    """Render the sandbox ``ticket-runner.yaml`` with the ``sandbox.skills`` mode.

    The emitted file is self-documenting: ``sandbox.skills`` reflects the mode
    the scaffold was invoked with, and carries a footnote explaining how to
    re-apply a post-scaffold flip (see T005d resolution, Q5).
    """
    return TICKET_RUNNER_YAML_TEMPLATE.replace("{skills_mode}", skills_mode)


def _read_yaml_sandbox_skills(yaml_path: Path) -> SkillsMode | None:
    """Read ``sandbox.skills`` from a ``ticket-runner.yaml`` file.

    Returns ``"default"`` or ``"all"`` when the key is present and valid,
    ``None`` otherwise (missing file, malformed YAML, missing/unknown value).
    """
    try:
        import yaml
    except ImportError:  # pragma: no cover - pyyaml is a hard dependency
        return None

    if not yaml_path.is_file():
        return None

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None

    if not isinstance(data, dict):
        return None
    sandbox = data.get("sandbox")
    if not isinstance(sandbox, dict):
        return None
    skills = sandbox.get("skills")
    if skills in ("default", "all"):
        return skills  # type: ignore[return-value]
    return None


def _resolve_skills_mode(
    cli_mode: SkillsMode | None,
    target_dir: Path,
) -> SkillsMode:
    """Resolve the effective skills mode: CLI > ``ticket-runner.yaml`` > fallback.

    Priority (per T005d resolution, Q2):
        1. Explicit ``cli_mode`` (from ``--skills``), when provided.
        2. ``ticket-runner.yaml: sandbox.skills`` under ``target_dir``.
        3. Hardcoded fallback ``"default"``.
    """
    if cli_mode is not None:
        return cli_mode
    yaml_mode = _read_yaml_sandbox_skills(target_dir / "ticket-runner.yaml")
    if yaml_mode is not None:
        return yaml_mode
    return "default"


def _filter_section_bullets(
    section_lines: list[str],
    keep_prefixes: tuple[str, ...],
) -> list[str]:
    """Filter bullets in a markdown section, returning heading + kept bullets.

    Bullets whose text (after "- ") starts with any of ``keep_prefixes`` are
    kept. All other bullets (drop-targeted or unrecognized) are dropped.
    Non-bullet lines (blank, continuation) are dropped to keep the section
    tight; upstream AGENTS.md bullets are single-line.
    """
    result: list[str] = []
    for line in section_lines:
        if line.startswith("## "):
            result.append(line)
            continue
        if line.startswith("- ") or line.startswith("* "):
            bullet_text = line[2:].lstrip()
            if any(bullet_text.startswith(p) for p in keep_prefixes):
                result.append(line)
            # else: drop
        # else: drop non-bullet lines (blank, continuation)
    return result


def extract_curated_subset(text: str, skills_mode: SkillsMode = "default") -> str:
    """Extract invariant-bearing curated sections from upstream AGENTS.md.

    Args:
        text: Raw upstream ``AGENTS.md`` content.
        skills_mode: Either ``"default"`` (4 curated skills shipped) or
            ``"all"`` (full skill catalog shipped — see T005d). Controls the
            bullet-trim for ``## Agent skills`` only.
    """
    lines = text.splitlines()
    sections: list[str] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in lines:
        if line.startswith("## "):
            heading = line.split("\n")[0].strip()
            if current_heading and any(current_heading.startswith(h) for h in INCLUDED_HEADINGS):
                sections.append(_finalize_section(current_heading, current_lines, skills_mode))
            current_heading = heading
            current_lines = [line]
        else:
            if current_heading:
                current_lines.append(line)

    if current_heading and any(current_heading.startswith(h) for h in INCLUDED_HEADINGS):
        sections.append(_finalize_section(current_heading, current_lines, skills_mode))

    return "\n\n".join(sections).strip()


def _finalize_section(
    heading: str,
    section_lines: list[str],
    skills_mode: SkillsMode,
) -> str:
    """Apply section-specific bullet trim and return the cleaned section text."""
    if heading.startswith("## Environment"):
        keep = ENV_BULLETS_KEEP_PREFIXES
    elif heading.startswith("## Agent skills"):
        keep = (
            AGENT_BULLETS_KEEP_PREFIXES_ALL
            if skills_mode == "all"
            else AGENT_BULLETS_KEEP_PREFIXES_DEFAULT
        )
    else:
        # ## Invariants (or any future INCLUDED_HEADINGS without a trim spec):
        # all bullets verbatim.
        return "\n".join(section_lines).strip()
    return "\n".join(_filter_section_bullets(section_lines, keep)).strip()


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


# Fallback when no upstream AGENTS.md is discoverable. Mirrors the default-mode
# Fallback when no upstream AGENTS.md is discoverable. Mirrors the default-mode
# bullet trim (per T005c resolution).
FALLBACK_CURATED_SUBSET: str = (
    "## Invariants\n"
    "- All automated work happens on agent/ticket-runner.\n"
    "- Commit format: <type>(<scope>): <Title>.\n"
    "- Worker executes tickets via configured worker.execution_skill.\n\n"
    "## Environment\n"
    "- Target platform is Windows/PowerShell.\n\n"
    "## Agent skills\n"
    "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
    "- `.agents/skills/implement-ticket-runner/SKILL.md` defines the default worker implementation discipline."
)

DEFAULT_UPSTREAM_AGENTS_MD: str = """# AGENTS.md

Target Project operating rules for Ticket Runner autonomous queue execution.

## Invariants
- All automated work happens on agent/ticket-runner; the Runner stages and commits, and .git/hooks/pre-push blocks pushes. Never git push.
- Commit format: Title must be <type>(<scope>): <Title> where <scope> names the architectural layer or subsystem, never a ticket number. Follow with a blank line and hyphen-bulleted imperative changes.
- Worker executes tickets via configured worker.execution_skill, performing pre-signal reviews, but never commits directly.
- Worker<->Runner messages are durable JSON files (.agent/signals/{ticket_id}_ready.json, .agent/questions/{ticket_id}.json) - never parse model stdout for state.
- Only the Runner's Gatekeeper passes a ticket, by running configured test/build commands; Worker self-reports don't count; 3 failed attempts trip the circuit breaker.
- Token budget: warn 120k, handoff 135k, hard ceiling 150k; handoff writes .agent/checkpoints/{ticket_id}/handoff.md.
- Single commit per ticket: Gatekeeper approval authors exactly one commit combining code, tests, newly logged gotchas, and the relocated ticket file (Status: completed).
- .agent/ is untracked runtime state; git-ignore it when implementing.
- Human verification happens after green checks via a /live-qa session the human runs; the Worker drafts no scenarios and self-reports no manual verification.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; handoff, claude-handoff, to-tickets have project-specific edits.
- `.agents/skills/handoff/SKILL.md` is load-bearing.
- `.agents/skills/implement-ticket-runner/SKILL.md` defines the default worker implementation discipline.
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline.
"""


def build_agents_md_content(
    preamble: str,
    *,
    skills_mode: SkillsMode = "default",
    upstream_agents_md: Path | None = None,
) -> str:
    """Build AGENTS.md content from a preamble plus the curated upstream subset.

    Resolves the upstream AGENTS.md (falling back to the canonical Target Project
    subset when none is specified), extracts the invariant-bearing sections,
    and stamps the result with today's sync date. Shared by the sandbox
    scaffolder and the interactive ``init`` scaffolder.
    """
    upstream_file = _resolve_upstream_agents_md(upstream_agents_md)
    if upstream_file and upstream_file.is_file():
        source_text = upstream_file.read_text(encoding="utf-8")
    else:
        source_text = DEFAULT_UPSTREAM_AGENTS_MD

    curated_subset = extract_curated_subset(
        source_text,
        skills_mode=skills_mode,
    )
    today = datetime.date.today().isoformat()
    return format_sandbox_agents_md(preamble, today, curated_subset)


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
    return None


def scaffold(
    target_dir: Path,
    *,
    force: bool = False,
    source_skills_dir: Path | None = None,
    upstream_agents_md: Path | None = None,
    skills_mode: SkillsMode = "default",
) -> None:
    """Scaffold onboarding sandbox tree to target_dir.

    Args:
        target_dir: Root directory for the target sandbox.
        force: If True, wipes existing source-tree files before regenerating.
               Preserves .git/ and .agent/ runtime state.
        source_skills_dir: Optional override for source skills catalog directory.
        upstream_agents_md: Optional override for upstream AGENTS.md file.
        skills_mode: Either ``"default"`` (4 curated skills shipped) or
            ``"all"`` (full skill catalog — see T005d). Affects the bullet
            trim applied to ``## Agent skills`` in AGENTS.md only.
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

    # 2. .agents/skills/<skill>/SKILL.md
    target_skills_dir = target / ".agents" / "skills"
    source_label = "Viello/agent-skills"
    fallback = False
    skills_data: dict[str, str] = {}

    if skills_mode == "all":
        if source_skills_dir is not None:
            if not source_skills_dir.is_dir():
                raise FileNotFoundError(f"Source skills directory does not exist: {source_skills_dir}")
            source_label = str(source_skills_dir)
            for item in sorted(source_skills_dir.iterdir()):
                skill_file = item / "SKILL.md"
                if item.is_dir() and skill_file.is_file():
                    skills_data[item.name] = skill_file.read_text(encoding="utf-8")
        else:
            try:
                skills_data = fetch_public_skills_catalog()
                source_label = "Viello/agent-skills"
            except Exception as exc:
                print(
                    f"[scaffold] Warning: Failed to fetch skill catalog from Viello/agent-skills: {exc}. "
                    "Falling back to curated default skills."
                )
                fallback = True

        if fallback or (source_skills_dir is None and not skills_data):
            fallback = True
            skills_src = _resolve_source_skills_dir(None)
            skills_data = {}
            for skill_name in CURATED_SKILLS:
                src_file = skills_src / skill_name / "SKILL.md" if skills_src else None
                if src_file and src_file.is_file():
                    skills_data[skill_name] = src_file.read_text(encoding="utf-8")
                else:
                    skills_data[skill_name] = (
                        f"---\nname: {skill_name}\ndescription: {skill_name} skill\n---\n# {skill_name}\n"
                    )
    else:
        # default mode: 4 curated skills
        skills_src = _resolve_source_skills_dir(source_skills_dir)
        for skill_name in CURATED_SKILLS:
            src_file = skills_src / skill_name / "SKILL.md" if skills_src else None
            if src_file and src_file.is_file():
                skills_data[skill_name] = src_file.read_text(encoding="utf-8")
            else:
                skills_data[skill_name] = (
                    f"---\nname: {skill_name}\ndescription: {skill_name} skill\n---\n# {skill_name}\n"
                )

    for skill_name, content in skills_data.items():
        dest_file = target_skills_dir / skill_name / "SKILL.md"
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        if not dest_file.exists() or force:
            dest_file.write_text(
                apply_sanitization(content, "skill_md"),
                encoding="utf-8",
            )
            created_count += 1

    # 3. docs/tickets/00-welcome/T001-hello-world.md
    welcome_ticket = target / "docs" / "tickets" / "00-welcome" / "T001-hello-world.md"
    welcome_ticket.parent.mkdir(parents=True, exist_ok=True)
    if not welcome_ticket.exists() or force:
        welcome_ticket.write_text(
            apply_sanitization(WELCOME_TICKET_CONTENT, "welcome_ticket"),
            encoding="utf-8",
        )
        created_count += 1

    # 4. src/sample_app/__init__.py
    sample_init = target / "src" / "sample_app" / "__init__.py"
    sample_init.parent.mkdir(parents=True, exist_ok=True)
    if not sample_init.exists() or force:
        sample_init.write_text(
            apply_sanitization(SAMPLE_APP_INIT, "python_src"),
            encoding="utf-8",
        )
        created_count += 1

    # 5. tests/test_smoke.py
    smoke_test = target / "tests" / "test_smoke.py"
    smoke_test.parent.mkdir(parents=True, exist_ok=True)
    if not smoke_test.exists() or force:
        smoke_test.write_text(
            apply_sanitization(SAMPLE_APP_TEST, "python_test"),
            encoding="utf-8",
        )
        created_count += 1

    # 6. AGENTS.md
    agents_file = target / "AGENTS.md"
    if not agents_file.exists() or force:
        agents_content = build_agents_md_content(
            DEFAULT_PREAMBLE,
            skills_mode=skills_mode,
            upstream_agents_md=upstream_agents_md,
        )
        agents_file.write_text(
            apply_sanitization(agents_content, "agents_md"),
            encoding="utf-8",
        )
        created_count += 1

    # 7. ticket-runner.yaml
    config_file = target / "ticket-runner.yaml"
    if not config_file.exists() or force:
        config_file.write_text(
            apply_sanitization(build_ticket_runner_yaml(skills_mode), "ticket_runner_yaml"),
            encoding="utf-8",
        )
        created_count += 1

    # 8. .gitignore
    gitignore_file = target / ".gitignore"
    if not gitignore_file.exists() or force:
        gitignore_file.write_text(
            apply_sanitization(GITIGNORE_CONTENT, "gitignore"),
            encoding="utf-8",
        )
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
    if skills_mode == "all":
        if fallback:
            print("[scaffold] all mode: 4 skills shipped (fallback to curated default)")
        else:
            print(f"[scaffold] all mode: {len(skills_data)} skills shipped from {source_label}")


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
    parser.add_argument(
        "--source-skills-dir",
        type=Path,
        default=None,
        help="Optional local directory override for source skills catalog",
    )
    parser.add_argument(
        "--skills",
        choices=("default", "all"),
        default=None,
        help=(
            "Skill catalog mode: 'default' ships the 4 curated skills "
            "(implement, code-review, diagnosing-bugs, handoff); 'all' ships "
            "the full catalog from Viello/agent-skills. Overrides ticket-runner.yaml "
            "sandbox.skills; falls back to it, then to 'default'."
        ),
    )

    args = parser.parse_args(argv)
    target_dir: Path = args.target_dir.resolve()
    skills_mode = _resolve_skills_mode(args.skills, target_dir)

    if args.force and not args.non_interactive and target_dir.exists():
        response = input(f"Warning: --force will wipe non-runtime files in '{target_dir}'. Proceed? [y/N]: ")
        if response.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    scaffold(
        target_dir,
        force=args.force,
        skills_mode=skills_mode,
        source_skills_dir=args.source_skills_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
