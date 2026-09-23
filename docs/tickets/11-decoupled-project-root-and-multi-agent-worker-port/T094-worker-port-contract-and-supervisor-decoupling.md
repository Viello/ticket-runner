# T094 — Worker Port Contract, OpenCode Adapter Realignment, and Supervisor Decoupling
Status: pending
Spec: docs/specs/11-decoupled-project-root-and-multi-agent-worker-port.md
Blocked by: None
Security: required
Reasoning: medium

### Requirements
- Introduce `WorkerEvent` in `runner/domain/telemetry.py` as a normalized domain model representing agent stream events (`type`, `session_id`, `timestamp`, `token_usage`, `part`, `raw`, `is_known`).
- Define the `AgentWorker` abstract protocol in `runner/ports/agent_worker.py` specifying:
  - `build_run_command(prompt: str, session_id: str | None = None, variant: str | None = None, model_id: str | None = None) -> list[str]`
  - `decode_event(line: str) -> WorkerEvent | None`
  - `extract_resource_access(event: WorkerEvent | None, raw_line: str | None = None) -> frozenset[str]`
- Refactor `runner/adapters/opencode/opencode_worker.py`:
  - Implement `AgentWorker` protocol on `OpenCodeWorker` (or adapter class).
  - Map decoded stream events to `WorkerEvent`, preserving `OpenCodeEvent` as a backwards-compatible alias.
  - Maintain session ID allowlist regex verification (`^ses_[A-Za-z0-9]+$`).
- Create `FakeAgentWorker` in `tests/fakes/fake_agent_worker.py` implementing `AgentWorker` with configurable events and command recording for deterministic testing.
- Decouple `WorkerSupervisor` in `runner/application/worker_supervisor.py`:
  - Remove all direct imports from `runner.adapters.opencode.opencode_worker`.
  - Accept `agent_worker: AgentWorker` in `WorkerSupervisor.__init__`.
  - Delegate command building, event decoding, and resource access extraction through `self._agent_worker`.
- Update `runner/container.py` default wiring to supply `OpenCodeWorker` as the default `AgentWorker` instance.
- Update `ARCHITECTURE.md` to document the `AgentWorker` port contract, `WorkerEvent` wire model, and supervisor decoupling.
- Jump-start:
  - Files to touch: `runner/domain/telemetry.py`, `runner/ports/agent_worker.py`, `runner/adapters/opencode/opencode_worker.py`, `runner/application/worker_supervisor.py`, `runner/container.py`, `tests/fakes/fake_agent_worker.py`, `ARCHITECTURE.md`, `tests/unit/ports/test_agent_worker.py`, `tests/unit/adapters/test_opencode_worker.py`, `tests/unit/application/test_worker_supervisor.py`.
  - Seams: `AgentWorker(Protocol)`, `WorkerEvent`, `WorkerSupervisor(agent_worker=...)`.
  - Verification: `pytest tests/unit/ports/test_agent_worker.py tests/unit/adapters/test_opencode_worker.py tests/unit/application/test_worker_supervisor.py`.

### Acceptance Criteria
- `AgentWorker` protocol is defined in `runner/ports/agent_worker.py` with zero dependencies on concrete adapters.
- `OpenCodeWorker` conforms to `AgentWorker` protocol without type errors and maps all 7 event types to `WorkerEvent`.
- `FakeAgentWorker` implements `AgentWorker` in `tests/fakes/fake_agent_worker.py`.
- `WorkerSupervisor` imports zero symbols from `runner.adapters.opencode.opencode_worker`.
- `ARCHITECTURE.md` is updated to reflect the `AgentWorker` port contract and decoupled supervisor architecture.
- Security verification: `build_run_command` validates prompt string emptiness, rejects invalid session IDs matching `^ses_[A-Za-z0-9]+$`, and avoids raw shell execution strings.

### Smoke Scenarios
**Scenario: Decoupled Worker Protocol and Supervisor Test Double**
- Setup: None (runs from repo root).
- Why: Verify that `WorkerSupervisor` can drive a simulated session to completion using an injected `AgentWorker` test double without importing OpenCode adapter modules.
- Steps:
  1. Run PowerShell command to verify `WorkerSupervisor` runs with `FakeAgentWorker` and no OpenCode imports exist in `runner/application/worker_supervisor.py`:
     ```powershell
     python -c @"
     import inspect
     from runner.application import worker_supervisor
     source = inspect.getsource(worker_supervisor)
     assert 'runner.adapters.opencode' not in source, 'Direct adapter import found in worker_supervisor'
     from runner.ports.agent_worker import AgentWorker
     from tests.fakes.fake_agent_worker import FakeAgentWorker
     fake = FakeAgentWorker()
     assert isinstance(fake, AgentWorker), 'FakeAgentWorker does not satisfy AgentWorker protocol'
     print('PASS: WorkerSupervisor decoupled from OpenCode adapter.')
     "@
     ```
  2. Run `pytest tests/unit/ports/test_agent_worker.py tests/unit/adapters/test_opencode_worker.py tests/unit/application/test_worker_supervisor.py`.
- Expected: Zero import violations detected, tests pass with exit code 0.

### Gotchas
- Keep `OpenCodeEvent` as a type alias or backwards-compatible shim in `runner/adapters/opencode/opencode_worker.py` so existing tests or imports outside supervisor don't break abruptly.
