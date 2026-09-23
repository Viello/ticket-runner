"""Application service for generating LLM configuration prompts."""

from __future__ import annotations

from runner.domain.scaffolding import ProjectHeuristics

__all__ = ["AIPromptGenerator"]


class AIPromptGenerator:
    """Formats self-contained Markdown prompts for LLM-assisted project configuration."""

    @classmethod
    def generate(cls, heuristics: ProjectHeuristics | None = None) -> str:
        """Format an exhaustive, self-contained Markdown prompt for ticket-runner.yaml authoring."""
        detected_context = ""
        if heuristics is not None:
            detected_context = f"""
## Pre-Detected Project Context
The following baseline heuristics were pre-detected in this repository:
- **Detected Stack**: `{heuristics.detected_stack}`
- **Project Name**: `{heuristics.name}`
- **Proposed Base Branch**: `{heuristics.base_branch}`
- **Proposed Agent Branch**: `{heuristics.branch}`
- **Proposed Test Command**: `{heuristics.test_cmd}`
- **Proposed Build Command**: `{heuristics.build_cmd}`
- **Worker Provider**: `{heuristics.provider}`
"""

        return f"""# Ticket Runner Configuration Prompt

## Context & Architecture
Ticket Runner is an external multi-agent orchestrator that drives AI coding agents (OpenCode, Antigravity CLI) through a sequential directory queue of tickets under `docs/tickets/`.
Ticket Runner operates on a decoupled two-tier configuration model:
1. **Global Configuration** (`~/.ticket-runner/config.yaml`): Stores machine-level credentials (Discord bot tokens, default models, presence timeouts, token thresholds).
2. **Project Overlay Configuration** (`<project-dir>/ticket-runner.yaml`): A minimal, project-specific configuration (<15 lines) defining only the local project settings (name, git branches, verification commands, and worker provider).

## Objective
Inspect this project repository and author a minimal, highly accurate `ticket-runner.yaml` in the project root.
{detected_context}
## Configuration Schema (`ticket-runner.yaml`)
The project configuration must follow this minimal schema (under 15 lines):

```yaml
project:
  name: "{heuristics.name if heuristics else '<project-name>'}"
  base_branch: "{heuristics.base_branch if heuristics else 'main'}"
  branch: "{heuristics.branch if heuristics else 'agent/ticket-runner'}"

verification:
  test_cmd: "{heuristics.test_cmd if heuristics and heuristics.test_cmd else '<test-command>'}"
  build_cmd: "{heuristics.build_cmd if heuristics else ''}"

worker:
  provider: "{heuristics.provider if heuristics else 'opencode'}"
```

### Field Definitions:
- `project.name`: Name of the project or repository.
- `project.base_branch`: The upstream integration branch (`main` or `master`).
- `project.branch`: The dedicated agent working branch (default: `agent/ticket-runner`).
- `verification.test_cmd`: Independent verification test suite command executed by the Gatekeeper to validate changes (e.g. `python -m pytest`, `npm test`, `cargo test`, `go test ./...`).
- `verification.build_cmd`: Optional build/typecheck command executed prior to testing (e.g. `npm run build`, `cargo build`, or empty `""`).
- `worker.provider`: Worker agent provider, either `opencode` or `antigravity`.

## Guidelines for Inspecting the Repository
To select the fastest, most reliable verification commands, inspect:
1. **Manifests & Package Files**:
   - Python: Inspect `pyproject.toml`, `setup.py`, `pytest.ini`, or `requirements.txt`. Prefer `python -m pytest` or project-specific test runners.
   - Node.js: Inspect `package.json` and lockfiles (`pnpm-lock.yaml` -> `pnpm test`, `yarn.lock` -> `yarn test`, `bun.lockb` -> `bun test`, `package-lock.json` -> `npm test`). Check `scripts.test` and `scripts.build`.
   - Rust: Inspect `Cargo.toml`. Propose `cargo test` and `cargo build`.
   - Go: Inspect `go.mod`. Propose `go test ./...`.
2. **CI / CD & Workflows**: Check `.github/workflows/`, GitLab CI, or Makefile for the exact test commands used in continuous integration.
3. **Speed & Determinism**: Pick commands that are fast, deterministic, and exit with code 0 on success.

## Stack Examples

### Python (pytest)
```yaml
project:
  name: "python-app"
  base_branch: "main"
  branch: "agent/ticket-runner"

verification:
  test_cmd: "python -m pytest"
  build_cmd: ""

worker:
  provider: "opencode"
```

### Node.js (pnpm / npm / yarn / bun)
```yaml
project:
  name: "node-app"
  base_branch: "main"
  branch: "agent/ticket-runner"

verification:
  test_cmd: "pnpm test"
  build_cmd: "pnpm run build"

worker:
  provider: "opencode"
```

### Rust (cargo)
```yaml
project:
  name: "rust-app"
  base_branch: "main"
  branch: "agent/ticket-runner"

verification:
  test_cmd: "cargo test"
  build_cmd: "cargo build"

worker:
  provider: "opencode"
```

### Go
```yaml
project:
  name: "go-app"
  base_branch: "main"
  branch: "agent/ticket-runner"

verification:
  test_cmd: "go test ./..."
  build_cmd: ""

worker:
  provider: "opencode"
```

## Output Format
Return ONLY the clean fenced YAML configuration block for `ticket-runner.yaml` ready to be written to disk.
"""
