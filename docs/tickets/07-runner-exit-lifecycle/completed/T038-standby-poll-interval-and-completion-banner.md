# T038 — Standby poll interval and completion banner
Status: completed
Completed: 2026-09-18T03:50:30Z
Spec: docs/specs/07-runner-exit-lifecycle.md
Blocked by: none

### Requirements
- Add `poll_interval: float = 5.0` to `LifecycleConfig` (runner/domain/config.py) with validation (positive finite number), and load it from YAML via `YamlConfigLoader` (runner/adapters/config/yaml_config_loader.py) into the `lifecycle:` section. Mirror it in the tracked template `config.example.yaml` with a comment.
- Thread the configured interval into the standby watch loop: `ticket_runner.run_start` (ticket_runner.py) should pass the loaded `config.lifecycle.poll_interval` to `QueueOrchestrator.run_lifecycle` (runner/application/queue_orchestrator.py), which already accepts `poll_interval`. Keep the `run_start` parameter as an override that defaults to the config value.
- Replace the standby entry message (`"[Queue] Lifecycle policy 'standby': Entering idle watch loop (polling every 5s)..."`) with an unambiguous one-time banner, emitted after the lock is released and before the watch loop begins: all tickets processed, standing by watching `docs/tickets/` for new tickets, and how to exit (Ctrl+C). No periodic heartbeat.
- Ensure the banner prints exactly once per standby entry (including re-entry after a standby-resume cycle drains the queue again).

### Acceptance Criteria
- `QueueOrchestrator.run_lifecycle` on a drained queue with `queue_completion="standby"` prints the new banner exactly once and polls at the configured interval (verifiable with an injected clock / `max_standby_iterations`).
- `poll_interval` is honored when set in config; an invalid value (negative, zero, or non-numeric) is rejected by config validation with a clear error.
- `config.example.yaml` documents `lifecycle.poll_interval`.
- Full pytest suite is green.

### Gotchas
- The sentinel lock must be released before the banner/watch loop (Windows sharing-violation gotcha already recorded in `docs/tickets/gotchas.md`) — print the banner after `self.release_lock()`.
- The CLI currently hardcodes `poll_interval: float = 5.0` on `run_start`; change the default to read from the loaded config while keeping the override parameter for tests.
- Standby re-entry after resuming and draining again must not double-print or skip the banner.