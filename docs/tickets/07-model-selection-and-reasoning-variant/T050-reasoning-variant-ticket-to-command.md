# T050 — Reasoning variant flows ticket frontmatter to every Session Run
Status: pending
Spec: docs/specs/07-model-selection-and-reasoning-variant.md
Blocked by: T049
Security: required
Reasoning: medium

### Requirements
- Carry a ticket's optional `Reasoning:` frontmatter value to `opencode run --variant` for every Session Run spawned under that ticket.
- Domain: append `reasoning: str = ""` to `Ticket` (frozen dataclass, validated string; empty means unset).
- Parser: extract `Reasoning:` case-insensitively (metadata keys are already lowercased), strip surrounding whitespace, and pass the value through verbatim — no lowercasing and no allowlist; absent or blank yields `""`. Mirror `_parse_security_required`.
- Command builder: `build_opencode_run_command(prompt, session_id=None, variant=None)` appends `--variant <variant>` after `--session` and before `--auto`, only when `variant` is a non-empty string. (The `model_id`/`-m` parameter arrives in T051.)
- Supervisor: `WorkerSupervisor.__init__(..., default_reasoning: str = "")`; inside `run()`, resolve `variant = ticket.reasoning or self._default_reasoning` when `ticket` is a `Ticket` (plain string ticket ids fall back to the default) and pass it to the builder. All run kinds — initial, handoff resume, crash retry, nudge, answer-resume — flow through this method.
- Container: wire `default_reasoning=resolved_config.model.default_reasoning` into the `WorkerSupervisor` construction.
- Jump-start:
  - Files to touch: `runner/domain/ticket.py`, `runner/adapters/markdown/parser.py`, `runner/adapters/opencode/opencode_worker.py`, `runner/application/worker_supervisor.py`, `runner/container.py`, plus matching unit tests.
  - Anchors: `_parse_security_required`; existing command tests in `tests/unit/adapters/test_opencode_worker.py`; the fake-runner run-path fixtures in `tests/unit/application/test_worker_supervisor.py` and `tests/unit/application/test_handoff_coordinator.py`.
  - Verification: `python -m pytest tests/unit/adapters/test_opencode_worker.py tests/unit/adapters/test_ticket_parser.py tests/unit/application/test_worker_supervisor.py`.

### Acceptance Criteria
- `Reasoning: HIGH`, `reasoning: high`, and `Reasoning:` (blank) parse to `"HIGH"`, `"high"`, and `""` respectively; a ticket without the field yields `""`.
- `build_opencode_run_command("p", variant="high")` produces `["opencode", "run", "--format", "json", "--variant", "high", "--auto", "p"]`; `variant=""` and `variant=None` omit the flag.
- The supervisor uses the ticket value when present, otherwise `default_reasoning`; when both are unset the flag is absent from the spawn.
- Variant resolution holds across an initial run, a handoff resume, and an answer-resume run (asserted via captured command lists).
- `build_container` wires the configured default into its supervisor.
- Existing suite green — commands without a variant still produce the exact token lists asserted by the spec 03/04 suites.

### Gotchas
- Flags must be inserted before `--auto`; spec-04 tests index tokens (`cmd[4]`, `cmd[5]`, `cmd[7]`) for commands carrying no model/variant and must remain valid.
- The value is untrusted ticket input reaching a subprocess: pass it as a single argv token, never shell-quoted, split, or reordered; whitespace-only values are treated as unset.
- `WorkerSupervisor.run` accepts `Ticket | str`; only the `Ticket` branch can carry reasoning.
- `Ticket` is frozen and constructed in many tests — appending a defaulted field keeps them compiling.
