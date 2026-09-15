# Spec 01: Doctor Pre-Flight and Git Operations

## Problem Statement

Autonomous execution requires strict environment prerequisites and an inviolable isolation layer. If the orchestrator starts in a dirty git working tree, without required CLI tools installed, or without safeguards against remote git pushes, an autonomous coding process can destroy uncommitted human work, push experimental code to remote repositories, or crash mid-ticket due to missing dependencies.

## Solution

Provide a pre-flight Doctor verification routine that validates the developer environment, CLI binaries, queue existence, configuration validity, and Discord connectivity before any work begins. Provide dedicated Git operations that enforce branch isolation on a dedicated branch (`agent/ticket-runner`), non-destructively install an unbypassable pre-push hook guardrail, and author conventional commits upon successful ticket completion.

## User Stories

1. As a developer, I want the Runner to verify that the OpenCode CLI is installed and executable before picking up tickets, so that the run does not fail midway through execution.
2. As a developer, I want the Runner to inspect `git status --porcelain` on startup and fail immediately if uncommitted changes exist, so that my existing uncommitted work is never overwritten or accidentally committed.
3. As a developer, I want the Runner to verify that `docs/tickets/` contains at least one pending Ticket file, so that the process does not idle without work.
4. As a developer, I want the Runner to validate `config.yaml` against its required schema before launching, so that misconfigured test commands or thresholds fail fast.
5. As a developer, I want the Runner to inspect `.git/hooks/pre-push` and non-destructively append a blocking guardrail for `agent/ticket-runner`, so that autonomous commands cannot push code to the remote repository while preserving any existing hooks I have installed.
6. As a developer, I want the Runner to verify Discord bot credentials on startup unless `--local-only` is specified, so that I am alerted immediately if remote notifications cannot be delivered.
7. As a developer, I want the Runner to support a `--local-only` CLI flag that bypasses Discord connectivity checks, so that I can run tickets entirely offline at my terminal.
8. As a developer, I want the Runner to automatically switch to or create the dedicated `agent/ticket-runner` branch on startup, so that `main` is never directly modified.
9. As a developer, I want the Runner to author authoritative conventional commits (`feat(T001): Title`) containing acceptance details upon Gatekeeper approval, so that the git history reflects cleanly verified units of work.
10. As a developer, I want the Runner to extract the commit SHA after each commit and record it in persistent state and the completed ticket file, so that completed work is fully auditable.
11. As a developer, I want the Runner to cleanly reset and clean the working tree (`git reset --hard HEAD` and `git clean -fd`) when a Ticket is skipped, so that Ticket $N+1$ always starts from a pristine tree.
12. As a developer, I want Doctor failures to display clear, actionable remediation messages in the terminal, so that I know exactly which prerequisite must be resolved before retrying.

## Implementation Decisions

- **Doctor Routine Architecture**: The Doctor runs synchronously on startup before initializing queue parsing, Discord bots, or terminal live displays. If any check fails, the Doctor prints diagnostic errors and exits with a non-zero exit code without altering repository state.
- **Pre-Push Hook Guardrail Merging**: The pre-push hook installer inspects `.git/hooks/pre-push`. If the file does not exist, it writes the shell script guardrail and marks it executable. If the file already exists, it scans for the unique Ticket Runner guardrail signature; if absent, it non-destructively appends the branch-checking script block to the end of the file.
- **Dedicated Branch Enforcement**: All automated work is isolated to `agent/ticket-runner`. If the branch does not exist, it is created from the current HEAD. The Doctor checks that the current checkout matches `agent/ticket-runner` before starting the Queue.
- **Local-Only Flag**: A CLI argument `--local-only` instructs the Doctor to skip Discord token verification, skip channel validation, and lock Presence Mode to `nearby`.
- **Command Runner Seam**: All external CLI executions (checking `opencode --version`, executing `git` commands, validating shell hooks) are dispatched via an injectable `CommandRunner` protocol.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that the Doctor permits startup when prerequisites are satisfied and halts with diagnostic error output when any prerequisite fails. Tests do not inspect internal check ordering or private helper methods.
- **Modules Tested**: Pre-flight Doctor validator, Git operations coordinator, pre-push hook installer, and CLI flag parser.
- **Seams and Test Doubles**: Tests run against temporary directories created via `pytest` fixtures. Git operations and binary checks interact with a fake `CommandRunner` that returns predetermined exit codes and output streams without calling actual operating system binaries.

## Out of Scope

- Automatic interactive git stashing of dirty working trees (the Doctor strictly fails fast).
- Merging the `agent/ticket-runner` branch back into `main` (this remains an explicit human-driven operation).
- Managing remote Git credentials or SSH keys.

## Further Notes

- In Windows environments, Git for Windows bundles a POSIX shell interpreter (`sh.exe`) that executes `.git/hooks/pre-push`. The hook script is authored for standard POSIX shell compatibility.
