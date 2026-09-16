# Spec 04: Signal Protocol, Gatekeeper Verification, and Circuit Breaker

## Problem Statement

Autonomous agents frequently hallucinate successful completion or declare tasks done without verifying edge cases, leading to broken builds when self-reports are trusted. Additionally, relying on unstructured console text for inter-process communication causes fragile parsing and lost state, while unconstrained retry loops can spin indefinitely on impossible tasks.

## Solution

Enforce durable, filesystem-based Signals in `.agent/signals/` and `.agent/questions/` for Worker-to-Runner state notifications. Validate all work through an independent Python Gatekeeper executing configured test and build commands. Supervise Verification Attempts against the configured `verification.max_attempts` budget, feeding diagnostic errors back to the Worker on early failures and halting for human intervention (`[R]etry`, `[S]kip`, `[A]bort`) when the budget is exhausted.

## User Stories

1. As a developer, I want the Worker to notify the Runner that implementation is complete by writing `.agent/signals/{ticket_id}_ready.json`, so that state transitions are durable and not dependent on console parsing.
2. As a developer, I want the Worker to ask clarification questions by writing `.agent/questions/{ticket_id}.json`, so that ambiguous requirements can be resolved before work proceeds.
3. As a developer, I want the Runner to enforce a 10-second grace period for the Worker to exit cleanly after emitting a Signal, terminating the process if it fails to exit on its own.
4. As a developer, I want the Gatekeeper to independently run the configured `build_cmd` and `test_cmd` when a ready Signal is detected, ensuring code passes verification regardless of what the Worker claims.
5. As a developer, I want the Gatekeeper to accept a Ticket only when all verification commands return exit code 0, protecting branch integrity.
6. As a developer, I want the Runner to capture the trailing output (last 100 lines) of failed verification commands and re-invoke the Worker's active session with these diagnostics on failed Verification Attempts before the budget is exhausted, allowing the agent to self-correct.
7. As a developer, I want the Circuit Breaker to trip after `verification.max_attempts` consecutive failed Verification Attempts, pausing the Queue and alerting me at the terminal and via Discord.
8. As a developer, I want the option to issue `[R]etry [hint]` when the Circuit Breaker trips, restoring the full `verification.max_attempts` budget and injecting my optional advice directly into the Worker session.
9. As a developer, I want the option to issue `[S]kip` when the Circuit Breaker trips, confirming the destructive skip before discarding uncommitted edits with `git reset --hard HEAD` and `git clean -fd`, marking the Ticket as skipped, and advancing to the next item.
10. As a developer, I want the option to issue `[A]bort` when the Circuit Breaker trips, cleanly shutting down the Runner process while preserving the working tree for direct debugging on the PC.
11. As a developer, I want the Runner to automatically update question signals with `"status": "answered"` and resume the Worker once an answer is submitted via terminal or Discord.

## Implementation Decisions

- **Signal File Schema (`ready.json`)**:
  Contains `ticket_id`, `status` (`"ready_for_verification"`), `modified_files` (string array), `self_review_notes` (string), `new_gotchas` (string array), optional `scope` (lowercase commit scope token, never a ticket number; absent means the orchestrator default applies), and `timestamp` (ISO-8601).
- **Question File Schema (`question.json`)**:
  Contains `ticket_id`, `question` (string), `type` (`"choice"` | `"text"`), `options` (string array or null), `status` (`"pending"` | `"answered"`), `answer` (string or null), and `created_at` (ISO-8601).
- **Signal Detection & Process Termination**: The Runner watches `.agent/signals/` and `.agent/questions/`. Upon file creation, the Runner monitors the Worker process. If the process does not terminate within 10 seconds, the Runner issues a forceful process termination. The grace clock starts once per Session Run and never resets on repeated polls.
- **Verification Attempt Model**: One Verification Attempt is one full cycle of Worker session execution, Signal validation, and Gatekeeper verification. A malformed ready Signal, a malformed pending question, and worker-phase non-READY statuses (stalled, ceiling, escalated, crash) each consume one attempt, with their diagnostics fed back into the active Worker session as the next resume prompt. The per-Ticket budget is in-memory only and comes from `verification.max_attempts` (default 3). A pending question interrupts the cycle without consuming budget.
- **Single-Use Signal Lifecycle**: A ready Signal is consumed the moment it is parsed and can never trigger a second verification. Answered question Signals are retained for audit; only the ready Signal is deleted on use. Both artifacts are purged from disk when the Ticket starts.
- **Gatekeeper Verification Execution**: Gatekeeper commands (`build_cmd`, `test_cmd` defined in `config.yaml`) are executed sequentially as shell command strings — `cmd.exe /d /s /c` on Windows, `/bin/sh -c` on POSIX (ADR 0016) — each bounded by its own `timeout_seconds` (default 300 seconds). A command passes only on exit code 0; a timed-out command is terminated and treated as a failure. If `build_cmd` is non-empty and fails, `test_cmd` is skipped.
- **Circuit Breaker Threshold**: The budget is `verification.max_attempts` (default 3) failed Verification Attempts before tripping the breaker; it is never hardcoded.
- **Intervention Menu Contract**: `[R]etry [hint]` restores the full `verification.max_attempts` budget and injects the optional hint into the Worker session; `[S]kip` requires one explicit confirmation (empty answer defaults to no) because it executes `git reset --hard HEAD` followed by `git clean -fd` before advancing the Queue; `[A]bort` stops the Runner without touching the working tree, preserving it for direct debugging.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that valid ready signals trigger Gatekeeper commands, that exit code 0 leads to commit actions, that non-zero exit codes trigger diagnostic retries with trailing logs, and that exhausting `verification.max_attempts` trips the Circuit Breaker. Tests do not verify internal command line formatting helpers.
- **Modules Tested**: Signal watcher, question responder, Gatekeeper command runner, and Circuit Breaker state machine.
- **Seams and Test Doubles**: Tests use temporary disk fixtures for `.agent/signals/` and an in-memory `CommandRunner` configured to simulate passing or failing build/test scripts. Behavioral tests inject clocks and scripted intervention fakes instead of sleeping through the 10-second grace or command timeouts, and never spawn live OpenCode.

## Out of Scope

- Automatic modification of `config.yaml` test commands.
- Retrying flaky tests automatically without Worker awareness.
- Executing Gatekeeper commands in external Docker containers (all runs are local subprocesses).

## Further Notes

- By strictly decoupling Worker implementation from Gatekeeper verification, the architecture prevents hallucinated test passes from ever reaching the git commit history.
