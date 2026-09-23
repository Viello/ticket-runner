# Spec 11: Decoupled Project Root & Multi-Agent Worker Port

## Problem Statement

Ticket Runner currently assumes that the execution directory (`cwd`), the configuration file (`config.yaml`), the ticket queue (`docs/tickets/`), runtime state (`.agent/`), and the git repository all reside in the exact same directory where the runner process is launched. Furthermore, `WorkerSupervisor` directly imports and depends on `runner.adapters.opencode.opencode_worker`, hardcoding OpenCode as the sole execution agent.

This tight coupling prevents Ticket Runner from operating as an external, reusable orchestrator that can manage arbitrary target repositories, and prevents developers from plugging in alternative agents such as the Antigravity CLI (`agy`).

## Solution

1. **Decoupled Project Root**: Introduce a `--project-dir <path>` CLI argument (defaulting to the current working directory). Update the composition root (`container.py`), `RuntimePaths`, `ConfigLoader`, `GitClient`, and `TicketStore` to resolve all project files, runtime signals, state stores, and ticket queues relative to the specified target project directory.
2. **`AgentWorker` Port Abstraction**: Define a clean `AgentWorker` protocol in `runner/ports/agent_worker.py` specifying lifecycle contracts for command construction, subprocess spawning, streaming event decoding, resource access detection, and token usage telemetry.
3. **Multi-Agent Adapters**:
   - Refactor `OpenCodeWorker` into a concrete adapter implementing `AgentWorker`.
   - Create a clean stub adapter `AntigravityWorker` implementing `AgentWorker`, prepared for full SDK/CLI integration.
   - Inject the configured `AgentWorker` into `WorkerSupervisor` via `runner/container.py` based on `worker.provider` configuration (`opencode` or `antigravity`).

## User Stories

1. As a developer, I want to run `ticket-runner --project-dir /path/to/my-app start`, so that Ticket Runner can orchestrate an external repository from any location on my system.
2. As a developer, I want `--project-dir` to default to the current working directory if omitted, so that existing single-repo workflows remain backwards-compatible.
3. As a developer, I want Ticket Runner to validate that `--project-dir` exists and is a valid git repository before executing, so that clear errors are raised immediately if the path is invalid.
4. As an architectural maintainer, I want `WorkerSupervisor` to depend strictly on the `AgentWorker` port, so that the application layer has zero dependencies on OpenCode-specific modules.
5. As an architectural maintainer, I want the `AgentWorker` port to expose a unified `spawn` method, so that process creation semantics are standardized across agent backends.
6. As an architectural maintainer, I want the `AgentWorker` port to expose a unified `decode_event` method returning normalized `WorkerEvent` models, so that telemetry, status updates, and logging work identically regardless of provider.
7. As an architectural maintainer, I want the `AgentWorker` port to expose a unified `extract_resource_access` method, so that skill and `AGENTS.md` access tracking functions universally.
8. As a developer, I want `OpenCodeWorker` to implement the `AgentWorker` protocol with full fidelity, preserving existing streaming JSON decoding, token telemetry, and session resumption.
9. As a developer, I want an `AntigravityWorker` adapter stub implementing `AgentWorker`, so that Antigravity CLI or Python SDK support can be activated via configuration without touching the core supervisor.
10. As a developer, I want to configure `worker.provider: "opencode"` or `worker.provider: "antigravity"` in `config.yaml`, so that I can easily toggle between supported agent providers.
11. As an operator, I want Doctor pre-flight checks to verify the binary existence of the configured `worker.provider` (e.g. checking `opencode` or `agy`), so that missing CLI tools are caught before queue processing begins.
12. As a maintainer, I want all unit and spec test suites to accept a mock or fake `AgentWorker`, so that worker interactions can be tested deterministically without real subprocess execution.
13. As an operator, I want the final ticket of this spec queue to audit implementation against Spec 11 and update living documents if any architectural details shifted during development.

## Implementation Decisions

1. **CLI Parameter & Path Plumbing**:
   - `ticket_runner.py` accepts `--project-dir` (type `Path`, default `Path.cwd().resolve()`).
   - `Container.create()` accepts `project_dir: Path` and injects it into:
     - `RuntimePaths(root_dir=project_dir / ".agent")`
     - `TicketStore(tickets_dir=project_dir / "docs" / "tickets")`
     - `SubprocessRunner(default_cwd=project_dir)`
     - `GitClient(repo_dir=project_dir)`
     - `ConfigLoader(config_path=...)`

2. **The `AgentWorker` Protocol Seam (`runner/ports/agent_worker.py`)**:
   ```python
   from typing import Protocol, Any
   from pathlib import Path
   from runner.domain.telemetry import WorkerEvent, TokenUsage

   class AgentWorker(Protocol):
       def build_run_command(
           self,
           prompt: str,
           session_id: str | None = None,
           variant: str | None = None,
           model_id: str | None = None,
       ) -> list[str]:
           ...

       def decode_event(self, line: str) -> WorkerEvent | None:
           ...

       def extract_resource_access(
           self,
           event: WorkerEvent | None,
           raw_line: str | None = None,
       ) -> frozenset[str]:
           ...
   ```

3. **Adapter Realignment**:
   - Move OpenCode-specific models from `runner/adapters/opencode/opencode_worker.py` to implement `AgentWorker`.
   - Normalize `OpenCodeEvent` into the domain entity `WorkerEvent`.
   - Create `runner/adapters/antigravity/antigravity_worker.py` implementing `AgentWorker`, providing initial command-line mapping (`agy run`) and event decoding stubs.

4. **Supervisor Decoupling (`runner/application/worker_supervisor.py`)**:
   - Replace direct imports of `OpenCodeWorkerCli`, `build_opencode_run_command`, `decode_event`, and `extract_resource_access` with an injected `agent_worker: AgentWorker`.
   - `WorkerSupervisor.__init__` receives `agent_worker: AgentWorker`.

5. **Doctor Pre-Flight Check Extension (`runner/application/doctor.py`)**:
   - Doctor checks the availability of the binary corresponding to `config.worker.provider`:
     - If `opencode`: verify `opencode` binary exists in `PATH`.
     - If `antigravity`: verify `agy` binary exists in `PATH`.

## Testing Decisions

- **Fast Isolated Tests**:
  - `tests/unit/ports/test_agent_worker.py`: Verify that both `OpenCodeWorker` and `AntigravityWorker` conform to `AgentWorker` protocol without type errors.
  - `tests/unit/adapters/test_opencode_worker_adapter.py`: Verify that OpenCode command generation and JSONL decoding map cleanly to domain `WorkerEvent`.
  - `tests/unit/application/test_worker_supervisor_decoupled.py`: Test `WorkerSupervisor` using a `FakeAgentWorker` double, asserting that process lifecycle, stalling, and signal termination work without any OpenCode dependencies.
  - `tests/unit/domain/test_runtime_paths_external.py`: Verify that `RuntimePaths` and `TicketStore` resolve correctly when given an arbitrary external path (`/tmp/other-project` or `D:\test\app`).
- **Integration Tests**:
  - `tests/specs/test_spec_11_decoupled_runner.py`: End-to-end simulation of running the CLI against a separate temporary directory containing a sample ticket queue.

## Out of Scope

- Implementing the interactive `ticket-runner init` wizard (deferred to Spec 12).
- Implementing the token-guarded behavioral verification harness (deferred to Spec 13).
- Full Antigravity Python SDK in-process execution (stub adapter CLI mapping only in this spec).

## Further Notes

- Backwards compatibility is strictly preserved: running `ticket-runner start` in the repository root without `--project-dir` will default to the current directory and behave identically to the existing system.
