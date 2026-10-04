"""Unit tests for runner.tools.scaffold_sandbox."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import pytest

from runner.adapters.git.pre_push_hook import PrePushHookInstaller
from runner.tools.scaffold_sandbox import (
    DEFAULT_PREAMBLE,
    _read_yaml_sandbox_skills,
    _resolve_skills_mode,
    build_ticket_runner_yaml,
    extract_curated_subset,
    get_default_target_dir,
    main,
    scaffold,
)


def test_get_default_target_dir() -> None:
    default_dir = get_default_target_dir()
    if sys.platform == "win32":
        assert default_dir == Path(r"D:\Sandbox\ticket-runner-live-target")
    else:
        assert default_dir == Path.home() / "Sandbox" / "ticket-runner-live-target"


def test_extract_curated_subset() -> None:
    sample_agents_md = """# AGENTS.md
Ticket Runner description.

## Implementation status
Specs 01-13 implemented.

## Read before designing
- ARCHITECTURE.md

## Invariants
- First invariant.
- Second invariant.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook executes under Git for Windows' bundled sh.
- Dependencies: discord.py, rich, pyyaml, pytest (see requirements.txt). Discord token comes from the DISCORD_BOT_TOKEN env var.
- Discord and terminal-UI adapters are implemented under runner/adapters/discord/ and runner/adapters/ui/.
- Pre-push hook guardrail is installed via runner/adapters/git/pre_push_hook.py reading scripts/pre-push.sh.

## Development workflow
General workflow info.

### 1. Alignment & Design
- Grill me.

### 3. Execution (Interactive or Ticket Runner)
- Implement tickets.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; handoff, claude-handoff, to-tickets have project-specific edits.
- `.agents/skills/handoff/SKILL.md` is load-bearing.
- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline.
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline (ADR 0013).
"""
    curated = extract_curated_subset(sample_agents_md)
    # Per T005c resolution: Invariants + Environment + Agent skills included.
    assert "## Invariants" in curated
    assert "- First invariant." in curated
    assert "- Second invariant." in curated
    assert "## Environment" in curated
    assert "## Agent skills" in curated
    # Per T005c bullet trim (default): only the Windows/PowerShell bullet survives.
    assert "Target platform is Windows/PowerShell" in curated
    assert "Dependencies:" not in curated
    assert "Discord and terminal-UI adapters" not in curated
    assert "Pre-push hook guardrail" not in curated
    # Per T005c bullet trim (default): only handoff + implement survive in Agent skills.
    assert "handoff/SKILL.md` is load-bearing" in curated
    assert "implement/SKILL.md` defines the default worker" in curated
    assert "vendors the user's global skill catalog" not in curated
    assert "security-review/SKILL.md" not in curated
    # Per T005c section exclusions.
    assert "## Implementation status" not in curated
    assert "## Read before designing" not in curated
    assert "## Development workflow" not in curated


def test_extract_curated_subset_all_skills_mode() -> None:
    sample_agents_md = """# AGENTS.md

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog.
- `.agents/skills/handoff/SKILL.md` is load-bearing.
- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline.
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline.
"""
    curated = extract_curated_subset(sample_agents_md, skills_mode="all")
    # Per T005c resolution (all mode): all 4 Agent skills bullets survive.
    assert "vendors the user's global skill catalog" in curated
    assert "handoff/SKILL.md` is load-bearing" in curated
    assert "implement/SKILL.md` defines" in curated
    assert "security-review/SKILL.md" in curated


def test_extract_curated_subset_unrecognized_bullets_dropped() -> None:
    """Bullets not in the keep-marker list are dropped (conservative default)."""
    sample_agents_md = """# AGENTS.md

## Environment
- Target platform is Windows/PowerShell.
- Future unknown bullet that isn't in T005c's rubric.
"""
    curated = extract_curated_subset(sample_agents_md)
    assert "Target platform is Windows/PowerShell" in curated
    assert "Future unknown bullet" not in curated


def test_scaffold_happy_path(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)

    # 1. .agent/ subdirs
    for sub in ("signals", "questions", "logs", "checkpoints", "evidence", "archive"):
        assert (target / ".agent" / sub).is_dir()

    # 2. .agents/skills
    for skill in ("implement", "code-review", "diagnosing-bugs", "handoff"):
        skill_file = target / ".agents" / "skills" / skill / "SKILL.md"
        assert skill_file.is_file()

    # 3. docs/tickets/00-welcome/T001-hello-world.md
    welcome_ticket = target / "docs" / "tickets" / "00-welcome" / "T001-hello-world.md"
    assert welcome_ticket.is_file()
    assert "Status: pending" in welcome_ticket.read_text(encoding="utf-8")

    # 4. src/sample_app/__init__.py and tests/test_smoke.py
    src_file = target / "src" / "sample_app" / "__init__.py"
    assert src_file.is_file()
    assert "def greet(name: str) -> str:" in src_file.read_text(encoding="utf-8")

    test_file = target / "tests" / "test_smoke.py"
    assert test_file.is_file()
    assert 'assert greet("world") == "hello, world!"' in test_file.read_text(encoding="utf-8")

    # 5. AGENTS.md
    agents_md = target / "AGENTS.md"
    assert agents_md.is_file()
    content = agents_md.read_text(encoding="utf-8")
    assert DEFAULT_PREAMBLE in content
    assert "<!-- mirrored from D:\\Projects/AGENTS.md on" in content
    assert "## Invariants" in content

    # 6. ticket-runner.yaml and .gitignore
    assert (target / "ticket-runner.yaml").is_file()
    assert (target / ".gitignore").is_file()

    # 7. Git repo checks
    assert (target / ".git").is_dir()
    branch_res = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert branch_res.stdout.strip() == "agent/ticket-runner"

    # Pre-push hook installed
    assert PrePushHookInstaller.is_installed(target / ".git")

    # Initial commit
    log_res = subprocess.run(
        ["git", "-C", str(target), "log", "-1", "--pretty=%B"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "chore(sandbox): initialize ticket-runner onboarding sandbox" in log_res.stdout


def test_scaffold_idempotent_preserves_existing_files(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)

    # Modify a file
    custom_text = "# Custom User Edit\n"
    (target / "AGENTS.md").write_text(custom_text, encoding="utf-8")

    # Re-run scaffold without force
    scaffold(target, force=False)

    # Check file was preserved
    assert (target / "AGENTS.md").read_text(encoding="utf-8") == custom_text


def test_scaffold_force_wipes_and_regenerates_preserving_runtime_and_git(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)

    # Modify AGENTS.md
    (target / "AGENTS.md").write_text("# Modified", encoding="utf-8")

    # Add extra source file
    extra_file = target / "extra.txt"
    extra_file.write_text("extra", encoding="utf-8")

    # Add a runtime file inside .agent/
    runtime_file = target / ".agent" / "logs" / "runtime.log"
    runtime_file.write_text("runtime state", encoding="utf-8")

    # Run with force
    scaffold(target, force=True)

    # Extra source file wiped
    assert not extra_file.exists()

    # AGENTS.md regenerated
    assert "## Invariants" in (target / "AGENTS.md").read_text(encoding="utf-8")

    # .git preserved
    assert (target / ".git").is_dir()

    # .agent runtime state preserved
    assert runtime_file.is_file()
    assert runtime_file.read_text(encoding="utf-8") == "runtime state"


def test_scaffold_git_identity_auto_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "sandbox"
    # Ensure git config has empty or custom behavior by running in clean target
    scaffold(target, force=False)

    # Check that git user.name and user.email are set locally if not global
    name_res = subprocess.run(
        ["git", "-C", str(target), "config", "user.name"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert name_res.stdout.strip() != ""


def test_main_cli_surface(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "cli_sandbox"
    exit_code = main(["--target-dir", str(target), "--non-interactive"])
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "[scaffold]" in captured
    assert "Target directory:" in captured
    assert "Files created:" in captured
    assert "Hook installed:" in captured
    assert "Commit:" in captured
    assert "Verification:" in captured


def test_build_ticket_runner_yaml_default_mode() -> None:
    content = build_ticket_runner_yaml("default")
    assert "sandbox:" in content
    assert 'skills: "default"' in content
    assert "# Flip + re-run sync_agents_md.py --write --skills <default|all> to apply." in content


def test_build_ticket_runner_yaml_all_mode() -> None:
    content = build_ticket_runner_yaml("all")
    assert 'skills: "all"' in content


def test_scaffold_yaml_contains_sandbox_skills_default(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False)
    yaml_text = (target / "ticket-runner.yaml").read_text(encoding="utf-8")
    assert "sandbox:" in yaml_text
    assert 'skills: "default"' in yaml_text
    assert "# Flip + re-run sync_agents_md.py --write --skills <default|all> to apply." in yaml_text
    assert _read_yaml_sandbox_skills(target / "ticket-runner.yaml") == "default"


def test_scaffold_yaml_contains_sandbox_skills_all(tmp_path: Path) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False, skills_mode="all")
    yaml_text = (target / "ticket-runner.yaml").read_text(encoding="utf-8")
    assert 'skills: "all"' in yaml_text
    assert _read_yaml_sandbox_skills(target / "ticket-runner.yaml") == "all"


def test_scaffold_all_mode_prints_deferred_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False, skills_mode="all")
    captured = capsys.readouterr().out
    assert "[scaffold] all mode: 4 skills shipped (catalog enumeration deferred to T005d-impl)" in captured


def test_scaffold_default_mode_omits_deferred_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False, skills_mode="default")
    captured = capsys.readouterr().out
    assert "catalog enumeration deferred" not in captured


def test_yaml_reader_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert _read_yaml_sandbox_skills(tmp_path / "absent.yaml") is None


def test_yaml_reader_returns_none_for_missing_key(tmp_path: Path) -> None:
    yaml_file = tmp_path / "ticket-runner.yaml"
    yaml_file.write_text("sandbox: {}\n", encoding="utf-8")
    assert _read_yaml_sandbox_skills(yaml_file) is None


def test_yaml_reader_returns_none_for_invalid_value(tmp_path: Path) -> None:
    yaml_file = tmp_path / "ticket-runner.yaml"
    yaml_file.write_text('sandbox:\n  skills: "bogus"\n', encoding="utf-8")
    assert _read_yaml_sandbox_skills(yaml_file) is None


def test_yaml_reader_returns_none_for_malformed_yaml(tmp_path: Path) -> None:
    yaml_file = tmp_path / "ticket-runner.yaml"
    yaml_file.write_text("sandbox: [unclosed\n", encoding="utf-8")
    assert _read_yaml_sandbox_skills(yaml_file) is None


def test_resolve_skills_mode_cli_overrides_yaml(tmp_path: Path) -> None:
    (tmp_path / "ticket-runner.yaml").write_text(
        'sandbox:\n  skills: "all"\n', encoding="utf-8"
    )
    assert _resolve_skills_mode("default", tmp_path) == "default"
    assert _resolve_skills_mode("all", tmp_path) == "all"


def test_resolve_skills_mode_falls_back_to_yaml_then_default(tmp_path: Path) -> None:
    assert _resolve_skills_mode(None, tmp_path) == "default"
    (tmp_path / "ticket-runner.yaml").write_text(
        'sandbox:\n  skills: "all"\n', encoding="utf-8"
    )
    assert _resolve_skills_mode(None, tmp_path) == "all"
