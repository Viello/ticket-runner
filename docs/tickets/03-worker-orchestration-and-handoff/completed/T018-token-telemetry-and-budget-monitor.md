# T018 — Token telemetry and budget monitor (domain)
Status: completed
Completed: 2026-09-16T13:04:30Z
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add `runner/domain/telemetry.py` with a pure domain model: `TokenUsage` (input, output, reasoning, cache read, cache write, optional total), an `occupancy` property implementing ADR 0015 (total when present, else input + output + reasoning + cache read + cache write), a budget-action enum (WARN, HANDOFF, CEILING), and a `BudgetMonitor` driven by `TokenBudgetConfig` that reports actions as occupancy is observed.
- Implement `effective_ceiling(configured, model_limit=None) -> int` returning `min(configured, model_limit)` when a limit is supplied, else the configured value.
- Semantics: WARN fires exactly once per Ticket supervision chain on first crossing `warn`; HANDOFF fires once when occupancy `>= handoff`; CEILING wins when occupancy `>= ceiling`; when one update crosses several thresholds, the highest-priority action is current while WARN/HANDOFF reminders are recorded as already-sent (deterministic, documented ordering).
- No I/O, no JSON parsing, no async — event decoding is T019's adapter; the monitor consumes `TokenUsage` objects only.
- Jump-start:
  - Files to touch: `runner/domain/telemetry.py`, `tests/unit/domain/test_telemetry.py`.
  - Seams: `TokenBudgetConfig` (`runner/domain/config.py`) supplies thresholds; `runner/domain/__init__.py` follows the flat entity convention.
  - Anchor patterns: invariant and threshold-parametrization tests in `tests/unit/domain/test_config.py`.
  - Verification: `pytest tests/unit/domain/test_telemetry.py`.

### Acceptance Criteria
- Occupancy uses `total` when present and the documented sum otherwise; cache/reasoning fields are counted exactly once (per-step provider semantics: `input` excludes cache read/write).
- Monitor emits WARN once per chain, HANDOFF once when `>= 135000`, CEILING when `>= 150000`; below 120k no action is reported.
- A resumed session reporting a larger occupancy does not re-fire WARN and immediately reports HANDOFF/CEILING when appropriate (monotonic per chain, reset only by constructing a fresh monitor).
- `effective_ceiling` returns the configured ceiling without a model limit and the model limit when it is smaller.

### Gotchas
- `tokens.input` excludes cache read/write — follow ADR 0015's formula and cover it with a test using a realistic cross-checked payload (see the example line in ADR 0015's narrative).
- `total` is optional in the stream; never assume it exists.
- Keep the module sync; no pytest-asyncio tricks required.
