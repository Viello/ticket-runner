"""Unit tests validating dual-track skills catalog and local vendoring (T128)."""

from __future__ import annotations

from pathlib import Path
import re
import yaml

from runner.adapters.markdown.parser import TicketMarkdownParser
from runner.domain.ticket import TicketStatus

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
UPSTREAM_SKILLS_DIR = Path(r"D:\Repos\agent-skills")


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        raise ValueError("Missing or invalid YAML frontmatter")
    frontmatter_raw, body = match.groups()
    data = yaml.safe_load(frontmatter_raw)
    return data, body


def test_to_ticket_runner_skill_conforms_to_specimen_a() -> None:
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        skill_dir = base_dir / "to-ticket-runner"
        skill_md = skill_dir / "SKILL.md"
        openai_yaml = skill_dir / "agents" / "openai.yaml"

        assert skill_md.is_file(), f"Missing {skill_md}"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        assert frontmatter.get("name") == "to-ticket-runner"
        assert len(frontmatter.get("description", "")) > 10
        assert frontmatter.get("disable-model-invocation") is True

        assert openai_yaml.is_file(), f"Missing {openai_yaml}"
        openai_data = yaml.safe_load(openai_yaml.read_text(encoding="utf-8"))
        assert "interface" in openai_data
        assert "To Ticket Runner" in openai_data["interface"].get("display_name", "")

        # Template inspection
        match = re.search(r"^\s*<ticket-runner-template>\s*\n([\s\S]*?)\n\s*</ticket-runner-template>", body, re.MULTILINE)
        assert match is not None, f"Missing <ticket-runner-template> in {skill_md}"
        template_text = match.group(1)

        assert "**Mode:** AFK" in template_text or "**Mode:**" in template_text
        assert "**Status:** pending" in template_text
        assert "**Spec:**" in template_text
        assert "**Blocked by:**" in template_text
        assert "## What to build" in template_text
        assert "## Jump-start" in template_text
        assert "## Acceptance criteria" in template_text
        assert "## Smoke scenarios" in template_text
        assert "## Gotchas" in template_text
        assert "- [ ]" in template_text

        # Validate that the template parses with TicketMarkdownParser
        sample = (
            template_text.replace("<spec-slug>", "demo-spec")
            .replace("<slug>", "demo")
            .replace("<NNN>", "101")
            .replace("<Ticket title>", "Demo Title")
            .replace("<The end-to-end behaviour this Ticket makes work, from the user's perspective,\nnot a layer-by-layer implementation list.>", "Build end to end demo.")
            .replace("<the seam to work at>", "seam")
            .replace("<functions, types, or patterns to model against>", "Anchor")
            .replace("<the command or demo that proves the slice>", "pytest")
            .replace("Criterion 1", "Work is done")
            .replace("Criterion 2", "Tests pass")
            .replace("<name>", "scenario_1")
            .replace("<the state to arrange>", "state")
            .replace("<what the scenario proves>", "proves")
            .replace("<action>", "action")
            .replace("<the observable outcome>", "outcome")
            .replace("<ticket-specific quirk, pitfall, or constraint>", "None")
        )
        # In case there are other placeholders
        sample = re.sub(r"<.*?>", "stub", sample)
        tmp_ticket = REPO_ROOT / ".agent" / "temp_t128_specimen_a.md"
        tmp_ticket.parent.mkdir(parents=True, exist_ok=True)
        try:
            tmp_ticket.write_text(sample, encoding="utf-8")
            ticket = TicketMarkdownParser().parse(tmp_ticket)
            assert ticket.id == "T101"
            assert ticket.status is TicketStatus.PENDING
            assert ticket.mode in ("AFK", "HITL")
        finally:
            if tmp_ticket.exists():
                tmp_ticket.unlink()


def test_implement_ticket_runner_skill_conforms_to_autonomous_spec() -> None:
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        skill_dir = base_dir / "implement-ticket-runner"
        skill_md = skill_dir / "SKILL.md"
        openai_yaml = skill_dir / "agents" / "openai.yaml"

        assert skill_md.is_file(), f"Missing {skill_md}"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        assert frontmatter.get("name") == "implement-ticket-runner"
        assert len(frontmatter.get("description", "")) > 10
        assert frontmatter.get("disable-model-invocation") is True

        assert openai_yaml.is_file(), f"Missing {openai_yaml}"
        openai_data = yaml.safe_load(openai_yaml.read_text(encoding="utf-8"))
        assert "interface" in openai_data
        assert "Implement Ticket Runner" in openai_data["interface"].get("display_name", "")

        # Must contain autonomous instructions
        assert "Jump-start" in body
        assert "Stuck-Test-Suite Protocol" in body or "stuck-test-suite" in body.lower()
        assert "code-review" in body
        assert "Acceptance criteria" in body
        assert "- [ ]" in body and "- [x]" in body
        assert ".agent/signals/" in body
        assert ".agent/questions/" in body
        # Worker must never commit or relocate files
        assert "never commit" in body.lower() or "never run `git commit`" in body.lower()
        assert "never relocate" in body.lower() or "gatekeeper relocates" in body.lower() or "gatekeeper owns" in body.lower()


def test_to_tickets_skill_conforms_to_specimen_b() -> None:
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        skill_dir = base_dir / "to-tickets"
        skill_md = skill_dir / "SKILL.md"

        assert skill_md.is_file(), f"Missing {skill_md}"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        assert frontmatter.get("name") == "to-tickets"
        assert "**Status:** ready-for-agent" in body
        assert "**What to build:**" in body
        assert "**Jump-start:**" in body
        assert "**Blocked by:**" in body
        assert "- [ ]" in body
        assert "completed/" in body


def test_implement_skill_is_pure_human_ai_interactive() -> None:
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        skill_dir = base_dir / "implement"
        skill_md = skill_dir / "SKILL.md"

        assert skill_md.is_file(), f"Missing {skill_md}"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        assert frontmatter.get("name") == "implement"
        # Zero autonomous signal noise
        assert ".agent/signals/" not in body
        assert ".agent/questions/" not in body
        assert "ready_for_verification" not in body

        # Supports both to-tickets and to-ticket-runner
        assert "to-tickets" in body
        assert "to-ticket-runner" in body
        assert "**Status:** completed" in body
        assert "**Completed:**" in body
        assert "**Status note:**" in body
        assert "completed/" in body
        assert "gotchas.md" in body


def test_code_review_skill_runs_3_axis_review() -> None:
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        skill_dir = base_dir / "code-review"
        skill_md = skill_dir / "SKILL.md"

        assert skill_md.is_file(), f"Missing {skill_md}"
        content = skill_md.read_text(encoding="utf-8")

        assert "Standards" in content
        assert "Spec" in content
        assert "Security" in content
        assert "security-review" in content
        assert "ready-for-human" in content or "escalat" in content.lower()


def test_smoke_fail_skill_uses_specimen_a_template() -> None:
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        skill_dir = base_dir / "smoke-fail"
        skill_md = skill_dir / "SKILL.md"

        assert skill_md.is_file(), f"Missing {skill_md}"
        content = skill_md.read_text(encoding="utf-8")

        match = re.search(r"<ticket-runner-template>\s*([\s\S]*?)\s*</ticket-runner-template>", content)
        assert match is not None
        template_text = match.group(1)

        assert "**Mode:** AFK" in template_text or "**Mode:**" in template_text
        assert "**Status:** pending" in template_text
        assert "## What to build" in template_text
        assert "## Jump-start" in template_text
        assert "## Acceptance criteria" in template_text
        assert "## Smoke scenarios" in template_text
        assert "## Gotchas" in template_text
        assert "- [ ]" in template_text


def test_ask_matt_and_readme_document_both_tracks_and_50_skills() -> None:
    # 1. Total skills count in upstream
    upstream_skills = [
        d for d in UPSTREAM_SKILLS_DIR.iterdir()
        if d.is_dir() and (d / "SKILL.md").is_file() and not d.name.startswith(".")
    ]
    assert len(upstream_skills) == 50, f"Expected 50 skills in {UPSTREAM_SKILLS_DIR}, found {len(upstream_skills)}"

    # 2. README.md check
    readme_path = UPSTREAM_SKILLS_DIR / "README.md"
    assert readme_path.is_file()
    readme_content = readme_path.read_text(encoding="utf-8")
    assert "**50**" in readme_content or "50 canonical skills" in readme_content
    assert "to-ticket-runner" in readme_content
    assert "implement-ticket-runner" in readme_content

    # 3. ask-matt checks
    for base_dir in [UPSTREAM_SKILLS_DIR, LOCAL_SKILLS_DIR]:
        ask_matt_md = base_dir / "ask-matt" / "SKILL.md"
        assert ask_matt_md.is_file()
        content = ask_matt_md.read_text(encoding="utf-8")
        assert "to-ticket-runner" in content
        assert "implement-ticket-runner" in content
        assert "to-tickets" in content
        assert "implement" in content


def test_publish_agent_skills_script_verifies_dual_tracks() -> None:
    script_path = REPO_ROOT / "scripts" / "publish_agent_skills.py"
    content = script_path.read_text(encoding="utf-8")
    assert "implement-ticket-runner/SKILL.md" in content
    assert "to-ticket-runner/SKILL.md" in content
    assert "openai.yaml" in content and "agents/" in content
