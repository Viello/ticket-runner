# T055 — Doctor terminal host detection, interactive prompt, and configuration persistence
Status: completed
Completed: 2026-09-19T10:28:00Z
Spec: docs/specs/06-state-persistence-and-terminal-ui.md
Blocked by: None
Reasoning: medium

### Requirements
- Add `UIConfig` dataclass to `runner/domain/config.py`:
  - `session_terminal: str = ""`
  - Add `ui: UIConfig = field(default_factory=UIConfig)` to `RunnerConfig`.
  - Validate that `session_terminal` is a string.
- Add terminal host pre-flight check (`CHECK_TERMINAL_HOST = "session_terminal"`) to `Doctor` in `runner/application/doctor.py`:
  - If `ui.session_terminal` is already set in `config.yaml`:
    - Verify that the configured executable is discoverable via `shutil.which(host)`.
    - If found, check passes; if missing, return a failing `CheckResult` with clear remediation.
  - If `ui.session_terminal` is unset or empty:
    - Probe system for available terminal hosts in priority order: `wt.exe` → `pwsh.exe` → `powershell.exe` → `cmd.exe`.
    - If no terminal hosts are detected, check fails with remediation indicating no supported terminal host found.
    - If exactly one terminal host is detected, auto-select it.
    - If multiple terminal hosts are detected:
      - In interactive mode (TTY available), prompt the user with a numbered menu to choose their preferred terminal host.
      - In non-interactive mode (e.g. CI or non-interactive pipe), auto-select the highest-priority detected host.
    - Persist the selected terminal host into `config.yaml` under `ui.session_terminal`.
- Jump-start:
  - Files to touch: `runner/domain/config.py`, `runner/application/doctor.py`, `runner/adapters/ui/terminal_prompts.py`, `runner/adapters/config/yaml_config_loader.py`, `tests/unit/application/test_doctor.py`, `tests/specs/test_spec_01_doctor.py`.
  - Seams: `shutil.which`, `runner/ports/config_loader.py`.
  - Anchor patterns: follow model prompt pattern from `runner/adapters/ui/model_prompt.py`.
  - Verification: `python -m pytest tests/unit/application/test_doctor.py tests/specs/test_spec_01_doctor.py`.

### Acceptance Criteria
- `RunnerConfig` includes `ui.session_terminal` and round-trips from YAML correctly.
- Pre-flight check passes without prompting when `ui.session_terminal` is already configured with an installed binary.
- Interactive terminal detection presents detected hosts in priority order and persists user choice to `config.yaml`.
- Non-interactive execution auto-selects the highest-priority available host (`wt.exe` > `pwsh.exe` > `powershell.exe` > `cmd.exe`) without blocking.
- Doctor check fails with actionable message when none of the candidate terminal hosts exist.
- Unit and spec-level tests verify terminal detection, interactive selection, non-interactive fallback, and configuration persistence.
- Full suite green: `python -m pytest`.

### Gotchas
- Test doubles must mock `shutil.which` or injectable path resolver to avoid depending on host OS installed binaries.
- Ensure YAML serializer updates or appends the `ui` block without destroying other config sections or environment variables.
- On Windows, `wt.exe` is an execution alias located in `%LOCALAPPDATA%\Microsoft\WindowsApps`; ensure PATH resolution finds `.exe` variants.
