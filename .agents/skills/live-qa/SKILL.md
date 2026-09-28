---
name: live-qa
description: "Human-driven live verification: the human drives the running app through scenarios while the agent records verdicts as durable evidence."
disable-model-invocation: true
---

# Live QA

The human is the sensor. Run after an implementation lands, while the real app is up: the human drives each scenario by hand; the agent probes, transcribes verdicts, and appends them to a durable log. The verdicts themselves are the evidence — the agent records, never infers a pass.

## Step 1: Pin the live target

Resolve a probe target (URL, port, or CLI entry point) in this order:

1. `.agent/live-qa.json` field `probe` (a confirmed target from a past session).
2. Sniff the environment: `package.json` scripts, README quickstart, `docker-compose.yml`, `[project.scripts]` in `pyproject.toml`, the ports named in the current diff. Propose the best candidate.
3. Ask the human.

Probe it: HTTP HEAD, TCP connect, or `--help` exit code. If it answers, state the target and begin. If it refuses, report "start the app, then run `/live-qa` again" and stop — launching processes belongs to the human.

Once a working target is confirmed, cache it in `.agent/live-qa.json`:

```json
{ "probe": "http://localhost:3000/health", "label": "<app name>", "notify_cmd": "<optional one-shot message command>" }
```

**Completion criterion**: a probe returns live, or the session ends with a start-the-app report.

## Step 2: Source the scenarios

Take the first available source:

1. **Checklist artifact** in the repo: the active or just-completed ticket's `### Smoke Scenarios` (`docs/tickets/**`), a PR body, or an acceptance-criteria section. Adopt its scenarios as live steps.
2. **Diff draft**: read the uncommitted diff (or the newest commit when clean) and draft scenarios in `Setup` / `Steps` / `Expected` form — one per user-visible branch the change touches, at least the happy path and one adjacent breakage.

Present the list for the human to edit: add, drop, reword. Drafted scenarios run only after the human signs the list.

**Completion criterion**: every scenario on the list carries a human-edited approval, and each has Setup, Steps, and Expected.

## Step 3: Drive the loop

Per scenario, one at a time — verdicts never batch:

1. State the scenario's Why in one or two plain sentences, then the Setup, Steps, and Expected verbatim.
2. The human drives the live app. The agent waits, silent.
3. Collect the verdict: `verified`, `failed` plus the human's `Observed:` words verbatim, or `skipped` plus the human's reason.
4. Append the entry to the log (Step 4 format) immediately.
5. If `.agent/live-qa.json` carries `notify_cmd`, run it with the one-line verdict message so the session streams to the remote channel. When the command is missing or fails, continue in terminal only.

**Completion criterion**: every scenario from Step 2 has exactly one verdict entry in the log.

## Step 4: Record the session

Append-only log at `.agent/live-qa_log_<slug>.md`, created with a `# Live QA Log: <slug>` header on first use. `<slug>`: the ticket ID when the scenarios came from a ticket, else the current branch name sanitized to lowercase alphanumeric and hyphens.

```markdown
## <ISO-8601 date> — <label> live session
### <scenario title> — [verified|failed|skipped] <ISO-8601 timestamp>
- Observed: <human's exact words>   <!-- failures and skips only -->
```

Close the session block with one summary line: `N verified, M failed, K skipped.`

**Completion criterion**: the log on disk replays every verdict spoken in Step 3, and the summary line adds up.

## Step 5: Hand off failures

For each `[failed]` entry, show the scenario and its Observed words, then offer to load `/diagnosing-bugs` in this session — the diagnosis loop owns root cause, fix, and re-verification. After a fix, re-run `/live-qa` on just the failed scenarios; the log takes fresh entries. A failure the human defers is recorded as-is and left standing.

**Completion criterion**: each failure is either in a `/diagnosing-bugs` handoff or explicitly deferred by the human.

## Guardrails

- Stage, commit, push, and deploy stay the human's call — the session's only writes are the log and `live-qa.json` cache.
- A verdict speaks only through the human's mouth; the agent's job is transcript fidelity.
- The session requires the human present at the machine driving the real app; a verdict relayed second-hand is a skip.
