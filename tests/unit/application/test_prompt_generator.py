"""Unit tests for AIPromptGenerator application service."""

from __future__ import annotations

import yaml
from runner.application.prompt_generator import AIPromptGenerator
from runner.domain.scaffolding import ProjectHeuristics


def test_prompt_generator_generates_markdown_without_heuristics() -> None:
    prompt = AIPromptGenerator.generate()

    assert isinstance(prompt, str)
    assert "# Ticket Runner Configuration Prompt" in prompt or "ticket-runner.yaml" in prompt
    assert "ticket-runner.yaml" in prompt
    # Must explain decoupled orchestrator model
    assert "orchestrator" in prompt.lower() or "runner" in prompt.lower()
    # Must document schema
    assert "project:" in prompt
    assert "verification:" in prompt
    assert "worker:" in prompt
    # Must contain guidelines for inspecting build/test files
    assert "test" in prompt.lower()
    assert "build" in prompt.lower()
    # Must include stack examples
    assert "python" in prompt.lower()
    assert "node" in prompt.lower()
    assert "rust" in prompt.lower()
    assert "go" in prompt.lower()


def test_prompt_generator_includes_heuristics_context() -> None:
    heuristics = ProjectHeuristics(
        name="my-app",
        detected_stack="python",
        test_cmd="python -m pytest tests/unit",
        build_cmd="",
        base_branch="main",
        branch="agent/ticket-runner",
        provider="opencode",
    )

    prompt = AIPromptGenerator.generate(heuristics)

    assert "my-app" in prompt
    assert "python -m pytest tests/unit" in prompt
    assert "python" in prompt
    assert "agent/ticket-runner" in prompt


def test_prompt_generator_minimal_schema_under_15_lines() -> None:
    prompt = AIPromptGenerator.generate()

    # Extract yaml code blocks
    lines = prompt.splitlines()
    in_yaml = False
    yaml_blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        if line.strip().startswith("```yaml"):
            in_yaml = True
            current_block = []
        elif line.strip() == "```" and in_yaml:
            in_yaml = False
            yaml_blocks.append(current_block)
        elif in_yaml:
            current_block.append(line)

    assert len(yaml_blocks) > 0, "Prompt must contain at least one fenced YAML block"
    # Find minimal sample block
    valid_configs = []
    for block in yaml_blocks:
        content = "\n".join(block)
        try:
            parsed = yaml.safe_load(content)
            if isinstance(parsed, dict) and "project" in parsed and "verification" in parsed:
                valid_configs.append(block)
        except Exception:
            pass

    assert len(valid_configs) > 0, "Must contain a valid ticket-runner.yaml example"
    # Ensure at least one valid schema example is under 15 lines
    assert any(len(block) < 15 for block in valid_configs)
