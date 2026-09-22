---
name: diagnosing-bugs
description: Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this", or reports something broken/throwing/failing/slow.
---

# Diagnosing Bugs

A discipline for hard bugs. Skip phases only when explicitly justified.

When exploring the codebase, read `CONTEXT.md` (if it exists) to get a clear mental model of the relevant modules, and check ADRs in the area you're touching.

## Redact

This skill has you show commands, outputs and captured artifacts. **Redact every secret first**: write `<REDACTED>` in its place. Build loops against env vars, so the credential stays in the environment rather than in what you show. Captured artifacts carry auth headers: quote only the lines that carry the signal.

If the redacted output is not enough to diagnose the bug, say so and ask the user.

## Phase 1: Build a feedback loop

**This is the skill.** Everything else is mechanical. If you have a **tight** pass/fail signal for the bug (one that goes red on _this_ bug), you will find the cause; bisection, hypothesis-testing, and instrumentation all just consume it. If you don't have one, no amount of staring at code will save you.

Spend disproportionate effort here. **Be aggressive. Be creative. Refuse to give up.**

### Ways to construct one, in roughly this order

1. **Failing test** at whatever seam reaches the bug: unit, integration, e2e.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture input, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright / Puppeteer) that drives the UI and asserts on DOM/console/network.
5. **Replay a captured trace.** Save a real network request / payload / event log to disk; replay it through the code path in isolation.
6. **Throwaway harness.** Spin up a minimal subset of the system (one service, mocked deps) that exercises the bug code path with a single function call.
7. **Property / fuzz loop.** If the bug is "sometimes wrong output", run 1000 random inputs and look for the failure mode.
8. **Bisection harness.** If the bug appeared between two known states (commit, dataset, version), automate "boot at state X, check, repeat" so you can `git bisect run` it.
9. **Differential loop.** Run the same input through old-version vs new-version (or two configs) and diff outputs.
10. **HITL bash script.** Last resort. If a human must click, drive _them_ with `scripts/hitl-loop.template.sh` so the loop is still structured. Captured output feeds back to you.

Build the right feedback loop, and the bug is 90% fixed.

### Tighten the loop

Treat the loop as a product. Once you have _a_ loop, **tighten** it:

- Can I make it faster? (Cache setup, skip unrelated init, narrow the test scope.)
- Can I make the signal sharper? (Assert on the specific symptom, not "didn't crash".)
- Can I make it more deterministic? (Pin time, seed RNG, isolate filesystem, freeze network.)

A 30-second flaky loop is barely better than no loop; a 2-second deterministic one is tight, a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the trigger 100×, parallelise, add stress, narrow timing windows, inject sleeps. A 50%-flake bug is debuggable; 1% is not, so keep raising the rate until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a) access to whatever environment reproduces it, (b) a redacted captured artifact (HAR file, log dump, core dump, screen recording with timestamps), or (c) permission to add temporary production instrumentation. Do **not** proceed to hypothesise without a loop.

### Completion criterion: a tight loop that goes red

Phase 1 is done when the loop is **tight** and **red-capable**: you can name **one command** (a script path, a test invocation, a curl) that you have **already run at least once** (show the invocation and its output, redacted), and that is:

- [ ] **Red-capable**: it drives the actual bug code path and asserts the **user's exact symptom**, so it can go red on this bug and green once fixed. Not "runs without erroring"; it must be able to _catch this specific bug_.
- [ ] **Deterministic**: same verdict every run (flaky bugs: a pinned, high reproduction rate, per above).
- [ ] **Fast**: seconds, not minutes.
- [ ] **Agent-runnable**: you can run it unattended; a human in the loop only via `scripts/hitl-loop.template.sh`.

If you catch yourself reading code to build a theory before this command exists, **stop: jumping straight to a hypothesis is the exact failure this skill prevents.** No red-capable command, no Phase 2.

## Phase 2: Reproduce + minimise

Run the loop. Watch it go red as the bug appears.

Confirm:

- [ ] The loop produces the failure mode the **user** described, not a different failure that happens to be nearby. Wrong bug = wrong fix.
- [ ] The failure is reproducible across multiple runs (or, for non-deterministic bugs, reproducible at a high enough rate to debug against).
- [ ] You have captured the exact symptom (error message, wrong output, slow timing) so later phases can verify the fix actually addresses it.

### Minimise

Once it's red, shrink the repro to the **smallest scenario that still goes red**. Cut inputs, callers, config, data, and steps **one at a time**, re-running the loop after each cut, and keep only what's load-bearing for the failure.

Why bother: a minimal repro shrinks the hypothesis space in Phase 3 (fewer moving parts left to suspect) and becomes the clean regression test in Phase 5.

Done when **every remaining element is load-bearing**: removing any one of them makes the loop go green.

Do not proceed until you have reproduced **and** minimised.

## Phase 3: Hypothesise

Generate **3–5 ranked hypotheses** before testing any of them. Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis must be **falsifiable**: state the prediction it makes.

> Format: "If <X> is the cause, then <changing Y> will make the bug disappear / <changing Z> will make it worse."

If you cannot state the prediction, the hypothesis is a vibe: discard or sharpen it.

**Show the ranked list to the user before testing.** They often have domain knowledge that re-ranks instantly ("we just deployed a change to #3"), or know hypotheses they've already ruled out. Cheap checkpoint, big time saver. Don't block on it; proceed with your ranking if the user is AFK.

## Phase 4: Instrument

Each probe must map to a specific prediction from Phase 3. **Change one variable at a time.**

Tool preference:

1. **Debugger / REPL inspection** if the env supports it. One breakpoint beats ten logs.
2. **Targeted logs** at the boundaries that distinguish hypotheses.
3. Never "log everything and grep".

**Tag every debug log** with a unique prefix, e.g. `[DEBUG-a4f2]`. Cleanup at the end becomes a single grep. Untagged logs survive; tagged logs die.

**Perf branch.** For performance regressions, logs are usually wrong. Instead: establish a baseline measurement (timing harness, `performance.now()`, profiler, query plan), then bisect. Measure first, fix second.

## Phase 5: Fix + regression test

Write the regression test **before the fix**, but only if there is a **correct seam** for it.

A correct seam is one where the test exercises the **real bug pattern** as it occurs at the call site. If the only available seam is too shallow (single-caller test when the bug needs multiple callers, unit test that can't replicate the chain that triggered the bug), a regression test there gives false confidence.

**If no correct seam exists, that itself is the finding.** Note it. The codebase architecture is preventing the bug from being locked down. Flag this for the next phase.

If a correct seam exists:

1. Turn the minimised repro into a failing test at that seam.
2. Watch it fail.
3. Apply the fix.
4. Watch it pass.
5. Re-run the Phase 1 feedback loop against the original (un-minimised) scenario.

## Phase 6: Cleanup

Required before declaring done:

- [ ] Original repro no longer reproduces (re-run the Phase 1 loop)
- [ ] Regression test passes (or absence of seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (`grep` the prefix)
- [ ] Throwaway prototypes deleted (or moved to a clearly-marked debug location)
- [ ] The hypothesis that turned out correct is stated in the commit / PR message, so the next debugger learns

---

## Stuck-Test-Suite Protocol

*Enter this protocol when the test suite itself is the obstacle — not the bug inside it. Symptoms: the suite hangs without printing a result, or a cascade of 10+ failures drowns any signal. The regular phases assume a feedback loop exists; this protocol builds one when the loop is broken.*

### Phase A: Observe

Before doing anything else, describe what you are actually seeing:

- Is the test process **still running** or did it exit?
- Is there **any output at all**, or did it go silent partway through?
- Did output stop after a specific test name, a specific module import, or immediately at start?

You cannot classify the failure until you can answer these. If the process is still running and silent, it is almost certainly blocked — on I/O, a lock, an event, or an infinite loop. Do not wait for it: kill it, note the last line emitted, and proceed.

Capture the exact last line(s) of output before silence or exit. That line is your first clue.

### Phase B: Classify

Assign one of four labels based on what you observed. The label determines what you fix first:

- **HANG** — the process was running but emitted no output for an extended period (30+ seconds for a fast machine, 60–120 s for a slow one). Root cause is almost always blocking I/O: a test waiting on stdin, a TTY interaction, an asyncio event that never fires, or a thread deadlock. The fix is in the code that blocks, not in the test harness.

- **CASCADE** — many tests failed (typically 5 or more) and the same error class, module, or import appears in most of them. One broken thing is killing everything downstream. The fix is the root import or initialization, not each individual test.

- **ENV** — the failure happens before a single test runs: a missing module, a wrong working directory, a missing binary, an incompatible dependency version. The suite is fine; the environment is wrong. Fix the environment, then re-run.

- **FLAKY** — exit is non-zero but nothing above fits: a small number of failures, no obvious pattern, no silence. Could be timing, ordering, or external state. Proceed to Phase C to isolate before guessing.

If you are unsure between HANG and CASCADE: HANG takes priority. A suite can produce many failures *before* going silent. Classify as HANG if there was a silence period, even if failures preceded it.

### Phase C: Isolate

The goal of isolation is a single-failure trace — the smallest invocation that reproduces the problem cleanly. Once you have it, the regular phases (Phase 1 onwards) become applicable again.

Run the **first failing test alone**. Use whatever invocation your test runner supports for single-test selection. Do not run the full suite again yet.

- If the isolated run **also fails**: you have a clean, minimal repro. The failure is in that test or what it imports. Now go to Phase 1 and build a tight loop around this single test.
- If the isolated run **passes**: the failure depends on test-ordering or shared state. The root cause is a side effect leaking between tests. Look for shared global state, module-level initialization, or database fixtures that are not reset between tests.
- If the isolated run **also hangs**: the HANG is reproducible in isolation. That specific test is blocking. Instrument it: add a print before every I/O call, every lock acquire, every `await`. The last print before silence is the site.

For a CASCADE, after running the first failing test in isolation, also check whether the top-repeating error class appears on its own (e.g. import the affected module directly in a REPL or scratch script). A module-level `ImportError` will reproduce instantly without running any test.

For an ENV failure, check the environment directly: verify the missing dependency is installed, the working directory is correct, and the binary is on PATH.

### Phase D: Escalate

If isolation did not produce a reproducible single-failure in one or two attempts, stop and escalate rather than guessing:

1. **State your classification** (HANG / CASCADE / ENV / FLAKY) and what evidence led to it.
2. **Report the last line before silence** (for HANG) or the **top repeating error** (for CASCADE).
3. **Report what isolation produced**: did the first test pass alone? Did it also hang?
4. **Ask**: should we apply the `/diagnosing-bugs` skill from Phase 1 against this specific isolated case? If yes, re-enter the skill with the isolated single-test loop as the feedback loop.

Do not burn more retries on the full suite until the isolated case is understood. A fresh attempt against an undiagnosed suite will produce identical output and identical failure.

If you are the orchestrator (Ticket Runner), emit a ready signal only after the isolated case passes or the escalation is documented. Never emit a ready signal while the test suite is still in a stuck state.
