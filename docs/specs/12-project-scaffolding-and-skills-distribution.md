# Spec 12: Project Scaffolding, LLM-Friendly Config & Skills Distribution

## Problem Statement

When a developer wants to use Ticket Runner on a new or existing repository, the onboarding process is entirely manual:
1. They must manually craft a complex `config.yaml` file with dozens of fields, many of which are machine-level settings (Discord bot tokens, token limits, model IDs) rather than project-specific settings.
2. They must manually create directory trees for `docs/specs/`, `docs/tickets/`, and `.agent/`.
3. They must manually copy vendored skills (`implement`, `code-review`, `to-tickets`, etc.) from an existing project, leading to fragmented, out-of-date local copies.
4. Developers working with AI coding assistants have no standardized prompt to hand to their AI to automatically inspect the target repository and generate the optimal project configuration.

## Solution

1. **Two-Tier Configuration Overlay**:
   - Split configuration into **Global User Configuration** (`~/.ticket-runner/config.yaml`) containing machine-wide preferences (Discord credentials, model lists, presence timeouts, token thresholds) and **Project Overlay Configuration** (`<project-dir>/ticket-runner.yaml`) containing only project-specific overrides (`test_cmd`, `build_cmd`, `base_branch`, `agent_branch`, `worker.provider`).
   - The runner automatically merges Project Overlay Config over global defaults upon loading.
2. **Interactive & Heuristic Scaffolding (`ticket-runner init`)**:
   - Provide a `ticket-runner init [--project-dir <path>]` command that inspects project files (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`), detects test and build commands, detects the git base branch, and prompts the user with smart defaults to generate a clean `ticket-runner.yaml`.
   - Automatically scaffolds required directories: `docs/specs/`, `docs/tickets/`, and `.agent/`.
3. **LLM-Friendly Configuration Prompt Generator**:
   - Add a `ticket-runner init --ai-prompt` flag that prints a self-contained, structured Markdown prompt containing a strict JSON/YAML schema, stack-specific examples, and clear instructions. A developer can copy-paste this prompt into any AI agent (or run it inline) to have the AI inspect the repository and author `ticket-runner.yaml` autonomously.
4. **Skills Repository & Distribution (`ticket-runner skills sync`)**:
   - Initialize and publish the canonical `Viello/agent-skills` remote repository on GitHub containing core reusable skills (`implement`, `code-review`, `security-review`, `to-tickets`, `handoff`, `diagnosing-bugs`, etc.).
   - Provide a `ticket-runner skills sync [--project-dir <path>]` command that downloads or updates the canonical skills catalog from the remote repository (`Viello/agent-skills`) into `<project-dir>/.agents/skills/`.
   - `ticket-runner init` automatically triggers skills synchronization as part of project setup.

## User Stories

1. As a developer, I want my global settings (Discord token, default models, token budget ceilings) stored once in `~/.ticket-runner/config.yaml`, so that I do not have to re-enter them in every repository.
2. As a developer, I want each target repository to need only a minimal `ticket-runner.yaml` (under 15 lines), so that configuration overhead is minimal and project-focused.
3. As a developer, I want Project Overlay Config in `ticket-runner.yaml` to take precedence over global settings in `~/.ticket-runner/config.yaml`, so that individual projects can customize their test commands or branch names.
4. As a developer, I want to run `ticket-runner init` inside an existing repository, so that the required directory structure (`docs/specs/`, `docs/tickets/`, `.agent/`) is created automatically.
5. As a developer initializing a Python project with `pyproject.toml`, I want `ticket-runner init` to auto-detect `python -m pytest` as the default test command, so that I can accept it with a single keystroke.
6. As a developer initializing a Node.js project with `package.json`, I want `ticket-runner init` to detect whether `npm`, `pnpm`, `yarn`, or `bun` is used and propose the appropriate test and build scripts.
7. As a developer initializing a Rust project with `Cargo.toml`, I want `ticket-runner init` to propose `cargo test` and `cargo build`.
8. As a developer initializing a Go project with `go.mod`, I want `ticket-runner init` to propose `go test ./...`.
9. As a developer, I want `ticket-runner init` to detect the current git default branch (`main` or `master`) and suggest it as `base_branch`, while defaulting `branch` to `agent/ticket-runner`.
10. As a developer working with an AI coding assistant, I want to run `ticket-runner init --ai-prompt`, so that I receive an exhaustive, self-contained prompt to hand to my AI to configure the project for me.
11. As an AI coding assistant receiving the prompt, I want the prompt to include clear schema rules and stack examples, so that I produce a valid `ticket-runner.yaml` without syntax errors.
12. As an ecosystem maintainer, I want the canonical reusable skills repository `Viello/agent-skills` published on GitHub, so that all runner installations have an authoritative, accessible remote catalog.
13. As a developer, I want to run `ticket-runner skills sync`, so that the latest verified skills from `Viello/agent-skills` are cloned or updated into my project's `.agents/skills/` directory.
14. As a developer, I want `ticket-runner init` to offer to sync skills automatically, so that a newly initialized project is immediately ready for agent execution.
15. As an operator, I want the final ticket of this spec queue to audit implementation against Spec 12 and update living documents if any architectural details shifted during development.

## Implementation Decisions

1. **Two-Tier Configuration Merging (`runner/adapters/config/yaml_config_loader.py`)**:
   - Define global path: `Path.home() / ".ticket-runner" / "config.yaml"`.
   - Define project path: `project_dir / "ticket-runner.yaml"` (with fallback to `project_dir / "config.yaml"` for backward compatibility).
   - Merging logic: Load global dict if present; load project dict if present; deep-merge project dict over global dict; parse into frozen domain `RunnerConfig`.

2. **Project Heuristics Sniffer (`runner/application/scaffolding.py`)**:
   - Create a pure application service `ProjectSniffer` that inspects `project_dir`:
     - Python: Checks `pyproject.toml`, `setup.py`, `requirements.txt` $\rightarrow$ `test_cmd = "python -m pytest"`.
     - Node: Parses `package.json` $\rightarrow$ checks lockfiles (`pnpm-lock.yaml`, `yarn.lock`, `package-lock.json`, `bun.lockb`) $\rightarrow$ inspects `scripts.test` and `scripts.build`.
     - Rust: Checks `Cargo.toml` $\rightarrow$ `test_cmd = "cargo test"`, `build_cmd = "cargo build"`.
     - Go: Checks `go.mod` $\rightarrow$ `test_cmd = "go test ./..."`.
     - Git: Inspects `git rev-parse --abbrev-ref origin/HEAD` or local branches to find `main` vs `master`.

3. **Interactive Scaffolder CLI (`runner/adapters/cli/scaffolder.py`)**:
   - Uses `rich.prompt.Prompt` and `rich.prompt.Confirm` to present detected defaults and allow inline editing.
   - Generates and writes `<project_dir>/ticket-runner.yaml`.
   - Creates directory structure with `.gitkeep` files where appropriate.
   - Ensures `.agent/` is added to the project's `.gitignore` if not already ignored.

4. **AI Prompt Generator (`runner/application/prompt_generator.py`)**:
   - `ticket-runner init --ai-prompt` formats a rich Markdown prompt:
     - Context: Explaining Ticket Runner's expectations.
     - Schema: Exact YAML specification for `ticket-runner.yaml`.
     - Guidelines: How the AI should inspect `package.json`, `pyproject.toml`, Makefile, or CI workflows to determine the fastest, most reliable test and build commands.
     - Output format: Clean fenced YAML block ready for writing to disk.

5. **Skills Catalog Publication & Client (`runner/adapters/skills/skills_client.py`)**:
   - Initialize and publish `Viello/agent-skills` on GitHub containing canonical skills and README index.
   - Implements a download/sync protocol pulling from GitHub raw or tarball archive (`https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz` or git clone via `CommandRunner`).
   - Copies files into `<project_dir>/.agents/skills/` while preserving custom project-specific skills that don't collide with catalog names.

## Testing Decisions

- **Unit Tests**:
  - `tests/unit/adapters/test_two_tier_config.py`: Test merging of global defaults with project overrides, ensuring project fields take precedence.
  - `tests/unit/application/test_project_sniffer.py`: Test detection on mock project directories (mock `package.json`, mock `pyproject.toml`, mock `Cargo.toml`, etc.).
  - `tests/unit/application/test_prompt_generator.py`: Verify that `--ai-prompt` outputs complete schema and valid instructions.
  - `tests/unit/adapters/test_skills_client.py`: Test skills downloading, extraction, path safety (Zip Slip prevention), and custom skill preservation.
- **Integration Tests**:
  - `tests/specs/test_spec_12_scaffolding.py`: Execute `ticket-runner init` on an empty temporary directory with simulated inputs; verify generated `ticket-runner.yaml`, created directories, and `.gitignore` update.

## Out of Scope

- Generating project-specific `verify-<app>` feature maps (deferred to Spec 13).

## Further Notes

- If a developer runs `ticket-runner init` in non-interactive environments (e.g. CI or automated scripts), a `--yes` / `--non-interactive` flag will accept all detected defaults automatically.
