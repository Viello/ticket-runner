"""Unit tests validating create-verification-skill and maintain-verification-skill meta-skills (T112)."""

from __future__ import annotations

from pathlib import Path
import re
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
CREATE_SKILL_PATH = SKILLS_DIR / "create-verification-skill" / "SKILL.md"
MAINTAIN_SKILL_PATH = SKILLS_DIR / "maintain-verification-skill" / "SKILL.md"


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a markdown file."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        raise ValueError("Missing or invalid YAML frontmatter")
    frontmatter_raw, body = match.groups()
    data = yaml.safe_load(frontmatter_raw)
    return data, body


def test_create_verification_skill_exists_and_has_valid_frontmatter() -> None:
    assert CREATE_SKILL_PATH.is_file(), f"Missing {CREATE_SKILL_PATH}"
    content = CREATE_SKILL_PATH.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(content)

    assert frontmatter.get("name") == "create-verification-skill"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter.get("disable-model-invocation") is True
    assert len(body.strip()) > 100


def test_create_verification_skill_documents_surface_detection() -> None:
    content = CREATE_SKILL_PATH.read_text(encoding="utf-8")

    # Surface detection coverage
    assert "Playwright" in content
    assert "package.json" in content
    assert "pyproject.toml" in content
    assert "CLI" in content or "subprocess" in content
    assert "API" in content or "curl" in content or "HTTP" in content


def test_create_verification_skill_documents_lifecycle_and_harness_contract() -> None:
    content = CREATE_SKILL_PATH.read_text(encoding="utf-8")

    # 5-step lifecycle contract
    lifecycle_steps = ["Launch", "Doctor", "Drive", "Evidence", "Cleanup"]
    for step in lifecycle_steps:
        assert step in content, f"Missing lifecycle step: {step}"

    # Harness stub requirements
    harness_stubs = ["launch", "doctor", "drive", "cleanup"]
    for stub in harness_stubs:
        assert f"`{stub}`" in content or f"harness/{stub}" in content

    # Stub documentation and surface type comments
    assert "Surface:" in content
    assert "Web UI" in content
    assert "CLI" in content
    assert "API" in content

    # Evidence directory requirement
    assert ".agent/evidence/" in content

    # Feature map contract
    assert "features/" in content
    assert "40 lines" in content or "<=40 lines" in content or "<= 40 lines" in content
    for section in ["Sub-features", "User POV Path", "Driving Harness", "Gotchas"]:
        assert section in content, f"Missing feature section in contract: {section}"


def test_create_verification_skill_template_adheres_to_feature_map_contract() -> None:
    content = CREATE_SKILL_PATH.read_text(encoding="utf-8")

    # Extract template block from markdown
    template_match = re.search(r"```markdown\s*\n(# Feature:.*?)\n```", content, re.DOTALL)
    assert template_match is not None, "Feature template block not found in create-verification-skill"
    template_text = template_match.group(1)

    lines = template_text.strip().splitlines()
    assert len(lines) <= 40, f"Template exceeded 40 lines: {len(lines)}"

    required_sections = ["### Sub-features", "### User POV Path", "### Driving Harness", "### Gotchas"]
    for sec in required_sections:
        assert sec in template_text, f"Template missing section: {sec}"


def test_maintain_verification_skill_exists_and_has_valid_frontmatter() -> None:
    assert MAINTAIN_SKILL_PATH.is_file(), f"Missing {MAINTAIN_SKILL_PATH}"
    content = MAINTAIN_SKILL_PATH.read_text(encoding="utf-8")
    frontmatter, body = _parse_frontmatter(content)

    assert frontmatter.get("name") == "maintain-verification-skill"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter.get("disable-model-invocation") is True
    assert len(body.strip()) > 100


def test_maintain_verification_skill_documents_audit_process() -> None:
    content = MAINTAIN_SKILL_PATH.read_text(encoding="utf-8")

    # Audit operations
    assert "orphaned" in content.lower()
    assert "uncovered" in content.lower() or "missing" in content.lower()
    assert "features/" in content
    assert "40 lines" in content or "<=40 lines" in content or "<= 40 lines" in content
    for section in ["Sub-features", "User POV Path", "Driving Harness", "Gotchas"]:
        assert section in content, f"Missing feature section in contract: {section}"
