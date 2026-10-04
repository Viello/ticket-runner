"""Unit tests for scripts/sync_agents_md.py."""

from __future__ import annotations

import datetime
from pathlib import Path
import pytest

from runner.tools.scaffold_sandbox import (
    DEFAULT_PREAMBLE,
    format_sandbox_agents_md,
)
from scripts.sync_agents_md import main


@pytest.fixture
def sample_upstream(tmp_path: Path) -> Path:
    upstream = tmp_path / "upstream_AGENTS.md"
    content = """# AGENTS.md

Ticket Runner description.

## Implementation status
Specs implemented.

## Invariants
- Invariant 1.
- Invariant 2.

## Environment
- Target platform is Windows/PowerShell.
- Dependencies: discord.py, rich, pyyaml, pytest.
- Discord and terminal-UI adapters are implemented under runner/adapters/.
- Pre-push hook guardrail is installed via runner/adapters/git/.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog.
- `.agents/skills/handoff/SKILL.md` is load-bearing.
- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline.
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline.
"""
    upstream.write_text(content, encoding="utf-8")
    return upstream


def test_sync_agents_md_in_sync(sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    sandbox_file = sandbox_dir / "AGENTS.md"

    # Create matching sandbox file with preamble and stamp.
    # Per T005c default-mode bullet trim: Environment keeps bullet #1 only;
    # Agent skills keeps bullets #2 + #3.
    curated_content = (
        "## Invariants\n"
        "- Invariant 1.\n"
        "- Invariant 2.\n\n"
        "## Environment\n"
        "- Target platform is Windows/PowerShell.\n\n"
        "## Agent skills\n"
        "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
        "- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline."
    )
    formatted = format_sandbox_agents_md(DEFAULT_PREAMBLE, "2026-10-01", curated_content)
    sandbox_file.write_text(formatted, encoding="utf-8")

    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "in sync" in captured.out.lower()


def test_sync_agents_md_drift_detected(sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    sandbox_file = sandbox_dir / "AGENTS.md"

    # Create diverged sandbox file (dropped a bullet T005c says to keep)
    curated_content = (
        "## Invariants\n"
        "- Diverged invariant.\n\n"
        "## Environment\n"
        "- Target platform is Windows/PowerShell.\n\n"
        "## Agent skills\n"
        "- .agents/skills/handoff/SKILL.md is load-bearing."
    )
    formatted = format_sandbox_agents_md(DEFAULT_PREAMBLE, "2026-10-01", curated_content)
    sandbox_file.write_text(formatted, encoding="utf-8")

    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "diverged invariant" in captured.out.lower() or "drift detected" in captured.err.lower()


def test_sync_agents_md_write_updates_sandbox(sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    sandbox_file = sandbox_dir / "AGENTS.md"

    # Create diverged sandbox file with custom preamble
    custom_preamble = "# Custom Sandbox Preamble\nLine 2\nLine 3\nLine 4\nLine 5"
    curated_content = "## Invariants\n- Old invariant."
    formatted = format_sandbox_agents_md(custom_preamble, "2020-01-01", curated_content)
    sandbox_file.write_text(formatted, encoding="utf-8")

    # Run with --write
    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
        "--write",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "updated" in captured.out.lower()

    # Verify updated content
    new_content = sandbox_file.read_text(encoding="utf-8")
    today = datetime.date.today().isoformat()
    assert f"<!-- mirrored from D:\\Projects/AGENTS.md on {today} -->" in new_content
    assert "- Invariant 1." in new_content
    assert custom_preamble in new_content

    # Next dry run should be in-sync
    code_after = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
    ])
    assert code_after == 0


def test_sync_agents_md_missing_files(tmp_path: Path) -> None:
    non_existent = tmp_path / "non_existent"
    code = main([
        "--target-dir", str(non_existent),
        "--upstream", str(non_existent / "upstream.md"),
    ])
    assert code == 2


def _curated_content(mode: str) -> str:
    """Build the curated subset matching ``extract_curated_subset`` output."""
    agent_skills = (
        "## Agent skills\n"
        "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
        "- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline."
    )
    if mode == "all":
        agent_skills = (
            "## Agent skills\n"
            "- `.agents/skills/` vendors the user's global skill catalog.\n"
            "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
            "- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline.\n"
            "- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline."
        )
    return (
        "## Invariants\n"
        "- Invariant 1.\n"
        "- Invariant 2.\n\n"
        "## Environment\n"
        "- Target platform is Windows/PowerShell.\n\n"
        + agent_skills
    )


def _seed_sandbox(sandbox_dir: Path, mode: str) -> Path:
    """Write a sandbox AGENTS.md curated in ``mode`` plus its ticket-runner.yaml."""
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    sandbox_file = sandbox_dir / "AGENTS.md"
    formatted = format_sandbox_agents_md(DEFAULT_PREAMBLE, "2026-10-01", _curated_content(mode))
    sandbox_file.write_text(formatted, encoding="utf-8")
    (sandbox_dir / "ticket-runner.yaml").write_text(
        f'sandbox:\n  skills: "{mode}"\n', encoding="utf-8"
    )
    return sandbox_file


def test_sync_default_scaffold_default_sync_in_sync(
    sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    _seed_sandbox(sandbox_dir, "default")
    code = main(["--target-dir", str(sandbox_dir), "--upstream", str(sample_upstream)])
    assert code == 0
    assert "in sync" in capsys.readouterr().out.lower()


def test_sync_all_scaffold_all_sync_in_sync(
    sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    _seed_sandbox(sandbox_dir, "all")
    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
        "--skills", "all",
    ])
    assert code == 0
    assert "in sync" in capsys.readouterr().out.lower()


def test_sync_yaml_mode_resolution_when_cli_absent(
    sample_upstream: Path, tmp_path: Path
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    _seed_sandbox(sandbox_dir, "all")
    # No --skills flag: the YAML's sandbox.skills: all drives the mode.
    code = main(["--target-dir", str(sandbox_dir), "--upstream", str(sample_upstream)])
    assert code == 0


def test_sync_cross_mode_drift_default_scaffold_all_sync(
    sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    _seed_sandbox(sandbox_dir, "default")
    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
        "--skills", "all",
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "security-review" in captured.out or "drift detected" in captured.err.lower()


def test_sync_cross_mode_drift_all_scaffold_default_sync(
    sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    _seed_sandbox(sandbox_dir, "all")
    # YAML says all but CLI pins default -> resolved default -> 2 bullets vs 4 -> drift.
    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
        "--skills", "default",
    ])
    assert code == 1
    captured = capsys.readouterr()
    assert "drift detected" in captured.err.lower() or "vendors the user's global" in captured.out


def test_sync_apply_auto_rewrites_on_yaml_mismatch(
    sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    # All-mode curated body, but YAML says default -> YAML-driven drift.
    _seed_sandbox(sandbox_dir, "all")
    (sandbox_dir / "ticket-runner.yaml").write_text(
        'sandbox:\n  skills: "default"\n', encoding="utf-8"
    )

    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
        "--apply",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "[sync] Applied sandbox.skills=default to AGENTS.md." in captured.out

    rewritten = (sandbox_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "vendors the user's global skill catalog" not in rewritten
    assert "security-review/SKILL.md" not in rewritten

    # A follow-up dry run is now clean.
    code_after = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
    ])
    assert code_after == 0


def test_sync_apply_no_op_when_yaml_agrees(
    sample_upstream: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sandbox_dir = tmp_path / "sandbox"
    sandbox_file = _seed_sandbox(sandbox_dir, "default")
    before = sandbox_file.read_text(encoding="utf-8")

    code = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(sample_upstream),
        "--apply",
    ])
    assert code == 0
    captured = capsys.readouterr()
    assert "Already in sync with sandbox.skills=default." in captured.out
    assert sandbox_file.read_text(encoding="utf-8") == before


def test_sync_agents_md_sanitizes_upstream_adrs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    upstream = tmp_path / "upstream_AGENTS.md"
    upstream.write_text(
        "# AGENTS.md\n\n"
        "## Invariants\n"
        "- Rule with ADR (ADR 0001).\n\n"
        "## Environment\n"
        "- Target platform is Windows/PowerShell.\n\n"
        "## Agent skills\n"
        "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
        "- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline.\n",
        encoding="utf-8",
    )

    sandbox_dir = tmp_path / "sandbox"
    sandbox_dir.mkdir()
    sandbox_file = sandbox_dir / "AGENTS.md"

    # Seed sandbox with sanitized invariant (no ADR)
    curated = (
        "## Invariants\n"
        "- Rule with ADR.\n\n"
        "## Environment\n"
        "- Target platform is Windows/PowerShell.\n\n"
        "## Agent skills\n"
        "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
        "- `.agents/skills/implement/SKILL.md` defines the default worker implementation discipline."
    )
    sandbox_file.write_text(
        format_sandbox_agents_md(DEFAULT_PREAMBLE, "2026-10-01", curated),
        encoding="utf-8",
    )

    code = main(["--target-dir", str(sandbox_dir), "--upstream", str(upstream)])
    assert code == 0
    assert "in sync" in capsys.readouterr().out.lower()

    # If we write/apply, ensure the rewritten output is also sanitized
    code_write = main([
        "--target-dir", str(sandbox_dir),
        "--upstream", str(upstream),
        "--write",
    ])
    assert code_write == 0
    assert "(ADR" not in sandbox_file.read_text(encoding="utf-8")

