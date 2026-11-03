from __future__ import annotations


import pathlib

import pytest

from scripts.publish_agent_skills import (
    SkillMetadata,
    parse_skill_metadata,
    load_all_skills,
    generate_catalog_readme,
    generate_license,
    sanitize_and_copy_skills,
    audit_files_for_secrets,
    validate_catalog_signal_contracts,
    publish_skills,
)


def test_parse_skill_metadata(tmp_path: pathlib.Path) -> None:
    skill_dir = tmp_path / "sample-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: sample-skill\n"
        "description: \"A sample skill for testing purposes.\"\n"
        "---\n\n"
        "# Sample Skill\n"
        "Instructions here.\n",
        encoding="utf-8",
    )

    meta = parse_skill_metadata(skill_dir)
    assert meta.name == "sample-skill"
    assert meta.description == "A sample skill for testing purposes."
    assert meta.path == skill_dir


def test_load_all_skills(tmp_path: pathlib.Path) -> None:
    for name in ["skill-b", "skill-a"]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Desc for {name}\n---\n", encoding="utf-8")
    
    # Also create a non-skill directory
    non_skill = tmp_path / "not-a-skill"
    non_skill.mkdir()

    skills = load_all_skills(tmp_path)
    assert len(skills) == 2
    assert skills[0].name == "skill-a"
    assert skills[1].name == "skill-b"


def test_generate_catalog_readme() -> None:
    skills = [
        SkillMetadata(name="implement", description="Implement tickets using TDD.", path=pathlib.Path("implement")),
        SkillMetadata(name="code-review", description="Review code changes.", path=pathlib.Path("code-review")),
    ]
    readme = generate_catalog_readme(skills)
    assert "# Agent Skills Catalog" in readme
    assert "[implement](implement/SKILL.md)" in readme or "`implement`" in readme
    assert "Implement tickets using TDD." in readme
    assert "[code-review](code-review/SKILL.md)" in readme or "`code-review`" in readme


def test_generate_license() -> None:
    license_text = generate_license()
    assert "MIT License" in license_text
    assert "Viello" in license_text


def test_sanitize_and_copy_skills(tmp_path: pathlib.Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()

    # Skill with valid files and ignored files
    skill1 = source_dir / "my-skill"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text("# My Skill", encoding="utf-8")
    pycache = skill1 / "__pycache__"
    pycache.mkdir()
    (pycache / "temp.pyc").write_bytes(b"bytecode")
    (skill1 / ".env").write_text("SECRET=123", encoding="utf-8")

    copied = sanitize_and_copy_skills(source_dir, target_dir)
    assert "my-skill" in copied
    assert (target_dir / "my-skill" / "SKILL.md").exists()
    assert not (target_dir / "my-skill" / "__pycache__").exists()
    assert not (target_dir / "my-skill" / ".env").exists()


def test_audit_files_for_secrets(tmp_path: pathlib.Path) -> None:
    safe_dir = tmp_path / "safe"
    safe_dir.mkdir()
    (safe_dir / "SKILL.md").write_text("# Clean documentation\nNo secrets here.", encoding="utf-8")

    findings = audit_files_for_secrets(safe_dir)
    assert findings == []

    leaky_dir = tmp_path / "leaky"
    leaky_dir.mkdir()
    (leaky_dir / "bad.txt").write_text("ghp_1234567890abcdefghijklmnopqrstuvwxyz", encoding="utf-8")

    leaky_findings = audit_files_for_secrets(leaky_dir)
    assert len(leaky_findings) > 0
    assert "GitHub personal access token" in leaky_findings[0] or "token" in leaky_findings[0].lower()


def test_validate_catalog_signal_contracts_clean_catalog(tmp_path: pathlib.Path) -> None:
    for name in ["skill-a", "skill-b"]:
        d = tmp_path / name
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Clean\n---\n# {name}\nNo json here.",
            encoding="utf-8",
        )
    skills = load_all_skills(tmp_path)
    violations = validate_catalog_signal_contracts(skills)
    assert violations == []


def test_validate_catalog_signal_contracts_catches_invalid_example(tmp_path: pathlib.Path) -> None:
    clean = tmp_path / "clean-skill"
    clean.mkdir()
    (clean / "SKILL.md").write_text(
        "---\nname: clean-skill\ndescription: Clean\n---\n# Clean",
        encoding="utf-8",
    )

    stale = tmp_path / "stale-skill"
    stale.mkdir()
    (stale / "SKILL.md").write_text(
        "---\nname: stale-skill\ndescription: Stale\n---\n# Stale\n\n```json\n"
        "{\n"
        '  "ticket_id": "<ticket_id>",\n'
        '  "question": "Missing type field",\n'
        '  "timestamp": "<ISO-8601-UTC>"\n'
        "}\n```\n",
        encoding="utf-8",
    )

    skills = load_all_skills(tmp_path)
    violations = validate_catalog_signal_contracts(skills)
    assert len(violations) == 1
    assert "stale-skill/SKILL.md" in violations[0]
    assert "missing required field 'type'" in violations[0]


def test_publish_skills_aborts_before_staging_on_invalid_catalog(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any

    stale = tmp_path / "stale-skill"
    stale.mkdir()
    (stale / "SKILL.md").write_text(
        "---\nname: stale-skill\ndescription: Stale\n---\n# Stale\n\n```json\n"
        "{\n"
        '  "ticket_id": "<ticket_id>",\n'
        '  "question": "What is this?",\n'
        '  "timestamp": "<ISO-8601-UTC>"\n'
        "}\n```\n",
        encoding="utf-8",
    )

    staging_attempted = False

    def fake_sanitize_and_copy(*args: Any, **kwargs: Any) -> list[str]:
        nonlocal staging_attempted
        staging_attempted = True
        return []

    monkeypatch.setattr("scripts.publish_agent_skills.sanitize_and_copy_skills", fake_sanitize_and_copy)

    with pytest.raises(RuntimeError, match="Signal contract validation failed"):
        publish_skills(source_dir=tmp_path)

    assert staging_attempted is False


def test_publish_skills_dry_run_aborts_before_staging_on_invalid_catalog(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typing import Any

    stale = tmp_path / "stale-skill"
    stale.mkdir()
    (stale / "SKILL.md").write_text(
        "---\nname: stale-skill\ndescription: Stale\n---\n# Stale\n\n```json\n"
        "{\n"
        '  "ticket_id": "<ticket_id>",\n'
        '  "question": "What is this?",\n'
        '  "timestamp": "<ISO-8601-UTC>"\n'
        "}\n```\n",
        encoding="utf-8",
    )

    staging_attempted = False

    def fake_sanitize_and_copy(*args: Any, **kwargs: Any) -> list[str]:
        nonlocal staging_attempted
        staging_attempted = True
        return []

    monkeypatch.setattr("scripts.publish_agent_skills.sanitize_and_copy_skills", fake_sanitize_and_copy)

    with pytest.raises(RuntimeError, match="Signal contract validation failed"):
        publish_skills(source_dir=tmp_path, dry_run=True)

    assert staging_attempted is False


def test_publish_skills_dry_run_reaches_staging_on_valid_catalog(tmp_path: pathlib.Path) -> None:
    valid = tmp_path / "valid-skill"
    valid.mkdir()
    (valid / "SKILL.md").write_text(
        "---\nname: valid-skill\ndescription: Valid skill description\n---\n# Valid Skill\n\n```json\n"
        "{\n"
        '  "ticket_id": "<ticket_id>",\n'
        '  "status": "ready_for_verification",\n'
        '  "modified_files": ["main.py"],\n'
        '  "self_review_notes": "All checks passed.",\n'
        '  "new_gotchas": [],\n'
        '  "timestamp": "<ISO-8601-UTC>",\n'
        '  "scope": "implementation"\n'
        "}\n```\n",
        encoding="utf-8",
    )

    result = publish_skills(source_dir=tmp_path, dry_run=True)
    assert result["dry_run"] is True
    assert result["skills_count"] == 1
    assert "valid-skill" in result["staged_skills"]


def _make_tarball_bytes(names: list[str]) -> bytes:
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for name in names:
            ti = tarfile.TarInfo(name=name)
            data = b"# skill"
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self._data = data
        self.status = status

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass


def test_verify_tarball_endpoint_passes_when_all_skills_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify verify_tarball_endpoint passes when all 6 -ticket-runner skills and implement exist."""
    import urllib.request
    from scripts.publish_agent_skills import verify_tarball_endpoint

    all_names = [
        "Viello-agent-skills-12345/implement/SKILL.md",
        "Viello-agent-skills-12345/to-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/implement-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/code-review-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/security-review-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/diagnosing-bugs-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/handoff-ticket-runner/SKILL.md",
    ]
    tar_bytes = _make_tarball_bytes(all_names)

    monkeypatch.setattr(urllib.request, "urlopen", lambda req: _FakeResponse(tar_bytes))
    count = verify_tarball_endpoint(repo="Viello/agent-skills", branch="main")
    assert count == 7


@pytest.mark.parametrize("missing_skill", [
    "to-ticket-runner",
    "implement-ticket-runner",
    "code-review-ticket-runner",
    "security-review-ticket-runner",
    "diagnosing-bugs-ticket-runner",
    "handoff-ticket-runner",
])
def test_verify_tarball_endpoint_fails_when_any_ticket_runner_skill_missing(
    monkeypatch: pytest.MonkeyPatch, missing_skill: str
) -> None:
    """Verify verify_tarball_endpoint raises AssertionError when any -ticket-runner skill is missing."""
    import urllib.request
    from scripts.publish_agent_skills import verify_tarball_endpoint

    all_names = [
        "Viello-agent-skills-12345/implement/SKILL.md",
        "Viello-agent-skills-12345/to-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/implement-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/code-review-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/security-review-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/diagnosing-bugs-ticket-runner/SKILL.md",
        "Viello-agent-skills-12345/handoff-ticket-runner/SKILL.md",
    ]
    remaining = [n for n in all_names if f"/{missing_skill}/" not in n]
    tar_bytes = _make_tarball_bytes(remaining)

    monkeypatch.setattr(urllib.request, "urlopen", lambda req: _FakeResponse(tar_bytes))
    with pytest.raises(AssertionError, match=f"'{missing_skill}/SKILL.md'"):
        verify_tarball_endpoint(repo="Viello/agent-skills", branch="main")
