# T022 — Fix Doctor Worker-Provider Resolution Under Single-Tier Config Load
**Type:** wayfinder:task (HITL)
Status: completed
Completed: 2026-10-14T07:30:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: medium

### Question

`Doctor._check_worker_binary` runs first and resolves `worker.provider` via a
single-tier `YamlConfigLoader.load(<project>/ticket-runner.yaml)`
(`runner/application/doctor.py:209`). The scaffold overlays emitted by T005/T007
(`D:\Sandbox\ticket-runner-live-target`, `D:\Projects\live-test-target`) contain a
`discord:` block with only `enabled: false`, omitting `token_env`, which
`load_from_dict` requires. The load raises, `_get_worker_provider` swallows the
exception, and the provider silently defaults to `"opencode"`. Every
`worker.provider: "antigravity"` live-test site therefore reports
`OpenCode CLI available (...)` and never verifies `agy` nor exercises
`AGENT_ANTIGRAVITY_BIN`. Observed while executing T008; recorded in
`docs/tickets/gotchas.md`.

### Why this matters

Pre-flight currently "passes" for the wrong reason on antigravity sites: it
validates an unrelated binary, so a broken or missing `agy` install is masked
until the first worker run. It also silently defeats the T001/T004 env-var
override on exactly the sites those tickets were built to service.

### Requirements

- Resolve the provider from the same two-tier merged config that `check_config`
  builds (project overlay over `DEFAULT_MACHINE_CONFIG` over
  `~/.ticket-runner/config.yaml`), instead of the single-tier `load()`.
- Do not swallow config errors into a hard-coded `"opencode"` fallback; a
  genuinely unloadable config should surface via `check_config`, not masquerade
  as a valid provider.
- Keep the check order / halt-on-first-failure semantics intact (the binary check
  still runs first).
- Optionally also emit `discord.token_env: "DISCORD_BOT_TOKEN"` in
  `runner/tools/scaffold_sandbox.py`'s `TICKET_RUNNER_YAML_TEMPLATE` to fix the
  overlay at the source — but the Doctor fix must stand on its own.
- Add a regression test in `tests/unit/application/test_doctor.py`: an overlay
  with `worker.provider: "antigravity"` and a `discord:` block lacking
  `token_env` yields the Antigravity/`agy` binary check, not the OpenCode check.
- Existing Doctor unit tests remain green.

### Acceptance Criteria

- `python ticket_runner.py --project-dir D:\Projects\live-test-target doctor`
  (with a pending ticket present) prints the Antigravity binary check (`agy`), not
  `OpenCode CLI available`.
- Same outcome for `D:\Sandbox\ticket-runner-live-target`.
- Regression test added and passing.
- No change to check order or `DoctorReport` shape.

### Smoke Scenarios

**Scenario: Antigravity site verifies the right binary**

- Setup: A live-test site with `worker.provider: "antigravity"` and a pending
  ticket (temporarily author one if the queue is empty).
- Why: Confirm Doctor resolves the configured provider from the merged config.
- Steps:
  1. Run
     `python ticket_runner.py --project-dir D:\Projects\live-test-target doctor`.
  2. Confirm the first check reports the Antigravity binary (`agy`), not OpenCode.
- Expected: The antigravity binary line appears; all other checks unchanged.

### Gotchas

- The root cause is the single-tier `load()` in `_get_worker_provider`, not the
  scaffold template alone — fixing only the template leaves existing overlays
  (and any hand-authored ones) broken.
- `check_config` populates `_loaded_config` later in the run; do not use check
  ordering as the fix (reordering changes halt-on-first-failure behaviour and
  existing test expectations).
- Discovered via T008; referenced by T011 (site doc) and T015 (driver scaffold);
  T099 is gated on this ticket.
