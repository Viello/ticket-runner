---
name: diagnosing-bugs-ticket-runner
description: "Autonomous worker diagnosis skill for Ticket Runner queues: build tight feedback loops, execute the Stuck-Test-Suite Protocol (HANG, CASCADE, ENV, FLAKY), withhold ready signals on stuck suites, and escalate via question signals."
disable-model-invocation: true
---

# Diagnosing Bugs Ticket Runner

Autonomous Worker debugging discipline for Ticket Runner queues. Orchestrated by `ticket_runner.py` via an AI coding agent backend (OpenCode, Antigravity CLI).

When debugging failures during implementation, read `CONTEXT.md` (if it exists) to ground your mental model of the relevant modules, and check `docs/adr/` for binding architectural decisions in the area you are touching.

## Redact Secrets

Redact every secret before logging or reporting: write `<REDACTED>` in its place. Build loops against environment variables so credentials remain isolated. Quote only the specific lines carrying the failure signal.

## Phase 1: Build a Feedback Loop

If you have a **tight** pass/fail signal for the bug (one that goes red on *this* specific failure), you will find the cause. If you do not have one, no amount of guessing will solve it.

### Ways to construct one:
1. **Failing targeted test** at the closest seam: `py -3 -m pytest tests/unit/<area>/test_<file>.py::<test_func> -q`.
2. **Deterministic CLI script or command** with fixture input, diffing output against expected state.
3. **Replay a trace or payload** through the code path in isolation.
4. **Throwaway scratch harness** in `<appDataDir>/brain/<conversation-id>/scratch/` exercising the failure path with minimal dependencies.

### When you genuinely cannot build a loop:
If a reproduction loop cannot be constructed due to missing environment access or external dependencies, do NOT guess. Stop and escalate to the human operator via a question signal (see Escalation via Question Signals below).

### Completion criterion:
A tight, red-capable command that is:
- **Red-capable**: drives the actual failing path and catches the specific symptom.
- **Deterministic**: produces the same verdict on every run.
- **Fast**: runs in seconds, not minutes.
- **Agent-runnable**: runs unattended via your command execution tool.

## Phase 2: Reproduce + Minimise

Run the loop. Watch it fail.
- Confirm the loop reproduces the exact failure under investigation.
- Shrink the reproduction to the smallest input, parameters, or test scenario that still fails.
- Cut away unrelated parts one at a time until every remaining element is load-bearing.

## Phase 3: Hypothesise

Generate 3–5 ranked, falsifiable hypotheses before making changes:
> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

## Phase 4: Instrument

Probe hypotheses systematically:
- Change one variable at a time.
- Use targeted debug logging tagged with a unique prefix (e.g. `[DEBUG-trace]`).
- Clean up all tagged debug logging before declaring completion.

## Phase 5: Fix + Regression Test

1. Turn the minimised reproduction into a failing regression test at the agreed seam.
2. Verify the regression test fails.
3. Apply the minimal fix to make it pass.
4. Re-verify that targeted tests and the broader suite pass.

## Phase 6: Cleanup

Before proceeding:
- Confirm the reproduction command passes cleanly.
- Ensure all temporary debug instrumentation is removed.
- State the verified root cause in your self-review notes.

---

## Stuck-Test-Suite Protocol

Enter this protocol when the test suite itself is the obstacle — the suite hangs without printing a result, or a cascade of failures drowns the signal.

### Phase A: Observe
1. Is the test process still running or did it exit?
2. Did output stop after a specific test, module import, or immediately at start?
3. If running and silent for 30+ seconds, terminate it and capture the exact last line emitted.

### Phase B: Classify
Classify the failure into one of four labels:
- **`HANG`**: The process was running but emitted no output for an extended period. Typically caused by blocking I/O, waiting on stdin/TTY, unawaited asyncio coroutines, or thread deadlocks.
- **`CASCADE`**: Many tests failed (5+) with the same error class, module, or import. One broken root dependency or import is killing downstream tests.
- **`ENV`**: Failure occurs before tests run (missing package, incompatible python version, bad path).
- **`FLAKY`**: Non-zero exit with no obvious pattern or hanging.

If unsure between `HANG` and `CASCADE`: `HANG` takes priority.

### Phase C: Isolate
Run the first failing test alone using single-test selection:
`py -3 -m pytest tests/<path>/test_file.py::test_name -q`
- If the isolated test **fails**: You have a minimal repro. Proceed to Phase 1.
- If the isolated test **passes**: The failure depends on test ordering or shared state (leaking fixtures, un-reset singletons).
- If the isolated test **hangs**: The hang is reproduced in isolation. Instrument the test to pinpoint the blocking line.

### Phase D: Escalate via Question Signals
If isolation does not produce a reproducible single-failure after 1–2 attempts, or if a feedback loop cannot be constructed:
1. **Stop immediately**: Do not burn verification attempts on the full suite.
2. Formulate your findings:
   - Classification (`HANG`, `CASCADE`, `ENV`, or `FLAKY`) and supporting evidence.
   - The last line of output before silence (for `HANG`) or the top repeating error (for `CASCADE`).
   - The outcome of isolated single-test runs.
3. Emit a durable question signal by writing `.agent/questions/<ticket_id>.json` following the schema in the task prompt's `Question Signal Protocol` section.
4. The Gatekeeper will transition to `WAITING_FOR_USER` and prompt the human operator via Discord or Terminal for direction.

## Critical Invariants

- **Never emit a ready signal while the test suite is still in a stuck state** or failing. Writing `.agent/signals/<ticket_id>_ready.json` while tests are red consumes verification attempts and risks tripping the Circuit Breaker.
- You must **NEVER** run `git commit` or relocate tickets.
- Defer all signal JSON formats to the task prompt's `Ready Signal Protocol` and `Question Signal Protocol` sections.
