# T013 — Ephemeral clean slate archival and chore commit
Status: pending
Spec: docs/specs/02-queue-and-tickets.md

### Requirements
- Implement the clean-slate flow (e.g. `runner/application/clean_slate.py` interactor) honoring `lifecycle.clean_slate` from `RunnerConfig`:
  - `interactive`: prompt `[Y/n]` through an injected confirmation callback (terminal `input` by default; Spec 05 can later route the prompt to Discord).
  - `always`: proceed without prompting. `never`: skip silently.
- On confirmation: back up `docs/tickets/<spec-slug>/` (including `completed/`) and `docs/specs/<spec-slug>.md` to untracked `.agent/archive/<spec-slug>/`, then remove them from git tracking, reset `docs/tickets/gotchas.md` to its skeleton, and author exactly one `chore(queue): Clean up <spec-slug> tickets, gotchas, and spec` commit (user story 13, ADR 0012).
- Back up before removing; declining the prompt or the `never` policy leaves the working tree untouched.
- Add the Git operations needed for removal (e.g. `git rm -r <path>`) to `GitClient` using the existing `CommandRunner` pattern; never push (ADR 0005).
- Hook the flow into the queue exhaustion path of `QueueOrchestrator` after the completion notice, before standby/terminate.
- Jump-start:
  - Files to touch: `runner/application/clean_slate.py`, `runner/adapters/git/git_client.py`, `runner/application/queue_orchestrator.py`, `tests/unit/application/test_clean_slate.py`, `tests/specs/test_spec_02_queue.py`.
  - Seams: `runner/application/clean_slate.py:CleanSlateArchiver` with injected `GitOperations`, confirmation callback, and archive root.
  - Anchor patterns: `GitOperations.commit_ticket` for commit conventions and `GitClient` command wrappers; `.agent/archive/` is untracked because `.agent/` is git-ignored; ADR 0012 chore commit wording.
  - Verification: `pytest tests/unit/application/test_clean_slate.py tests/specs/test_spec_02_queue.py`.

### Acceptance Criteria
- `interactive` prompts, and `[Y]` archives + removes + commits in one `chore(queue)` commit; `[n]` changes nothing.
- `always` performs the flow without prompting; `never` never archives or commits.
- Archive copies of tickets and the spec exist under `.agent/archive/<spec-slug>/` before removal, and the archive is not tracked by git.
- `docs/tickets/gotchas.md` is reset to its skeleton in the same commit; root living documents (`AGENTS.md`, `ARCHITECTURE.md`, `CONTEXT.md`) are untouched.
- The commit message exactly follows `chore(queue): Clean up <spec-slug> tickets, gotchas, and spec` with no ticket numbers (AGENTS.md).
- Tests use temporary trees and `FakeCommandRunner` to assert archive-then-remove ordering and single-commit behavior.

### Gotchas
- `git rm` fails on paths that are not tracked; handle a re-run or partially tracked state with a clear error and no partial deletion.
- The archive copy must complete before any `git rm`; an interruption between them must not lose history.
- Commit scope must be `queue` and the message must not include ticket identifiers (AGENTS.md commit format; `GitOperations` sanitizes titles, but the chore message is authored directly).
- `.agent/` is git-ignored by design, so the backup is intentionally untracked — do not add it to git.
