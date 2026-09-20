# T062 — Config schema auto support and Doctor pre-flight verification
Status: completed
Completed: 2026-09-20T10:24:00Z
Blocked by: T061
Reasoning: low

### Requirements
- Update `config.yaml` and `config.example.yaml` to default `ui.session_terminal: "auto"`.
- Update domain model `UIConfig` and `YamlConfigLoader` in `runner/adapters/yaml/config_loader.py` to permit `"auto"` alongside existing allowed candidate terminal hosts.
- Update `Doctor.check_terminal_host()` in `runner/application/doctor.py`:
  - When `session_terminal` is `"auto"` (or empty): uses `TerminalHostDetector` to sniff the active host, confirms it resolves on PATH, and reports `✓ Session terminal host 'auto' resolved to '<host>' on PATH.`.
  - When an explicit host is configured (e.g. `"powershell.exe"`), retains existing behavior and validates that specific host on PATH.
  - Fails with clear remediation if no supported terminal hosts can be resolved.
- Wire `TerminalHostDetector` into `build_container` in `runner/container.py` and `ticket_runner.py` so `TuiCoordinator` receives the resolved host binary.
- Jump-start:
  - Files to touch: `runner/domain/config.py`, `runner/adapters/yaml/config_loader.py`, `runner/application/doctor.py`, `runner/container.py`, `ticket_runner.py`, `config.yaml`, `config.example.yaml`, `tests/unit/application/test_doctor.py`, `tests/unit/adapters/test_yaml_config_loader.py`.
  - Seams: `Doctor.check_terminal_host()` and `build_container`.
  - Anchor patterns: Existing candidate probing in `runner/application/doctor.py` and `YamlConfigLoader.load()`.
  - Verification command: `python -m pytest tests/unit/application/test_doctor.py tests/unit/adapters/test_yaml_config_loader.py tests/unit/test_container.py`.

### Acceptance Criteria
- `config.yaml` and `config.example.yaml` specify `session_terminal: "auto"`.
- `YamlConfigLoader` successfully validates and loads `"auto"` into `UIConfig.session_terminal`.
- `Doctor.check_terminal_host()` passes when `session_terminal` is `"auto"` and reports the resolved binary name.
- Explicit host setting in `config.yaml` overrides auto-detection and continues to validate that specific binary.
- `build_container` resolves `"auto"` to a concrete binary before instantiating `TuiCoordinator`.
- All unit tests in `tests/unit/application/test_doctor.py`, `tests/unit/adapters/test_yaml_config_loader.py`, and `tests/unit/test_container.py` pass cleanly.

### Gotchas
- Ensure `TuiCoordinator` receives the resolved host string (e.g. `"powershell.exe"`), never the raw string `"auto"`, so that `build_tui_command` only ever receives valid host binaries.
- Non-destructive YAML persistence should preserve human comments when updating configuration.
