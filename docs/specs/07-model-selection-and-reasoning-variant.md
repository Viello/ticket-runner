# Spec 07: Model Selection and Reasoning Variant

## Problem Statement

The Runner currently has no notion of which LLM to use — model identity is either baked into OpenCode's own defaults or set out-of-band by the user. When switching between providers (e.g. DeepSeek for fast iteration, Qwen for heavier tasks) the user must manually adjust OpenCode configuration rather than telling the Runner which model to use for a given run. Additionally, tickets that require deep, multi-step reasoning waste budget on lightweight tasks and vice versa, with no mechanism to tune the model's thinking depth per ticket. The result is either overpaying for simple tickets or under-thinking complex ones, with no Runner-enforced record of the choice.

## Solution

Introduce a `model:` configuration block in `config.yaml` that holds a labelled list of available LLMs and a default reasoning level. At startup the Runner presents the list and lets the developer pick (or accepts a `--model` flag for scripted use). The chosen model is session-scoped: fixed for the entire Runner run and stored in `.agent/state.json` for crash recovery. Individual tickets may override only the reasoning depth via an optional `Reasoning:` frontmatter field; the Runner passes that value as `--variant` to every `opencode run` call under that ticket. If a ticket omits the field the configured default applies; if the default is also unset, `--variant` is omitted entirely, deferring to OpenCode's own default.

## User Stories

1. As a developer, I want to configure a named list of LLMs in `config.yaml` so the Runner knows which models are available for my project.
2. As a developer, I want each configured model to have a human-readable label so the startup prompt is readable without deciphering provider/model strings.
3. As a developer, I want the Runner to show a numbered model-selection menu at startup when multiple models are configured, so I can pick the right model for this session.
4. As a developer, I want the Runner to auto-select the model silently when exactly one model is configured, skipping the prompt entirely.
5. As a developer, I want to pass `--model <id>` at launch to skip the interactive prompt and select a model programmatically for scripted or CI use.
6. As a developer, I want the Runner to reject a `--model` value that is not in the configured list, so I get an early error instead of a silent wrong-model run.
7. As a developer, I want the selected model stored in `.agent/state.json` so crash recovery restores the same model without re-prompting.
8. As a developer, I want crash recovery to show a brief notice of the restored model and let me override it with `--model` if needed.
9. As a developer, I want the Doctor to fail pre-flight if `model.models` is empty or missing, preventing a model-less run from starting silently.
10. As a developer, I want the selected model passed as `-m provider/model` to every `opencode run` call, so model identity is consistently enforced across all Session Runs.
11. As a developer, I want to declare `Reasoning: high` in a ticket's frontmatter to run that ticket's Worker with elevated thinking depth without switching models.
12. As a developer, I want to omit `Reasoning:` from most tickets and rely on a project-wide `model.default_reasoning` in `config.yaml`, so I only override where it matters.
13. As a developer, I want `model.default_reasoning` to be optional and default to empty, so omitting it causes `--variant` to be skipped entirely and OpenCode uses its own default.
14. As a developer, I want the `Reasoning:` field applied to every `opencode run` under the ticket — initial Session Run, handoff resumes, and answer-resume runs — so reasoning depth is consistent across the full ticket lifecycle.
15. As a developer, I want the Runner to pass the `Reasoning:` value through to OpenCode's `--variant` flag without validating the string, so I am not blocked by Runner-side allowlist drift when providers update their variant vocabulary.
16. As a developer, I want newly generated tickets (via `/to-tickets`) to include an optional `Reasoning:` field with an inline comment showing example values, so I can set reasoning depth without consulting external docs.
17. As a developer, I want `Reasoning:` parsed case-insensitively from the ticket frontmatter, consistent with how `Status:` and `Security:` are already parsed.

## Implementation Decisions

### Config Schema: `model:` Block

`config.yaml` gains a new top-level `model:` section:

```yaml
model:
  default_reasoning: ""      # passed as --variant; flag is omitted when empty
  models:
    - id: "deepseek/deepseek-chat"
      label: "DeepSeek Chat"
    - id: "qwen/qwen-plus"
      label: "Qwen Plus"
```

The `models` list is required and must be non-empty (enforced by the Doctor). Each entry carries an `id` (the `provider/model` string passed to OpenCode's `-m` flag) and a `label` (shown in the startup prompt). `default_reasoning` is optional and defaults to an empty string.

### CLI Flag: `--model`

`ticket_runner.py start` gains an optional `--model <id>` flag. Resolution order at startup:

1. `--model <id>` passed → validate against `model.models` list; error if not found.
2. `--model` omitted + exactly one model configured → auto-select silently.
3. `--model` omitted + multiple models configured → display interactive numbered prompt.

### State Persistence

`.agent/state.json` gains a `selected_model` string field storing the `id` of the model chosen at startup. On crash recovery the Runner reads this field, displays a notice (*"Resuming with \<label\> — pass `--model` to override"*), and skips the selection prompt unless `--model` is explicitly passed.

### Doctor Pre-Flight Check

The Doctor's startup check gains a `model.models` non-empty guard. If the list is absent or empty, the Doctor emits a descriptive error and halts before any queue execution begins.

### Command Construction: Model and Variant Injection

`build_opencode_run_command` (the existing function in the OpenCode worker adapter) gains two optional parameters: `model_id` (the session-scoped provider/model string) and `variant` (the per-ticket reasoning level). When `model_id` is provided, `-m <model_id>` is appended. When `variant` is a non-empty string, `--variant <variant>` is appended. Both flags are omitted when their values are absent or empty. The Worker Supervisor passes these from the active ticket's resolved model context on every Session Run it spawns.

### Ticket Frontmatter: `Reasoning:` Field

The Runner's ticket parser gains case-insensitive extraction of the `Reasoning:` frontmatter field. Resolution order for variant value:

1. Ticket `Reasoning:` field (non-empty) → use as `--variant`
2. `model.default_reasoning` in config (non-empty) → use as `--variant`
3. Neither set → omit `--variant`

### Startup Prompt UX

When the interactive selection prompt is shown, it renders inside the existing terminal UI flow (before the Rich dashboard starts). Format:

```
Select model for this session:
  [1] DeepSeek Chat    (deepseek/deepseek-chat)
  [2] Qwen Plus        (qwen/qwen-plus)
> _
```

A single keypress selects; Enter confirms. Invalid input loops the prompt.

### Session-Scoped vs. Per-Ticket Scope

Model identity (`-m`) is session-scoped: fixed when the Runner starts and applied uniformly across all tickets in that run. Reasoning variant (`--variant`) is per-ticket: resolved fresh for each ticket from ticket frontmatter and config default. This separation keeps model choice an operator concern and reasoning depth a ticket concern.

## Testing Decisions

Good tests assert externally observable behaviour — the command list returned by `build_opencode_run_command`, the error raised when an unknown model is passed, the variant resolved from ticket frontmatter — not internal parsing mechanics.

Modules to test:

- **`build_opencode_run_command`** — the existing unit tests in `test_opencode_worker.py` are the anchor pattern. Add parametrised cases: model only, variant only, both, neither; verify the exact token list in each case.
- **Config loader / Doctor model check** — unit-test the non-empty guard: missing `model.models` key, empty list, and valid list each produce the expected outcome.
- **Startup model resolution** — unit-test all three selection paths (flag passed and valid, flag passed and invalid, omitted with one model, omitted with multiple models) at the CLI-argument-parsing layer, using the existing Doctor/config fixture pattern.
- **Ticket frontmatter `Reasoning:` extraction** — unit-test the resolver: ticket sets value, ticket omits (config default used), both omit (flag absent from command), case-insensitive parse.
- **State persistence** — unit-test that `selected_model` is written to and read from `.agent/state.json` correctly, using the existing state file fixture pattern.

Prior art: `tests/unit/adapters/opencode/test_opencode_worker.py` for command-building tests; `tests/unit/application/test_doctor.py` for Doctor pre-flight check patterns; `tests/unit/application/test_worker_supervisor.py` for Session Run construction patterns.

## Out of Scope

- Per-phase reasoning (different variant for initial vs. handoff Session Runs within one ticket).
- Full model switching per ticket (only reasoning variant varies per ticket; model is session-scoped).
- Runner-side validation of variant strings against a provider allowlist.
- Automatic reasoning-level inference from ticket complexity signals.
- Temperature, top-p, or other sampling parameter controls.
- Multi-model parallelism (running two models simultaneously on the same ticket for comparison).

## Further Notes

Variant strings are provider-specific. Anthropic uses `low`, `medium`, `high`, `max`; DeepSeek and Qwen may differ. Because the Runner passes the value through blindly, a misconfigured `Reasoning:` value surfaces as an OpenCode CLI error on the first Session Run of the ticket — loud and early. The inline comment in the ticket template (`# optional: low | medium | high | max (provider-specific; omit to use config default)`) is intentionally illustrative, not exhaustive. ADR 0022 records the full rationale for these choices.
