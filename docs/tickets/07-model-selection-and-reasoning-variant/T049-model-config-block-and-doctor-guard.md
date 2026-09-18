# T049 — `model:` config block and Doctor model guard
Status: pending
Spec: docs/specs/07-model-selection-and-reasoning-variant.md
Blocked by: None
Reasoning: medium

### Requirements
- Add the `model:` configuration surface: a labelled list of selectable LLMs plus a session-wide default reasoning level.
- Domain: `ModelEntry` (`id`, `label`) and `ModelConfig` (`models: tuple[ModelEntry, ...] = ()`, `default_reasoning: str = ""`) in `runner/domain/config.py`, following existing frozen-dataclass invariant style. Reject blank `id`/`label`, duplicate ids, and non-string `default_reasoning` (missing/null treated as `""`).
- Composition: append `model: ModelConfig = field(default_factory=ModelConfig)` to `RunnerConfig` last, so all existing construction sites compile unchanged; the empty default is what keeps the loader tolerant.
- Loader: `runner/adapters/config/yaml_config_loader.py` parses an optional `model:` section — absent or null yields `ModelConfig()`, non-mapping raises `ConfigError`, entries must be mappings carrying non-empty `id`/`label`. Do **not** add `model` to `REQUIRED_SECTIONS`.
- Doctor: add `CHECK_MODEL = "model"` and `check_model()`, registered after `check_config`; absent/empty `model.models` fails pre-flight with a message naming `model.models` and a remediation showing the YAML block to add. Skip gracefully (pass) when no config was loaded, mirroring `check_verification_commands`.
- `config.example.yaml` gains the block from the spec (`deepseek/deepseek-chat` "DeepSeek Chat", `qwen/qwen-plus` "Qwen Plus", `default_reasoning: ""`).
- Jump-start:
  - Files to touch: `runner/domain/config.py`, `runner/adapters/config/yaml_config_loader.py`, `runner/application/doctor.py`, `config.example.yaml`, `tests/unit/domain/test_config.py`, `tests/unit/adapters/test_yaml_config_loader.py`, `tests/unit/application/test_doctor.py`.
  - Anchors: `VerificationConfig`/`DiscordConfig` invariant style; `check_verification_commands` for the lazy-config guard pattern; `run()`'s ordered `check_runners` list.
  - Verification: `python -m pytest tests/unit/domain/test_config.py tests/unit/adapters/test_yaml_config_loader.py tests/unit/application/test_doctor.py`.

### Acceptance Criteria
- A config without a `model:` section loads successfully with `config.model.models == ()` — critically, `test_load_root_config_yaml` (which loads the untracked live `config.yaml`) stays green.
- `config.example.yaml` loads with two ordered labelled models and `default_reasoning == ""`.
- Blank/absent `id` or `label`, duplicate ids, non-mapping entries, and non-string `default_reasoning` raise `ConfigError`.
- Doctor with empty/absent models reports a failed check named `model` whose remediation shows how to add the block; with a populated list it passes.
- Existing `RunnerConfig(...)` construction in tests and `runner/container.py` needs no new argument.
- Full suite green: `python -m pytest`.

### Gotchas
- The tolerant loader is deliberate: Doctor owns the non-empty guard, so the suite never goes red merely because the untracked local `config.yaml` has no `model:` block — the root-config smoke test loads that live file.
- Consequence: after this ticket lands, a fresh `ticket_runner.py start` on this repo fails pre-flight until the human adds a real `model:` block to the untracked `config.yaml`. That is the intended US 9 behavior and a documented operational step, not a regression.
- YAML `default_reasoning:` with no value parses as `None` and must be treated as `""`.
- `RunnerConfig` is frozen; adding the field anywhere but the final position would reorder required arguments. Use `field(default_factory=ModelConfig)` last.
