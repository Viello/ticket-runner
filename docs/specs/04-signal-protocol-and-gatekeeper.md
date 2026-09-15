# Spec 04: Signal Protocol, Gatekeeper Verification, and Circuit Breaker

## Problem Statement

Autonomous agents frequently hallucinate successful completion or declare tasks done without verifying edge cases, leading to broken builds when self-reports are trusted. Additionally, relying on unstructured console text for inter-process communication causes fragile parsing and lost state, while unconstrained retry loops can spin indefinitely on impossible tasks.

## Solution

Enforce durable, filesystem-based Signals in `.agent/signals/` and `.agent/questions/` for Worker-to-Runner state notifications. Validate all work through an independent Python Gatekeeper executing configured test and build commands. Supervise verification attempts with a 3-attempt Circuit Breaker that feeds diagnostic errors back to the Worker on early failures and halts for human intervention (`[R]etry`, `[S]kip`, `[A]bort`) when limits are breached.

## User Stories

1. As a developer, I want the Worker to notify the Runner that implementation is complete by writing `.agent/signals/{ticket_id}_ready.json`, so that state transitions are durable and not dependent on console parsing.
2. As a developer, I want the Worker to ask clarification questions by writing `.agent/questions/{ticket_id}.json`, so that ambiguous requirements can be resolved before work proceeds.
3. As a developer, I want the Runner to enforce a 5-second grace period for the Worker to exit cleanly after emitting a Signal, terminating the process if it fails to exit on its own.
4. As a developer, I want the Gatekeeper to independently run the configured `build_cmd` and `test_cmd` when a ready Signal is detected, ensuring code passes verification regardless of what the Worker claims.
5. As a developer, I want the Gatekeeper to accept a Ticket only when all verification commands return exit code 0, protecting branch integrity.
6. As a developer, I want the Runner to capture the trailing output (last 100 lines) of failed verification commands and re-invoke the Worker's active session with these diagnostics on Attempts 1 and 2, allowing the agent to self-correct.
7. As a developer, I want the Circuit Breaker to trip after 3 consecutive Gatekeeper verification failures, pausing the Queue and alerting me at the terminal and via Discord.
8. As a developer, I want the option to issue `[R]etry [hint]` when the Circuit Breaker trips, resetting the attempt counter and injecting my advice directly into the Worker session.
9. As a developer, I want the option to issue `[S]kip` when the Circuit Breaker trips, discarding uncommitted edits with `git reset --hard HEAD` and `git clean -fd`, marking the Ticket as skipped, and advancing to the next item.
10. As a developer, I want the option to issue `[A]bort` when the Circuit Breaker trips, cleanly shutting down the Runner process for direct debugging on the PC.
11. As a developer, I want the Runner to automatically update question signals with `"status": "answered"` and resume the Worker once an answer is submitted via terminal or Discord.

## Implementation Decisions

- **Signal File Schema (`ready.json`)**:
  Contains `ticket_id`, `status` (`"ready_for_verification"`), `modified_files` (string array), `self_review_notes` (string), `new_gotchas` (string array), and `timestamp` (ISO-8601).
- **Question File Schema (`question.json`)**:
  Contains `ticket_id`, `question` (string), `type` (`"choice"` | `"text"`), `options` (string array or null), `status` (`"pending"` | `"answered"`), `answer` (string or null), and `created_at` (ISO-8601).
- **Signal Detection & Process Termination**: The Runner watches `.agent/signals/` and `.agent/questions/`. Upon file creation, the Runner monitors the Worker process. If the process does not terminate within 5 seconds, the Runner issues a forceful process termination.
- **Gatekeeper Verification Execution**: Gatekeeper commands (`build_cmd`, `test_cmd` defined in `config.yaml`) are executed sequentially with a configurable timeout (default 300 seconds). If `build_cmd` is non-empty and fails, `test_cmd` is skipped.
- **Circuit Breaker Threshold**: Maximum verification attempts is hardcoded to 3 before tripping the breaker.
- **Skip Reset Contract**: The `[S]kip` action executes `git reset --hard HEAD` followed by `git clean -fd` to remove all uncommitted modifications and untracked artifacts before advancing the Queue.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that valid ready signals trigger Gatekeeper commands, that exit code 0 leads to commit actions, that non-zero exit codes trigger diagnostic retries with trailing logs, and that 3 consecutive failures trip the Circuit Breaker. Tests do not verify internal command line formatting helpers.
- **Modules Tested**: Signal watcher, question responder, Gatekeeper command runner, and Circuit Breaker state machine.
- **Seams and Test Doubles**: Tests use temporary disk fixtures for `.agent/signals/` and an in-memory `CommandRunner` configured to simulate passing or failing build/test scripts.

## Out of Scope

- Automatic modification of `config.yaml` test commands.
- Retrying flaky tests automatically without Worker awareness.
- Executing Gatekeeper commands in external Docker containers (all runs are local subprocesses).

## Further Notes

- By strictly decoupling Worker implementation from Gatekeeper verification, the architecture prevents hallucinated test passes from ever reaching the git commit history.
