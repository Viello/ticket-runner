# T069 — Smoke Scenarios surfacing in Gatekeeper
Status: pending

### Requirements
- Add an optional `manual_verification` field to `ReadySignal`: a tuple of dicts, each with keys `name`, `setup`, `steps`, `expected`. Defaults to an empty tuple when absent from the JSON payload (backward-compatible — existing ready signals without the field parse without error).
- In `VerificationLoop.run()`, after `report.passed` is confirmed and before returning `VerificationLoopResult.passed(...)`:
  1. Read `ready_signal.manual_verification` (may be empty).
  2. If non-empty, append a `"Manual verification required:"` section to the commit body — one `"- <name>"` bullet per scenario — by passing the extra lines through the `changes` list accepted by `GitOperations.commit_ticket()`. Call `commit_ticket()` only if `GitOperations` is available via the `VerificationLoop`; otherwise log a warning and skip the commit-body injection (do not block the pass).
  3. After the commit (or if no GitOperations), print the full human-action checklist to the terminal via the existing `self._notify` / printer channel — Setup, Steps, and Expected preserved verbatim per scenario.
  4. Send a summary to Discord via the Discord adapter stub: one line per scenario name in the format `✅ Gatekeeper passed — manual verification required:\n• <name1>\n• <name2>`. If Discord adapter is absent, call a no-op stub and log a warning — never raise.
- If `manual_verification` is empty, emit a single terminal line: `All Smoke Scenarios covered by automated tests — no manual steps required.` No Discord send in this case.

Jump-start:
- `ReadySignal` dataclass: `runner/domain/signal.py` lines 225–280 — add `manual_verification: tuple[dict, ...]  = ()` field; update `ReadySignal.parse()` to read `payload.get("manual_verification", [])` and coerce to a tuple of dicts (validate each entry is a dict with string values, raise `SignalFormatError` on malformed entries).
- `VerificationLoop.run()`: `runner/application/gatekeeper.py` lines 729–737 — the `if report.passed:` branch is the insertion point; `InterventionGateway` is already injected at `__init__` (line 540); `self._notify` is the existing printer/notify channel.
- Commit body injection: `GitOperations.commit_ticket()` at `runner/application/git_operations.py` lines 135–200 — the `changes` list becomes the bulleted body; append the `"Manual verification required:"` header and scenario name bullets as extra entries in `changes`. `GitOperations` is not currently injected into `VerificationLoop` — check `ticket_processor.py` (`GatekeeperTicketProcessor`) for where `VerificationLoop` is constructed and how `GitOperations` is threaded through; add it as an optional injectable parameter to `VerificationLoop.__init__` following the existing nullable-dependency pattern.
- Discord: find or create `DiscordAdapter` stub in `runner/adapters/discord/` (same no-op stub pattern established in T066); inject via `VerificationLoop.__init__` alongside `intervention_gateway`.
- Tests: `tests/unit/application/test_verification_loop.py` — add a `ReadySignal` fixture with a populated `manual_verification` list; assert terminal output contains full scenario detail; assert Discord stub receives names-only summary; assert commit body contains scenario names; assert empty `manual_verification` emits the "all covered" line and no Discord send.
- Verify with: `python -m pytest tests/unit/application/test_verification_loop.py -x`

### Acceptance Criteria
- A `ReadySignal` JSON payload without `manual_verification` parses successfully with `manual_verification == ()`.
- A `ReadySignal` with a malformed `manual_verification` entry (non-dict or missing string values) raises `SignalFormatError`.
- When `manual_verification` contains two scenarios, the terminal output contains their full Setup / Steps / Expected blocks verbatim.
- When `manual_verification` contains two scenarios, the Discord stub receives a message containing both scenario names and no Setup/Steps/Expected detail.
- When `manual_verification` contains two scenarios, the commit body includes a `"Manual verification required:"` section with one bullet per scenario name.
- When `manual_verification` is empty, terminal emits `All Smoke Scenarios covered by automated tests — no manual steps required.` and Discord stub is not called.
- A missing or stub Discord adapter never raises.
- `python -m pytest tests/unit/application/test_verification_loop.py -x` exits 0.

### Smoke Scenarios
**Scenario: full human-action checklist appears on Gatekeeper pass**
- Setup: Arrange a ready signal JSON file for an active ticket containing a `manual_verification` array with two entries (each having `name`, `setup`, `steps`, `expected`). Set `bug_escalation_at: 1` and ensure the test suite passes on first attempt.
- Steps:
  1. Run the Runner against the ticket until the Gatekeeper passes.
  2. Observe terminal output after "Gatekeeper passed".
- Expected: The terminal displays each scenario's name, Setup, Steps, and Expected content verbatim. No detail is truncated. The commit message (`git log -1`) contains a `Manual verification required:` section with one bullet per scenario name.

**Scenario: Discord stub receives names-only summary**
- Setup: Same as above. Inspect the Discord adapter stub (or a log line if the stub logs its calls).
- Steps:
  1. Run the Runner through a Gatekeeper pass with a non-empty `manual_verification` payload.
  2. Check stub log or in-memory call record.
- Expected: The Discord message contains scenario names only (no Setup/Steps/Expected). Does not raise even when the Discord adapter is a no-op stub.

**Scenario: no checklist output when all scenarios are auto-covered**
- Setup: Arrange a ready signal with `manual_verification: []`. Ensure the test suite passes.
- Steps:
  1. Run the Runner through a Gatekeeper pass.
  2. Observe terminal output.
- Expected: Terminal emits `All Smoke Scenarios covered by automated tests — no manual steps required.` No Discord send occurs.

### Gotchas
- `ReadySignal` is a `frozen=True` dataclass with strict `__post_init__` validation. Add `manual_verification` after the existing optional `scope` field and give it `= ()` as its default so it never needs `object.__setattr__` coercion unless the payload supplies a non-empty value.
- `GitOperations` is not currently injected into `VerificationLoop`. Introduce it as `git_operations: GitOperations | None = None` in `__init__` and guard every call with `if self._git_operations is not None` — existing tests that don't supply it must not break.
- Discord send is fire-and-forget and must never propagate exceptions. Wrap in `try/except Exception: logger.warning(...)` identical to the pattern in T066.
- Scenario names in the commit body must be sanitised by `commit_ticket()`'s existing ticket-number-stripping regex — do not bypass it. Verify that a scenario name containing `"T069"` survives the strip (the regex targets `T\d{3,4}` prefixes in the title, not arbitrary body text; confirm the body is passed through `formatted_changes` which applies the same strip).
