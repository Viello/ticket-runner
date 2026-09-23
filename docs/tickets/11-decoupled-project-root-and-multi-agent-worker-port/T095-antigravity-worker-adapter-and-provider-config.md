# T095 — Antigravity Worker Adapter and Multi-Agent Provider Configuration
Status: pending
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
Blocked by: T094
Security: required
Reasoning: medium

### Requirements
- Extend `WorkerConfig` in `runner/domain/config.py` with `provider: str = "opencode"` and validate that `provider` is either `"opencode"` or `"antigravity"`, raising `ConfigError` for unsupported providers.
- Implement `AntigravityWorker` adapter in `runner/adapters/antigravity/antigravity_worker.py` conforming to the `AgentWorker` protocol:
  - `build_run_command(...)`: maps arguments to `['agy', 'run', '--auto', prompt]`, appending optional model flags or resume session options.
  - `decode_event(...)`: stream event decoder returning normalized `WorkerEvent` models.
  - `extract_resource_access(...)`: resource access detection stub for Antigravity events.
- Update `runner/container.py` factory logic to instantiate either `OpenCodeWorker` or `AntigravityWorker` based on `config.worker.provider`.
- Update `config.example.yaml` and `config.yaml` to document `worker.provider` options and defaults.
- Update `README.md` Worker Configuration section documenting provider choices (`opencode` vs `antigravity`).
- Jump-start:
  - Files to touch: `runner/domain/config.py`, `runner/adapters/antigravity/__init__.py`, `runner/adapters/antigravity/antigravity_worker.py`, `runner/container.py`, `config.yaml`, `config.example.yaml`, `README.md`, `tests/unit/adapters/test_antigravity_worker_adapter.py`, `tests/unit/domain/test_config.py`.
  - Seams: `WorkerConfig.provider`, `AntigravityWorker.build_run_command`, `AntigravityWorker.decode_event`.
  - Verification: `pytest tests/unit/adapters/test_antigravity_worker_adapter.py tests/unit/domain/test_config.py`.

### Acceptance Criteria
- `WorkerConfig` rejects invalid provider values with `ConfigError` and defaults to `"opencode"`.
- `AntigravityWorker` implements `AgentWorker` protocol and produces correct CLI argument tokens (`['agy', 'run', ...]`).
- `build_container` instantiates `AntigravityWorker` when `config.worker.provider == "antigravity"`.
- `config.yaml`, `config.example.yaml`, and `README.md` document `worker.provider`.
- Security verification: `AntigravityWorker.build_run_command` properly parameterizes prompt and flags into distinct argv tokens without shell interpolation.

### Smoke Scenarios
**Scenario: Antigravity Command Generation and Config Switching**
- Setup: None (runs from repo root).
- Why: Verify that configuring `worker.provider: "antigravity"` creates an `AntigravityWorker` adapter and builds valid CLI arguments.
- Steps:
  1. Run PowerShell verification asserting `WorkerConfig` accepts "antigravity", rejects invalid providers, and `AntigravityWorker` constructs expected argv lists:
     ```powershell
     python -c @"
     from runner.domain.config import WorkerConfig
     from runner.domain.exceptions import ConfigError
     cfg = WorkerConfig(execution_skill='.agents/skills/implement/SKILL.md', provider='antigravity')
     assert cfg.provider == 'antigravity'
     try:
         WorkerConfig(execution_skill='.agents/skills/implement/SKILL.md', provider='unsupported')
         raise AssertionError('Should have failed on invalid provider')
     except ConfigError:
         pass
     from runner.adapters.antigravity.antigravity_worker import AntigravityWorker
     worker = AntigravityWorker()
     cmd = worker.build_run_command(prompt='implement ticket')
     assert cmd[:3] == ['agy', 'run', '--auto'], f'Unexpected cmd: {cmd}'
     print('PASS: AntigravityWorker and provider configuration verified.')
     "@
     ```
  2. Run `pytest tests/unit/adapters/test_antigravity_worker_adapter.py`.
- Expected: CLI argv starts with `['agy', 'run', '--auto']`, config validates properly, tests exit 0.

### Gotchas
- The Antigravity adapter in this spec is an execution CLI adapter stub; full Python SDK in-process streaming is out of scope per Spec 11.
