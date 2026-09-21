# Spec 10 — Stuck-Detection, Diagnostic Escalation & Observability

## Problem Statement

When a verification suite hangs — because a test blocks on terminal input, an asyncio event never fires, or a TUI subsystem waits forever — the orchestrator sits idle until the global `timeout_seconds` expires, then burns the remaining retry budget on the identical broken suite. A slow machine exacerbates the problem: a 30-second default silence window produces false alarms on hardware where test setup alone takes 20–40 seconds.

Cascading failures compound it further. When one broken import or initialization bug kills 40 tests at once, the LLM and the operator see a wall of noise rather than a root cause. Without triage, all retries chase symptoms.

Neither the orchestrator nor any skill currently gives a manually-guided LLM session a runbook for this situation, so the problem recurs across every project.

On the observability side: while a ticket runs, the operator has no window into what the Worker is doing between steps. Diagnosing slow or stuck runs requires tailing raw log files.

## Solution

A layered stuck-detection system composed of four capabilities:

1. **Silence window** — a configurable outer guard on every verification subprocess: if no stdout/stderr line arrives within `silence_window_seconds`, the process tree is killed and the failure is classified `HANG` before any retry analysis. Applies universally regardless of test runner.

2. **Failure analyser** — a pure domain function that inspects raw output and termination reason, classifies the failure (`HANG` / `CASCADE` / `ENV` / `FLAKY`), extracts the top-3 error-class fingerprints from the full run, and re-runs the first failing test in isolation to produce a clean single-failure trace. The isolation command is inferred by heuristic from `test_cmd`, with an explicit `isolation_cmd` override in config for edge cases. Per-test timeout injection (optional, `per_test_timeout_seconds`) adds an inner guard for runners that support it natively.

3. **Structured diagnostic report + escalation** — assembled from the `FailureDiagnostic` (classification, identified tests, top errors, bounded log tail, suggested action) plus a token-budget snapshot. Emitted at a configurable attempt threshold (`bug_escalation_at: 1` by default, `-1` for circuit-breaker-only), sent simultaneously to terminal and Discord (graceful no-op if Discord is not yet configured). The report always asks: *"Run `/diagnosing-bugs`? [Y/n]"* — operator can step in without losing context.

4. **Durable status event file + step observability** — `.agent/status.json` is written atomically on every Worker step, attempt transition, and escalation event, giving any consumer (terminal, Discord, future TUI) a stable poll target. The terminal surfaces the Worker's own step narration in near-real-time alongside a periodic heartbeat line.

The `/diagnosing-bugs` skill is extended with a runner-agnostic stuck-test-suite runbook so manually-guided LLM sessions benefit from the same discipline.

## User Stories

1. As a Runner operator, I want the orchestrator to detect a hanging verification suite within a configurable window (default 60 s, raised on slow machines) and kill it cleanly, so I don't wait 5 minutes for a timeout that never resolves.
2. As a Runner operator, I want the failure classified as HANG, CASCADE, ENV, or FLAKY before any retry is consumed, so I understand the failure mode without reading raw logs.
3. As a Runner operator, I want the top-3 error-class fingerprints extracted from a cascade run, so I can immediately see the root-cause pattern.
4. As a Runner operator, I want the first failing test re-run in isolation before a retry, so I receive a clean single-failure trace instead of 40 cascaded failures.
5. As a Runner operator, I want a structured diagnostic report — classification, root test(s), top errors, bounded log tail, suggested next action, and token-budget snapshot — surfaced at attempt 1 (configurable), so I can decide whether to intervene or allow retries.
6. As a Runner operator, I want the diagnostic sent to both terminal and Discord simultaneously, so I see it regardless of my presence mode.
7. As a Runner operator, I want the diagnostic to ask whether I want to run `/diagnosing-bugs`, so I can step in interactively without losing the failure context.
8. As a Runner operator, I want `silence_window_seconds` configurable in `config.yaml` with a 60 s default, so I can raise it on a slow machine to avoid false-alarm kills during long test setup.
9. As a Runner operator, I want `per_test_timeout_seconds` configurable (0 = disabled), so I can optionally inject a runner-native per-test timeout flag for supported runners.
10. As a Runner operator, I want an `isolation_cmd` override in config (e.g. `pytest {test_id} -x`), so I can specify the exact single-test rerun when the heuristic fails.
11. As a Runner operator, I want `bug_escalation_at` configurable (-1 = circuit-breaker-only, 0 = never, N = after Nth attempt), so I tune escalation aggressiveness per project.
12. As a Runner operator, I want a durable `.agent/status.json` written on every Worker step and attempt transition, so any observer can poll current orchestrator state without parsing log files.
13. As a Runner operator, I want the Worker's step narration surfaced in near-real-time on the terminal, so I know what the model is doing between steps.
14. As a Runner operator, I want a periodic heartbeat line (ticket, attempt, token budget) when the Worker is silent, so I always have a sense of progress.
15. As a manually-guided LLM session participant, I want `/diagnosing-bugs` to include a stuck-test-suite runbook, so any LLM I guide can self-triage and escalate rather than spinning on a broken suite.
16. As a Worker (LLM), I want to know that when my test suite stalls, the required path is to classify the failure and isolate the first failing test before emitting a ready signal, so I don't burn all my attempts on the same undiagnosed failure.
17. As a Runner operator using a non-Python project, I want the stuck-detection system to work regardless of test runner (jest, go test, cargo test, dotnet test, etc.), so the discipline is universally applicable.
18. As a Runner operator, I want the silence window to be the universal outer guard and the per-test timeout to be an optional runner-specific inner guard, so the system is robust even when no per-test timeout flag is available.

## Implementation Decisions

### Config schema

Four fields added to the `verification:` section:

```yaml
verification:
  silence_window_seconds: 60    # kill if no stdout/stderr for N seconds; raise for slow machines
  per_test_timeout_seconds: 0   # 0 = disabled; inject runner-native flag when > 0
  isolation_cmd: ""             # optional template for single-test rerun, e.g. "pytest {test_id} -x"
  bug_escalation_at: 1          # escalate after this attempt number; -1 = circuit-breaker only; 0 = never
```

The config loader and validator must accept these fields with the defaults above. `silence_window_seconds` must be > 0; `per_test_timeout_seconds` must be >= 0; `bug_escalation_at` must be >= -1.

### Silence window (verification subprocess guard)

The existing verification command runner streams stdout/stderr from the test subprocess. Extend its inner streaming loop with a silence timer mirroring the pattern already present in `WorkerSupervisor` for the Worker process. If no line arrives within `silence_window_seconds`:

- Terminate the process tree via `taskkill /T /F` on Windows, `proc.terminate()` on POSIX (same pattern as `SubprocessProcessHandle`).
- Return a result carrying `termination_reason = HANG` so downstream analysis can classify without inspecting output.

`per_test_timeout_seconds > 0` triggers a heuristic: the runner detects the test framework from `test_cmd` keywords and injects the appropriate flag (`--timeout=N` for pytest, `--testTimeout=N*1000` for jest/vitest, `-timeout Ns` for go test). Runners without native support (cargo, dotnet) receive no flag; the silence window remains their only guard.

### Failure analyser (domain service)

A pure function — no subprocess dependencies — with signature:

```
analyse(output_lines, exit_code, termination_reason, isolation_cmd_builder) → FailureDiagnostic
```

`FailureDiagnostic` is a value object containing:
- `label`: `HANG | CASCADE | ENV | FLAKY`
- `root_tests`: list of test identifiers found as the first failing test(s)
- `top_errors`: up to 3 unique error-class fingerprints (exception names, "ImportError", "AssertionError", etc.)
- `log_tail`: last 100 lines of combined output
- `isolation_output`: output of re-running the first failing test in isolation (None if skipped or heuristic unavailable)
- `suggested_action`: short human-readable string

**Classification heuristics:**
- `HANG` — termination_reason is STALLED/HANG
- `ENV` — output contains "ModuleNotFoundError", "ImportError", "command not found", or similar setup failure patterns before any test runs
- `CASCADE` — many `FAILED` / `ERROR` entries with a single repeating error class
- `FLAKY` — none of the above (exit != 0, no clear pattern)

**Isolation command heuristic** (used when `isolation_cmd` is empty):
- `test_cmd` contains `pytest` → `pytest {test_id} -x`
- `test_cmd` contains `jest` or `vitest` → `npx {runner} --testNamePattern "{test_name}"`
- `test_cmd` contains `go test` → `go test -run {test_name} ./...`
- `test_cmd` contains `cargo test` → `cargo test {test_name}`
- Otherwise → skip isolation, set `isolation_output = None`

### Structured diagnostic report

A renderer that takes `FailureDiagnostic` + current `TokenUsage` and produces a bounded markdown section for terminal/Discord output. Format:

```
⚠ HANG detected — test_suite.py::test_tui_render
Top errors: TimeoutError (×12), AssertionError (×3), ...
[last 100 lines of output]
Token budget: 42,150 / 150,000
Suggested: Run /diagnosing-bugs (§ Stuck-Test-Suite Runbook)
Run /diagnosing-bugs now? [Y/n]
```

### Escalation coordinator

A domain service checked inside `VerificationLoop` after each attempt completes with a non-zero exit:

1. Build `FailureDiagnostic` via analyser.
2. If `bug_escalation_at == 0` → skip escalation.
3. If `bug_escalation_at == -1` → escalate only when circuit breaker is about to trip.
4. If `attempt_number >= bug_escalation_at` → escalate.
5. Render diagnostic report; send to terminal via `InterventionGateway` AND Discord channel (no-op stub if Discord not yet implemented).
6. Prompt: *"Run /diagnosing-bugs? [Y/n]"* — on Y: yield `INTERVENTION_REQUESTED` with diagnostic attached; on N/non-interactive: consume reply, log, resume next attempt.

### Status event file

**Port:** `StatusPublisher` — `publish(event: StatusEvent) → None`. Events: `STEP_FINISHED`, `ATTEMPT_STARTED`, `ATTEMPT_ENDED`, `ESCALATION_EMITTED`, `CIRCUIT_BREAKER_TRIPPED`.

**Adapter:** `JsonFileStatusPublisher` writes `.agent/status.json` atomically (same `atomic_write_text` helper used elsewhere):

```json
{
  "ticket_id": "T063",
  "run_state": "running",
  "attempt": 2,
  "max_attempts": 3,
  "token_count": 42150,
  "token_budget": 150000,
  "last_step_summary": "Edited runner/verification.py to add silence window guard",
  "last_step_at": "2026-09-21T11:00:00+08:00",
  "last_event": "STEP_FINISHED"
}
```

### Step-summary observability

`WorkerSupervisor` already processes `step_finish` events; hook a callback that:
- Extracts the assistant message text (the model's narration of what it just did).
- Writes a `STEP_FINISHED` event to `StatusPublisher`.
- In nearby mode: prints one truncated line (≤ 120 chars) to terminal.
- Heartbeat: if 30 seconds pass without a step event, print a heartbeat line `[T063 | attempt 2/3 | 42k tokens | idle…]`.

## Testing Decisions

**What makes a good test:** test observable behaviour at the highest seam that exercises the real code path. Do not test internal parse helpers or classification heuristics in isolation; test the analyser function end-to-end with fixture output strings.

**Silence window tests** — extend the existing `FakeProcessHandle` pattern:
- Yield lines with injected clock gaps exceeding `silence_window_seconds`.
- Assert the process is killed and `termination_reason == HANG` is returned.
- Assert normal fast completion is not affected.

**Failure analyser tests** — pure unit tests in `tests/unit/domain/`:
- Fixture: pytest HANG output → assert `label == HANG`, `root_tests` populated.
- Fixture: 40-failure cascade with common ImportError → assert `label == CASCADE`, `top_errors[0] == "ImportError"`.
- Fixture: ENV failure (ModuleNotFoundError before any test runs) → assert `label == ENV`.
- Assert isolation command builder produces correct template for each known runner.

**Escalation tests** — at `VerificationLoop` seam:
- Inject fake `FailureDiagnostic`; mock `InterventionGateway`.
- Assert diagnostic emitted at `bug_escalation_at` attempt.
- Assert always emitted when circuit breaker trips.
- Assert `bug_escalation_at == 0` suppresses escalation.

**StatusPublisher tests** — `tests/unit/adapters/`:
- Write a `STEP_FINISHED` event; assert `.agent/status.json` contains expected JSON fields.
- Assert atomic write: no partial file on simulated write failure.

**Prior art:** `tests/unit/adapters/test_command_runner.py`, `tests/unit/application/test_verification_loop.py`, `tests/unit/domain/` for pure functions, `tests/unit/adapters/test_yaml_config_loader.py` for config additions.

## Out of Scope

- Rich TUI panel rendering (deferred to a TUI sprint; `status.json` is the foundation).
- Discord adapter implementation for escalation messages (graceful no-op stub only).
- Automatic test skipping (`--ignore` or `-k not <flaky>`) to unblock forward progress.
- FLAKY detection across multiple runs (single-run heuristics only).
- Bisection or historical failure tracking.

## Further Notes

- `silence_window_seconds` guards the *verification subprocess*, not the Worker. It is distinct from `WorkerSupervisor`'s stall timeout which guards the Worker session. Both should be documented clearly in `config.example.yaml` comments to prevent confusion.
- The `/diagnosing-bugs` skill is extended — not replaced — with a stuck-test-suite section. The section is runner-agnostic by design; the agent deduces runner-specific invocations from project context rather than following a command lookup table.
- `AGENTS.md` receives two minimal pointer additions per the `writing-for-agents` discipline: the skill body carries all detail.
