# T025 — Prefactor: rename verification budget to `max_attempts` and align Spec 04
Status: pending
Spec: docs/specs/04-signal-protocol-and-gatekeeper.md
Blocked by: none

### Requirements
- Rename the verification budget to `max_attempts` end to end, meaning "total Verification Attempts before the Circuit Breaker trips" (default 3): domain config, YAML key `verification.max_attempts`, both config files, the README config table, and every test that references the old name.
- Patch Spec 04 so no decision contradicts the settled design: US3 and the signal-detection decision use a 10-second exit grace; the Circuit Breaker budget comes from `verification.max_attempts` instead of being hardcoded; add the Verification Attempt model (one attempt = Worker cycle, Signal validation, and Gatekeeper verification; malformed Signal and worker-phase non-READY statuses consume budget with diagnostics fed back to the active session); single-use Signal lifecycle (ready consumed on parse, answered questions retained, purge at Ticket start); intervention menu contract (`[R]etry` full budget reset with optional hint, `[S]kip` confirmed destructive skip, `[A]bort` preserving the working tree); optional `scope` field on the ready signal; Gatekeeper commands run as shell strings with per-command `timeout_seconds`.
- Jump-start:
  - Files to touch: `runner/domain/config.py`, `runner/adapters/config/yaml_config_loader.py`, `config.yaml`, `config.example.yaml`, `README.md`, `docs/specs/04-signal-protocol-and-gatekeeper.md`, `tests/unit/domain/test_config.py`, `tests/unit/adapters/test_yaml_config_loader.py`.
  - Seams: `VerificationConfig` validation and the loader's defaults for the `verification` block.
  - Anchor patterns: loader error style in `runner/adapters/config/yaml_config_loader.py`; README table formatting.
  - Verification: full `pytest` green; `rg "max_retries"` returns no hits outside `ticket-runner-plan.md`.

### Acceptance Criteria
- `VerificationConfig.max_attempts` (default 3, positive-integer validation) replaces `max_retries` everywhere outside the historical plan file.
- YAML `verification.max_attempts` parses, defaults to 3 when omitted, and rejects non-positive values; both config files document it as the total Verification Attempts before the Circuit Breaker trips.
- Spec 04 describes the 10-second grace, the configured budget, the Verification Attempt model, shell-executed commands, single-use Signals, the intervention menu, abort semantics, and the optional `scope`; it no longer mentions 5 seconds, a hardcoded 3, or `max_retries`.
- The full pytest suite is green.

### Gotchas
- `ticket-runner-plan.md` is a historical plan — leave it untouched.
- The rename is user-facing configuration: update comments and README prose, not just identifiers.
- Do not renumber Spec 04 user stories; US1–US11 stay stable so tickets and the behavioral suite keep referencing them.
