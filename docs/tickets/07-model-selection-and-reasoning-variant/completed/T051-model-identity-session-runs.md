# T051 — Model identity: `--model` plumbed to every Session Run
Status: completed
Completed: 2026-09-18T09:22:00Z
Spec: docs/specs/07-model-selection-and-reasoning-variant.md
Blocked by: T050
Security: required
Reasoning: medium

### Requirements
- Make model identity session-scoped and enforced on every `opencode run` invocation.
- Command builder: `build_opencode_run_command(..., model_id=None)` appends `-m <model_id>` when non-empty, ordered before `--variant` and before `--auto`.
- Supervisor: `WorkerSupervisor.__init__(..., model_id: str | None = None)`; every `run()` passes it through to the builder.
- Composition: `build_container(model_id: str | None = None)` forwards to the supervisor.
- CLI: add `--model <id>` to the `start` subparser in `ticket_runner.py`. After Doctor passes, validate the flag against the configured `model.models` ids; an unknown id prints an error listing the configured ids and returns exit code 1 without starting orchestration. A valid id is passed into `build_container`. Omitting `--model` leaves `model_id=None` and no `-m` anywhere (interactive/state resolution arrives in T052).
- Jump-start:
  - Files to touch: `runner/adapters/opencode/opencode_worker.py`, `runner/application/worker_supervisor.py`, `runner/container.py`, `ticket_runner.py`, `tests/unit/adapters/test_opencode_worker.py`, `tests/unit/application/test_worker_supervisor.py`, `tests/unit/test_cli.py`.
  - Seams: `doctor.loaded_config` is populated after `run_doctor`; `run_start` already threads `container_instance`/`orchestrator_instance` injection paths — resolve the flag only on the locally built container path.
  - Anchors: `create_parser()` subparser pattern; `FakeDoctorPassing` supplies `loaded_config` in CLI tests.
  - Verification: `python -m pytest tests/unit/adapters/test_opencode_worker.py tests/unit/application/test_worker_supervisor.py tests/unit/test_cli.py`.

### Acceptance Criteria
- Parametrised exact token lists: model only adds `-m` before `--auto`; variant only adds `--variant`; both add `-m` then `--variant`; neither adds nothing. `model_id=""` and `None` omit `-m`.
- Every Session Run path (initial, handoff resume, crash retry, nudge, answer-resume) carries `-m` when the supervisor has a model id.
- `start --model qwen/qwen-plus` with a config containing that id builds the container with that model; `start --model bogus` prints the configured ids and exits 1 with no orchestrator lifecycle run.
- No `--model` means no `-m` in any spawn, and all existing CLI tests stay green; monkeypatched `build_container` doubles accept the new keyword.
- Full suite green: `python -m pytest`.

### Gotchas
- Exit code for an unknown `--model` is 1 (runtime error); exit 2 stays reserved for operator aborts.
- The model id reaches argv as one token; validation against the configured list happens before it is ever passed through (state-driven resolution re-validates in T052).
- Keep `--model` on the `start` subparser only; `doctor` has no model context.
- `run_start` test doubles that replace `build_container` must tolerate the new `model_id` keyword.
