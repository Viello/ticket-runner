# T101 — Two-Tier Configuration Overlay Loader
Status: completed
Completed: 2026-09-23T14:43:00Z
Spec: docs/specs/12-project-scaffolding-and-skills-distribution.md
Blocked by: None
Security: required
Reasoning: medium

### Requirements
- Extend `YamlConfigLoader` in `runner/adapters/config/yaml_config_loader.py` and the `ConfigLoader` port in `runner/ports/config_loader.py` to support two-tier configuration loading:
  - Global user configuration path: `Path.home() / ".ticket-runner" / "config.yaml"`.
  - Project overlay configuration path: `<project_dir> / "ticket-runner.yaml"` (with fallback to `<project_dir> / "config.yaml"` for backward compatibility).
  - Add method `load_two_tier(project_dir: Path | str, global_path: Path | str | None = None, project_config_path: Path | str | None = None) -> RunnerConfig`.
- Implement deep-merge semantics:
  - If the global configuration file exists, load its dictionary; if missing, use built-in safe default machine configuration (e.g. Discord disabled, standard token budget `warn=120000, handoff=135000, ceiling=150000`, presence `nearby`, lifecycle `standby`, git `auto_push=False`).
  - If the project overlay configuration file exists, load its dictionary and deep-merge over the global dictionary.
  - Project values strictly take precedence over global values.
  - Validate the merged dictionary through `load_from_dict(merged_dict)` to construct the immutable `RunnerConfig` domain object.
- Support minimal project overlays (<15 lines): projects should only need to specify project-specific overrides (e.g., `project.name`, `project.base_branch`, `verification.test_cmd`, `verification.build_cmd`, `worker.provider`) without re-declaring tokens, presence, lifecycle, or discord settings.
- Unit tests in `tests/unit/adapters/test_two_tier_config.py` verifying deep-merging, precedence, missing global file fallback, missing project file handling, and backward-compatible `config.yaml` fallback.
- Jump-start:
  - Files to touch: `runner/adapters/config/yaml_config_loader.py`, `runner/ports/config_loader.py`, `tests/unit/adapters/test_two_tier_config.py`.
  - Seams: `ConfigLoader(Protocol)`, `YamlConfigLoader.load_two_tier()`.
  - Verification: `pytest tests/unit/adapters/test_two_tier_config.py`.

### Acceptance Criteria
- `YamlConfigLoader.load_two_tier()` successfully resolves global configuration from `~/.ticket-runner/config.yaml` and project overlay from `<project-dir>/ticket-runner.yaml`.
- If `<project-dir>/ticket-runner.yaml` is absent, falls back gracefully to `<project-dir>/config.yaml`.
- Project configuration overrides take precedence over global configuration on a per-field basis (deep-merge, not shallow key replacement).
- If global configuration does not exist, safe defaults are supplied so the runner can run on minimal project overlays without throwing missing section errors.
- Minimal project overlay (<15 lines) with only `project` and `verification` sections validates into a complete, valid `RunnerConfig`.
- Security verification: Safe path resolution prevents path traversal attacks when resolving `project_dir` or `global_path`.

### Smoke Scenarios
**Scenario: Two-Tier Configuration Overlay Merging**
- Setup: None (runs from repository root).
- Why: Test that Ticket Runner can read machine-wide defaults and combine them with project-specific settings so you don't have to re-type Discord tokens, token budgets, or model settings in every new repo.
- Steps:
  1. Run this self-contained Python command to create an isolated test directory, write a minimal project overlay (`ticket-runner.yaml`), and load it via `load_two_tier()`:
     ```powershell
     python -c "import tempfile, pathlib; from runner.adapters.config.yaml_config_loader import YamlConfigLoader; td = pathlib.Path(tempfile.mkdtemp()); (td / 'ticket-runner.yaml').write_text('project:\n  name: demo\n  branch: agent/ticket-runner\n  base_branch: main\nverification:\n  test_cmd: pytest -v\n', encoding='utf-8'); cfg = YamlConfigLoader().load_two_tier(project_dir=td); assert cfg.project.name == 'demo'; assert cfg.verification.test_cmd == 'pytest -v'; assert cfg.tokens.ceiling == 150000; print('PASS: Two-tier config successfully loaded and merged')"
     ```
- Expected:
  - Command executes cleanly with exit code 0.
  - Console prints: `PASS: Two-tier config successfully loaded and merged`.

### Gotchas
- When performing a deep merge, dictionaries should be recursively merged, while lists or scalar values in the project overlay should replace the global counterpart rather than appending or colliding.
