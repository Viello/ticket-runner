---
name: smoke-fail
description: "Triage a failed smoke scenario and resolve it in the current session: diagnose the root cause, fix it, and land the change as a single squash-or-new commit."
disable-model-invocation: true
---

# Smoke Fail Recovery

Human-in-the-loop skill. Run when a manual smoke scenario fails. Diagnose and fix in the same session, landing the change in a single commit.

Two paths:

- **Squash path** — the latest commit introduced the failing scenario. Amend it: fix folded in, one clean commit.
- **New-commit path** — intervening commits make amend unsafe. Write a regression ticket, fix it, commit normally.

---

## Step 1: Git probe — determine squash or new-commit path

Run `git log --oneline -5`. Check whether the most recent commit references the originating ticket ID, scenario slug, or feature area the failing scenario belongs to.

When squash-eligible, surface the finding:

> *"Latest commit is `<hash> <message>`. Squash the fix into it (amend)?"*

Wait for operator confirmation.

- **Confirmed squash** → go to Step 2 (skip Step 2b tracker detection).
- **Declined or intervening commits present** → proceed to Step 2b (new-commit path).

**Completion criterion**: Path determined and confirmed by operator.

---

## Step 2: Ingest the failed scenario details

Extract failure details from durable sources first, interactive intake as fallback:

1. **Durable smoke log** (`smoke_log_<spec-slug>.md` or equivalent in the repo): locate entry by ticket ID or scenario title. Extract `Setup`, `Steps`, and `Expected` verbatim. Ask the operator for `Observed`.
2. **Originating ticket** (`docs/tickets/<spec-slug>/completed/<T-NNN>-<slug>.md` or equivalent): read the `### Smoke Scenarios` section.
3. **Interactive intake** (when no durable source exists): ask the operator for originating context (ticket ID, PR, SHA, or feature area), scenario title, setup, steps, observed, and expected.

**Completion criterion**: Originating context, scenario title, setup, steps, observed, and expected are fully captured.

---

## Step 2b: Tracker detection *(new-commit path only)*

Detect the primary ticket destination:

1. **Ticket Runner queue** — `docs/tickets/` exists. Target: `docs/tickets/<spec-slug>/T<NNN>-smoke-regression-<scenario-slug>.md`. Determine `<NNN>` by scanning all subdirectories (active and `completed/`) for the highest existing ticket number and incrementing by 1.
2. **Issue tracker (GitHub / Linear)** — `.github/` exists or `gh` CLI is available. Command: `gh issue create --label bug,regression`.
3. **Local scratch** — fallback. Target: `.scratch/<feature-slug>/issues/<NN>-smoke-regression-<scenario-slug>.md`.

Confirm with the operator before drafting.

**Completion criterion**: Destination confirmed and path or tracker access validated.

---

## Step 3: Draft the regression ticket

Use as the working spec for diagnosis. On the squash path this draft is in-session only — not written to disk.

### Ticket Runner / local scratch template

<ticket-runner-template>
# T<NNN> — Smoke regression: <Scenario Title>
Status: pending
Spec: docs/specs/<spec-slug>.md
Blocked by: None

### Requirements
- Fix regression identified during smoke verification of <originating_id>:
  - Observed: <observed_output>
  - Expected: <expected_output>
- Jump-start:
  - Files to touch: <files_to_touch>
  - Seams to work at: <seams_or_modules>
  - Verification: <verification_command>

### Acceptance Criteria
- Smoke scenario "<Scenario Title>" passes verification.
- Automated regression test added covering the failure mode.

### Smoke Scenarios
**Scenario: <Scenario Title>**
- Setup: <setup_steps or "None (runs from repo root)">
- Why: <1-2 sentences in simple plain English: what was broken and why we are verifying this fix>
- Steps: <numbered, conversational, spoon-fed instructions with exact copy-pasteable terminal commands or scripts>
- Expected: <exact success output to look for, and failure cues>

### Gotchas
- <Triage insights or quirks noted during failure capture>
</ticket-runner-template>

### GitHub / Linear template

```
## Originating Context
Regression observed during smoke testing of <originating_id_or_feature>.

## Observed Behavior
<observed_output>

## Expected Behavior
<expected_output>

## Reproduction Steps
1. Setup: <setup_steps>
2. Steps: <test_steps>

## Smoke Scenarios
**Scenario: <Scenario Title>**
- Setup: <setup_steps or "None (runs from repo root)">
- Why: <1-2 sentences in simple plain English: what was broken and why we are verifying this fix>
- Steps: <numbered, conversational, spoon-fed instructions with exact copy-pasteable terminal commands or scripts>
- Expected: <exact success output to look for, and failure cues>

## Jump-start
- Files to inspect: <files_to_touch>
- Verification: <verification_command>
```

**New-commit path only**: present the draft to the operator, confirm accuracy, then persist to disk or publish via `gh issue create`. Report the file path or issue URL before proceeding.

**Completion criterion**: Ticket drafted with concrete paths, observed/expected behaviors, and embedded smoke scenario. (New-commit path: also persisted and confirmed.)

---

## Step 4: Diagnose

Load `/diagnosing-bugs`. Anchor the diagnosis loop on the reproduction steps and observed failure from Step 2. Build a tight, red-capable feedback loop before touching any implementation code.

**Completion criterion**: Feedback loop exists, has gone red at least once on this exact failure.

---

## Step 5: Fix and commit

Apply the fix. Run the feedback loop green. Then commit:

### Squash path

1. Append a new entry to the repo's runtime-lessons log (`docs/tickets/gotchas.md` or equivalent):

   ```
   ### <Scenario Title> — smoke regression (<ISO date>)
   - Problem: <observed failure, one sentence>
   - Fix: <what changed and why>
   - Verification: <command that goes green>
   ```

2. Stage fix code, regression test, and updated gotchas log.

3. Amend the previous commit:
   - Keep the original `<type>(<scope>): <Title>` line unchanged.
   - Append a new imperative bullet to the commit body describing the fix.
   - Update the `Manual verification required:` trailing section — mark the scenario `[fixed in this amend]`.
   - Run `git commit --amend`.

4. Report the amended commit hash and updated message to the operator.

**Completion criterion**: `git log -1` shows one commit with the fix folded in and the amended message includes `[fixed in this amend]`.

---

### New-commit path

1. Move the regression ticket to `completed/` and set `Status: completed` with `Completed: <ISO-8601-UTC>`.

2. Append the same gotchas entry as the squash path.

3. Stage fix code, regression test, relocated ticket file, and updated gotchas log.

4. Commit following repo convention (`<type>(<scope>): <Title>`, bulleted imperative body). Include a `Manual verification required:` trailing section listing the smoke scenario, tagged `[also auto-covered]` where the regression test exercises it end-to-end.

5. Report the commit hash and message to the operator.

**Completion criterion**: Ticket in `completed/`, commit recorded, operator confirmed.

---

## Step 6: Verify smoke scenario

Walk the operator through the `### Smoke Scenarios` using the ELI5 standard. Human eyes required regardless of automated coverage:
1. State **Why we check this** in 1-2 plain sentences.
2. State the **Setup** requirements or confirm clean state.
3. Provide the **Steps** as spoon-fed, numbered instructions with exact copy-pasteable terminal commands or runnable test snippets so the operator never has to write test code.
4. State the exact **Expected** output (what success looks like) and clear failure cues.

Append a passing entry to the smoke log if the repo maintains one.

If the scenario still fails, re-enter Step 4.

**Completion criterion**: Operator confirms the smoke scenario passes.

