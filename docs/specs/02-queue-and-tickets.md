# Spec 02: Directory-Based Ticket Queue and Gotchas Management

## Problem Statement

Autonomous orchestrators require an unambiguous source of truth for work items, cross-session learnings, and completion history. If the queue parser permits race conditions with external text editors, creates git merge conflicts across branches, clutters active directories with historical tickets, or fails to propagate lessons learned across runs, the orchestrator becomes destructive to human planning and repeats past mistakes.

## Solution

Provide a directory-based Markdown queue manager rooted at `docs/tickets/<spec-slug>/` that maintains strict sequential execution, protects the queue directory via a sentinel OS file lock (`docs/tickets/.queue.lock`) with pause releases, automatically relocates completed or skipped ticket files to a `completed/` subfolder, and continuously aggregates global Gotchas into `docs/tickets/gotchas.md` from verified Worker runs.

## User Stories

1. As a developer, I want to define sequential Tickets as individual Markdown files in `docs/tickets/<spec-slug>/T<NNN>-<slug>.md` containing requirements, acceptance criteria, and specific Gotchas, so that each unit of work has an isolated, merge-friendly specification.
2. As a developer, I want the Runner to maintain an exclusive OS file lock on a sentinel file (`docs/tickets/.queue.lock`) while a Ticket is executing, so that external editors cannot trigger conflicting writes or corrupt queue directory state.
3. As a developer, I want the Runner to release the sentinel lock whenever the process is paused via `[p]`, waiting on a question, or halted by the Circuit Breaker, so that I can freely insert, reorder, or edit pending ticket files.
4. As a developer, I want the Runner to re-acquire the sentinel lock and re-scan `docs/tickets/<spec-slug>/` upon resuming from pause, so that newly added or modified ticket files are immediately reflected in execution order.
5. As a developer, I want the Runner to execute Tickets strictly one at a time sorted by ticket identifier (`T001`, `T002`, etc.), selecting the first file with `Status: pending`, so that dependencies between tickets are naturally respected.
6. As a developer, I want the Runner to preserve all custom markdown formatting, comments, and spacing within each ticket file during status updates.
7. As a developer, I want the Runner to relocate a completed Ticket file from `docs/tickets/<spec-slug>/` to `docs/tickets/<spec-slug>/completed/`, so that the active queue directory remains concise and contains only unfinished work.
8. As a developer, I want completed Ticket files to be stamped with completion timestamp in their header metadata and relocated to completed/ within the single feature commit, so that every completed item is atomic and traceable without a redundant commit (ADR 0012).
9. As a developer, I want the Runner to extract `new_gotchas` emitted in completion signals and append them directly to `docs/tickets/gotchas.md`, so that subsequent Tickets automatically benefit from newly discovered runtime pitfalls.
10. As a developer, I want skipped Tickets (resulting from Circuit Breaker escalation) to be relocated to `docs/tickets/<spec-slug>/completed/` with `Status: skipped` and failure details, so that the Queue continues forward without stalling.
11. As a developer, I want an empty pending Queue across all spec directories to trigger a graceful transition to standby or process termination per configuration, so that the Runner lifecycle behaves predictably when all work is done.
12. As a developer, I want each Ticket file to optionally declare a `Spec: docs/specs/<spec-slug>.md` header linking to its originating spec (with fallback to the parent directory name), so that the Runner can ground the Worker in overarching architectural context.
13. As a developer, I want the Runner to interactively prompt for a clean-slate wipe when a spec queue is exhausted, backing up completed tickets and specs to untracked `.agent/archive/<spec-slug>/` and removing them from git tracking in a single chore commit, so that workspace context remains token-optimized without losing history (ADR 0012).

## Implementation Decisions

- **Directory-Based Queue Layout & Spec Linkage (ADR 0011)**: Active tickets live as individual Markdown files under `docs/tickets/<spec-slug>/T<NNN>-<slug>.md`. The parser reads ticket metadata (`Status:`, optional `Spec:`) and requirements. If `Spec:` is omitted, the parser auto-infers the spec path from `docs/specs/<spec-slug>.md` matching the ticket's parent directory.
- **Sentinel File Locking**: During active execution of any Ticket, the Runner holds an exclusive OS file handle on `docs/tickets/.queue.lock` using platform-specific locking (`msvcrt.locking` on Windows). On pause events, question prompts, or circuit breaker trips, the lock handle is closed to allow external text editor writes.
- **Completed Archive Directory & Single Atomic Commit**: When a ticket passes Gatekeeper verification, the Runner updates its metadata (`Status: completed`, `Completed: <iso_time>`), moves the file to `docs/tickets/<spec-slug>/completed/T<NNN>-<slug>.md`, and stages the code, tests, gotchas, and relocated ticket together in a single atomic feature commit without recording commit SHA in frontmatter (ADR 0012).
- **Ephemeral Queue Clean Slate**: When all tickets in `docs/tickets/<spec-slug>/` reach completion, the Runner pauses and prompts the user in the terminal (or via Discord thread) to wipe the completed queue and spec for a clean slate. On confirmation, the Runner copies `docs/tickets/<spec-slug>/` and `docs/specs/<spec-slug>.md` into untracked `.agent/archive/<spec-slug>/`, then removes the directories from Git and resets `docs/tickets/gotchas.md` in an automated `chore(queue): Clean up <spec-slug> tickets, gotchas, and spec` commit.
- **Global Gotchas Aggregation**: Cross-ticket lessons learned are maintained in `docs/tickets/gotchas.md`. Each Worker prompt is composed by joining `docs/tickets/gotchas.md` with the active Ticket's own `### Gotchas` block before invocation.
- **Atomic File Writes**: Status and metadata updates to any ticket file or `gotchas.md` write to a sibling temporary file (`.tmp`) and atomically replace the target file.
- **Status Enumeration**: Ticket status values are strictly: `pending`, `running`, `completed`, and `skipped`.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that directory scanning extracts expected pending Tickets in sequence, that completed tickets are cleanly moved to the `completed/` directory, that sentinel file locking blocks concurrent access during runs, and that `new_gotchas` append to `gotchas.md`.
- **Modules Tested**: Queue directory scanner, ticket markdown parser/serializer, sentinel file lock coordinator, and gotchas aggregation manager.
- **Seams and Test Doubles**: Tests operate against real temporary directory trees on disk using `pytest` fixtures, verifying actual file operations and sentinel locking.

## Out of Scope

- Remote synchronization of ticket files to GitHub Issues or Linear (handled by separate exporter tooling).
- Multi-branch or multi-queue concurrent execution (Ticket Runner is strictly single-queue sequential).
- Arbitrary markdown styling transformations.

## Further Notes

- Grouping tickets by spec folder (`docs/tickets/<spec-slug>/`) mirrors `docs/specs/`, providing clear visual alignment between requirements specifications and executable ticket units.
