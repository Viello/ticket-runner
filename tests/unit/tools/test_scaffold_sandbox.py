"""Unit tests for runner.tools.scaffold_sandbox."""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.error
import pytest

from runner.adapters.git.pre_push_hook import PrePushHookInstaller
from runner.tools.scaffold_sandbox import (
    DEFAULT_PREAMBLE,
    _read_yaml_sandbox_skills,
    _resolve_skills_mode,
    build_ticket_runner_yaml,
    extract_curated_subset,
    fetch_public_skills_catalog,
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
    for skill in ("implement-ticket-runner", "code-review", "diagnosing-bugs", "handoff"):
        skill_file = target / ".agents" / "skills" / skill / "SKILL.md"
        assert skill_file.is_file()

    # 3. docs/tickets/00-welcome/T001-hello-world.md
    welcome_ticket = target / "docs" / "tickets" / "00-welcome" / "T001-hello-world.md"
    assert welcome_ticket.is_file()
    assert "**Status:** pending" in welcome_ticket.read_text(encoding="utf-8")

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


def test_fetch_public_skills_catalog_from_tarball(monkeypatch: pytest.MonkeyPatch) -> None:
    # Synthesize an in-memory tarball with 2 skills and an extra non-skill file
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Extra non-skill file
        readme_data = b"# Readme\n"
        ti = tarfile.TarInfo(name="agent-skills-main/README.md")
        ti.size = len(readme_data)
        tar.addfile(ti, io.BytesIO(readme_data))

        # Skill 1
        skill1_data = b"---\nname: skill-one\n---\n# Skill One\n"
        ti1 = tarfile.TarInfo(name="agent-skills-main/skill-one/SKILL.md")
        ti1.size = len(skill1_data)
        tar.addfile(ti1, io.BytesIO(skill1_data))

        # Skill 2
        skill2_data = b"---\nname: skill-two\n---\n# Skill Two\n"
        ti2 = tarfile.TarInfo(name="agent-skills-main/skill-two/SKILL.md")
        ti2.size = len(skill2_data)
        tar.addfile(ti2, io.BytesIO(skill2_data))

    tar_bytes = buf.getvalue()

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return tar_bytes

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=15.0: FakeResponse(),
    )

    catalog = fetch_public_skills_catalog()
    assert len(catalog) == 2
    assert "skill-one" in catalog
    assert "skill-two" in catalog
    assert "# Skill One" in catalog["skill-one"]
    assert "# Skill Two" in catalog["skill-two"]


def test_fetch_public_skills_catalog_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        readme_data = b"# Readme\n"
        ti = tarfile.TarInfo(name="agent-skills-main/README.md")
        ti.size = len(readme_data)
        tar.addfile(ti, io.BytesIO(readme_data))

    tar_bytes = buf.getvalue()

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def read(self) -> bytes:
            return tar_bytes

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=15.0: FakeResponse(),
    )

    with pytest.raises(ValueError, match="No skills found"):
        fetch_public_skills_catalog()


def test_scaffold_all_mode_with_source_skills_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_catalog = tmp_path / "fake_catalog"
    for i in range(1, 6):
        skill_dir = fake_catalog / f"fake-skill-{i}"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: fake-skill-{i}\n---\n# Skill {i}\n", encoding="utf-8")

    target = tmp_path / "sandbox"
    scaffold(target, force=False, skills_mode="all", source_skills_dir=fake_catalog)
    captured = capsys.readouterr().out

    # More than 4 skills shipped
    target_skills = list((target / ".agents" / "skills").iterdir())
    assert len(target_skills) == 5
    for i in range(1, 6):
        assert (target / ".agents" / "skills" / f"fake-skill-{i}" / "SKILL.md").is_file()

    assert "[scaffold] all mode: 5 skills shipped from" in captured
    assert "deferred to T005d-impl" not in captured


def test_scaffold_all_mode_network_fallback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_network_error(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("Network unreachable (simulated)")

    monkeypatch.setattr("runner.tools.scaffold_sandbox.fetch_public_skills_catalog", raise_network_error)

    target = tmp_path / "sandbox"
    scaffold(target, force=False, skills_mode="all")
    captured = capsys.readouterr().out

    # Ships 4 curated skills on fallback
    target_skills = list((target / ".agents" / "skills").iterdir())
    assert len(target_skills) == 4
    for skill_name in ("implement-ticket-runner", "code-review", "diagnosing-bugs", "handoff"):
        assert (target / ".agents" / "skills" / skill_name / "SKILL.md").is_file()

    assert "[scaffold] Warning: Failed to fetch skill catalog from Viello/agent-skills" in captured
    assert "[scaffold] all mode: 4 skills shipped (fallback to curated default)" in captured
    assert "deferred to T005d-impl" not in captured


def test_scaffold_all_mode_live_network(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "sandbox"
    scaffold(target, force=False, skills_mode="all")
    captured = capsys.readouterr().out

    target_skills = [d for d in (target / ".agents" / "skills").iterdir() if d.is_dir()]
    assert len(target_skills) > 4
    assert "[scaffold] all mode: " in captured
    assert "skills shipped from Viello/agent-skills" in captured
    assert "deferred to T005d-impl" not in captured


def test_main_cli_skills_all_source_skills_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fake_catalog = tmp_path / "cli_catalog"
    for i in range(1, 6):
        skill_dir = fake_catalog / f"cli-skill-{i}"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: cli-skill-{i}\n---\n# CLI Skill {i}\n", encoding="utf-8")

    target = tmp_path / "cli_sandbox"
    code = main([
        "--target-dir", str(target),
        "--non-interactive",
        "--skills", "all",
        "--source-skills-dir", str(fake_catalog),
    ])
    assert code == 0
    captured = capsys.readouterr().out
    target_skills = [d for d in (target / ".agents" / "skills").iterdir() if d.is_dir()]
    assert len(target_skills) == 5
    assert "[scaffold] all mode: 5 skills shipped from" in captured
    assert "deferred to T005d-impl" not in captured


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


def test_scaffold_sanitizes_adr_and_welcome_spec(tmp_path: Path) -> None:
    """Scaffold output sanitization strips ADRs and replaces welcome ticket spec."""
    upstream_file = tmp_path / "upstream_AGENTS.md"
    upstream_file.write_text(
        "# AGENTS.md\n\n"
        "## Invariants\n"
        "- Invariant with ref (ADR 0001).\n"
        "- Invariant with another ref (ADR 0004).\n\n"
        "## Environment\n"
        "- Target platform is Windows/PowerShell.\n\n"
        "## Agent skills\n"
        "- `.agents/skills/handoff/SKILL.md` is load-bearing.\n"
        "- `.agents/skills/implement/SKILL.md` defines the default worker.\n",
        encoding="utf-8",
    )

    target = tmp_path / "sandbox"
    scaffold(target, force=False, upstream_agents_md=upstream_file)

    # 1. AGENTS.md must contain no (ADR references
    agents_text = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "(ADR" not in agents_text
    assert "- Invariant with ref." in agents_text
    assert "- Invariant with another ref." in agents_text

    # 2. Welcome ticket must carry a non-empty Spec: with no docs/specs/<name>.md
    ticket_text = (
        target / "docs" / "tickets" / "00-welcome" / "T001-hello-world.md"
    ).read_text(encoding="utf-8")
    assert "docs/specs/" not in ticket_text
    assert "**Spec:** N/A (sandbox demo)" in ticket_text

