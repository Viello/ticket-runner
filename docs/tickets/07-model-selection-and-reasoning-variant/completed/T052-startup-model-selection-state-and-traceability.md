# T052 — Interactive model selection, state persistence, and restore notice
Status: completed
Completed: 2026-09-18T12:46:00Z
Spec: docs/specs/07-model-selection-and-reasoning-variant.md
Blocked by: T048, T051
Security: required
Reasoning: high

### Requirements
- Implement the full startup resolution order, persist the choice to `.agent/state.json`, and close Spec 07 with a traceability suite.
- New application interactor (e.g. `runner/application/model_selection.py`) resolving in this order:
  1. explicit `--model` (already validated in T051) → use it and persist.
  2. else read `.agent/state.json`; if `selected_model` is present and still configured → restore it and print verbatim `Resuming with <label> — pass --model to override`.
  3. recorded id no longer configured → warn that the recorded model is unavailable, then fall through.
  4. zero configured models → resolve silently to `None` (Doctor owns the US 9 guard; this path is never reached in production).
  5. exactly one configured model → auto-select silently.
  6. multiple models → interactive prompt.
  7. prompt needed but stdin is non-interactive → `NonInteractiveError` whose message tells the operator to pass `--model`.
- Prompt adapter (e.g. `runner/adapters/ui/model_prompt.py`) rendering a plain-text menu before any dashboard starts:
  ```
  Select model for this session:
    [1] DeepSeek Chat    (deepseek/deepseek-chat)
    [2] Qwen Plus        (qwen/qwen-plus)
  > _
  ```
  Raw single-key reading through an injectable `read_key` seam (`msvcrt` default on Windows): digit selects, Enter confirms, invalid input loops without confirming. Follow `TerminalInterventionGateway`'s injected-`input_fn`/`output_fn` pattern (defaults resolved at instantiation time, never bound at class definition).
- Persistence: after resolution, read the state document (absent or corrupt → warn and treat as `{}`), merge in `selected_model`, and write the exact document (all unrelated keys preserved) through `StateStore` before the container is built. A write failure prints an actionable error and returns exit 1.
- CLI wiring: `run_start` gains optional injection seams (`state_store`, `model_prompt`/`key_reader`) so tests never touch the real `.agent/state.json` or raw stdin. Resolve selection only on the locally built container path.
- Traceability suite `tests/specs/test_spec_07_model_selection.py` mapping user stories 1–17 to end-to-end tests with fakes: flag-invalid exit 1, single-model auto-select, keypress selection, restore notice, drift fallback, corrupt-state warning, write-failure exit, all four command token cases, and cross-run variant consistency (initial, handoff resume, answer-resume). Include a check that `.agents/skills/to-tickets/SKILL.md` still carries the `Reasoning:` template line (US 16 is otherwise pre-satisfied).
- Jump-start:
  - Files to touch: `runner/application/model_selection.py` (new), `runner/adapters/ui/model_prompt.py` (new), `ticket_runner.py`, `tests/unit/application/test_model_selection.py` (new), `tests/unit/adapters/test_model_prompt.py` (new), `tests/unit/test_cli.py`, `tests/specs/test_spec_07_model_selection.py` (new).
  - Seams: `FakeDoctorPassing` supplies `loaded_config`; `RuntimePaths.state_path` and `JsonStateStore` from T048; `FakeStateStore` for tests.
  - Anchors: `TerminalInterventionGateway` injected I/O; `_configure_console_encoding` for Windows console behavior.
  - Verification: `python -m pytest tests/unit/application/test_model_selection.py tests/unit/adapters/test_model_prompt.py tests/specs/test_spec_07_model_selection.py`.

### Acceptance Criteria
- Flag path selects without reading state or prompting; the written state document afterwards still contains every pre-existing key.
- Restore path (`{"selected_model": "qwen/qwen-plus", ...}` with that id configured) prints the verbatim notice, skips the prompt, and resolves that id.
- Drift path (recorded id absent from the configured list) warns and falls through to auto-select or prompt.
- Single-model config auto-selects silently; a multiple-model config renders the menu, a fake key sequence `["2", "\r"]` selects the second entry, and invalid keys loop until valid.
- Non-interactive stdin with multiple models and no flag exits 1 with a message mentioning `--model`; zero configured models resolves silently to `None`.
- A corrupt state document warns and is treated as absent; a failing state write exits 1 before orchestration starts.
- The traceability suite maps US 1–17 and passes, and the full suite is green: `python -m pytest`.

### Gotchas
- Tests must inject the fake state store and fake key reader — `run_start` in a test process must never read/write the real `.agent/state.json` nor block on stdin (see gotchas: Redirected Stdin Fails with EOFError; Builtin Input Defaults Bind at Class Definition Time).
- `msvcrt` exists only on Windows; guard the default key reader and raise `NonInteractiveError` when raw console input is unavailable.
- The restore notice wording is a contract: `Resuming with <label> — pass --model to override`.
- State contents are untrusted: re-validate the recorded id against `model.models` before it can flow to the supervisor or argv.
- Existing CLI tests use a dummy config with zero models and monkeypatched `build_container`; silent `None` resolution for the zero-model case is what keeps them green.
- Injected containers/orchestrators already encode their collaborators — skip selection resolution for those paths.
