---
name: smoke-fail
description: "Create a regression ticket from a failed smoke scenario across Ticket Runner, issue trackers, or local scratch files, then initiate diagnosis."
disable-model-invocation: true
---

# Smoke Fail Recovery

Triage failed smoke scenarios and generate reproducible regression tickets across any project or tracking system, ensuring human verification scenarios persist through fixes.

## When to use

Run `/smoke-fail` whenever a manual check, batch smoke review, PR verification, or ad-hoc smoke test fails.

---

## Step 1: Detect destination tracker and workspace context

Inspect the workspace to determine the primary ticket destination, then confirm with the operator:

1. **Ticket Runner directory queue**: detected when `docs/tickets/` exists or `AGENTS.md` defines Ticket Runner architecture.
   - Target path: `docs/tickets/<spec-slug>/T<NNN>-smoke-regression-<scenario-slug>.md`
   - Identifier: dynamically inspect `docs/tickets/` across all spec subdirectories (active and `completed/`) to determine the highest existing `T<NNN>` and increment by 1.
2. **Issue tracker (GitHub, Linear)**: detected when `.github/` exists or git remote points to a hosted repository and tracking CLI (`gh`) is present.
   - Command: `gh issue create` with labels `bug`, `regression`, `ready-for-agent`.
3. **Local scratch files**: fallback or lightweight mode.
   - Target path: `.scratch/<feature-slug>/issues/<NN>-smoke-regression-<scenario-slug>.md`

Prompt the operator to confirm the detected destination or select an alternative before drafting.

**Completion criterion**: Destination tracker confirmed and target directory or tracker access validated.

---

## Step 2: Ingest the failed scenario details

Extract failure information using smart intake with manual fallback:

1. **Inspect durable smoke logs**:
   - Check `.agent/smoke_log_<spec-slug>.md` if present.
   - Match the scenario by originating ticket ID or scenario title.
   - Extract `Setup`, `Steps`, and `Expected` verbatim from the log entry.
   - Ask the operator for the `Observed` behavior: terminal error, stack trace, unexpected output, or UI divergence.
2. **Interactive intake (when no smoke log exists)**:
   - Ask the operator for:
     - **Originating context**: ticket ID, PR number, commit SHA, or feature area.
     - **Scenario title**: concise descriptive name.
     - **Setup**: synthetic configuration, environment variables, or fixtures required.
     - **Steps**: sequence of human actions executed.
     - **Observed**: actual behavior observed.
     - **Expected**: desired behavior expected from the requirement.

**Completion criterion**: Originating context, scenario name, setup, steps, observed outcome, and expected outcome are fully captured.

---

## Step 3: Draft the regression ticket

Draft the ticket using the template matching the confirmed destination tracker:

### Destination: Ticket Runner Queue

Adheres strictly to the domain entity parser in `runner.domain.ticket.Ticket.parse`:

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
- Setup: <setup_steps>
- Steps: <test_steps>
- Expected: <expected_output>

### Gotchas
- <Triage insights or quirks noted during failure capture>
</ticket-runner-template>

### Destination: Local Scratch File

<local-ticket-template>
# <NN>: Smoke regression: <Scenario Title>

**Originating Context:** <originating_id_or_feature>

**Observed vs Expected:**
- Observed: <observed_output>
- Expected: <expected_output>

**Jump-start:**
- Files to touch: <files_to_touch>
- Verification command: <verification_command>

**Status:** ready-for-agent

### Acceptance criteria
- [ ] Reproduce failure with automated test
- [ ] Fix root defect
- [ ] Confirm smoke scenario passes

### Smoke Scenarios
**Scenario: <Scenario Title>**
- Setup: <setup_steps>
- Steps: <test_steps>
- Expected: <expected_output>
</local-ticket-template>

### Destination: Issue Tracker (GitHub / Linear)

<issue-template>
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
- Setup: <setup_steps>
- Steps: <test_steps>
- Expected: <expected_output>

## Jump-start
- Files to inspect: <files_to_touch>
- Verification: <verification_command>
</issue-template>

**Completion criterion**: Regression ticket text completely filled out with concrete paths, observed/expected behaviors, and embedded smoke scenario.

---

## Step 4: Confirm and persist

1. Present the draft ticket to the operator for review.
2. Ask: *"Does this accurately capture the failure and reproduction steps?"*
3. Save or publish upon confirmation:
   - For file-based destinations (Ticket Runner or local scratch): write the file to the target path and confirm file creation.
   - For issue trackers: run CLI command (e.g. `gh issue create --title "..." --body "..." --label bug,regression`) and report the created issue URL.

**Completion criterion**: Ticket persisted to disk or published to tracker, and file path or issue URL reported to operator.

---

## Step 5: Transition to diagnosis

Immediately following ticket persistence, prompt the operator to begin diagnosis:

> *"Regression ticket persisted: `<path_or_url>`. Would you like to begin root-cause diagnosis now using `/diagnosing-bugs` to build an isolated red feedback loop?"*

When accepted:
1. Load `/diagnosing-bugs`.
2. Anchor the diagnosis loop on the reproduction steps and observed failure recorded in the regression ticket.
3. Build the tight automated test or harness before modifying implementation code.

**Completion criterion**: Operator transitioned to diagnosis session or session closed upon operator request.
