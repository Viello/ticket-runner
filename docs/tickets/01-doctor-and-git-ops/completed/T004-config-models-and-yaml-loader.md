# T004 — Configuration domain models and YAML schema loader
Status: completed
Completed: 2026-09-15T15:24:00Z
Spec: docs/specs/01-doctor-and-git-ops.md

### Requirements
- Define immutable domain configuration dataclasses in `runner/domain/config.py`:
  - `ProjectConfig`, `WorkerConfig`, `VerificationConfig`, `TokenBudgetConfig`, `PresenceConfig`, `DiscordConfig`, `LifecycleConfig`, `GitConfig`, and composite `RunnerConfig`.
- Define `ConfigLoader` abstract protocol in `runner/ports/config_loader.py`.
- Implement `YamlConfigLoader` adapter in `runner/adapters/config/yaml_config_loader.py` using PyYAML.
- Validate configuration against schema rules:
  - Required sections present.
  - Token threshold invariants: `warn < handoff < ceiling`.
  - Verification commands are strings; timeout is a positive integer.
  - Presence mode is either `nearby` or `away`.
  - Lifecycle `clean_slate` is either `interactive`, `always`, or `never` (defaults to `interactive`).
  - Discord configuration stores environment variable name in `token_env`, never raw credentials.
- Raise informative `ConfigError` with exact field error details upon schema violation.
- Provide default `config.yaml` in repository root adhering to Spec 01 §16 and plan §17.
- Jump-start:
  - Files to touch: `runner/domain/config.py`, `runner/ports/config_loader.py`, `runner/adapters/config/__init__.py`, `runner/adapters/config/yaml_config_loader.py`, `config.yaml`, `tests/unit/adapters/test_yaml_config_loader.py`.
  - Seams: `runner/ports/config_loader.py:ConfigLoader`.
  - Anchor patterns: Spec 01 §16 and plan §17 `config.yaml` schema.
  - Verification: `pytest tests/unit/adapters/test_yaml_config_loader.py`.

### Acceptance Criteria
- Valid YAML config parses into a strongly-typed `RunnerConfig` domain object.
- Missing required sections or fields raise descriptive `ConfigError`.
- Violations of token budget invariants (`warn >= handoff` or `handoff >= ceiling`) raise descriptive `ConfigError`.
- Default `config.yaml` in repository root satisfies all validation constraints.
- Unit tests verify all error conditions and default configuration parsing.

### Gotchas
- `config.yaml` must never contain raw API secrets or bot tokens; it only specifies the environment variable name (`token_env: "DISCORD_BOT_TOKEN"`).
