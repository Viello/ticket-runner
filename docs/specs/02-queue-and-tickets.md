# Spec 02: Queue Management and Tickets Queue File

## Problem Statement

Autonomous orchestrators require an unambiguous source of truth for work items, cross-session learnings, and completion history. If the queue parser destroys markdown comments, reformats user text, permits race conditions with external text editors, or fails to propagate lessons learned across runs, the orchestrator becomes destructive to human planning and repeats past mistakes.

## Solution

Provide a non-destructive Markdown parser and state manager for `tickets.md` that maintains strict sequential execution, enforces OS file locking during active execution with pause releases, automatically relocates completed or skipped tickets to an archive section, and continuously updates global Gotchas from verified Worker runs.

## User Stories

1. As a developer, I want to define a list of sequential Tickets in `tickets.md` with requirements, acceptance criteria, and specific Gotchas, so that the Runner has a clear specification for each unit of work.
2. As a developer, I want the Runner to maintain an active OS file lock on `tickets.md` while a Ticket is executing, so that external editors cannot trigger conflicting writes or corrupt queue state.
3. As a developer, I want the Runner to release the file lock on `tickets.md` whenever the process is paused via `[p]`, waiting on a question, or halted by the Circuit Breaker, so that I can freely insert, reorder, or edit pending tickets.
4. As a developer, I want the Runner to re-acquire the file lock and re-parse `tickets.md` upon resuming from pause, so that my queue edits are immediately reflected in execution order.
5. As a developer, I want the Runner to execute Tickets strictly one at a time from top to bottom, selecting the first item with `Status: pending`, so that dependencies between tickets are naturally respected.
6. As a developer, I want the Runner to preserve all custom markdown formatting, comments, and spacing in `tickets.md` during updates, so that my notes and queue structure remain intact.
7. As a developer, I want the Runner to relocate a completed Ticket block from the active queue to `## Completed Tickets` at the bottom of `tickets.md`, so that the active queue remains concise and focused.
8. As a developer, I want completed Ticket blocks to be stamped with completion timestamp and git commit SHA, so that every completed item is traceable to source control.
9. As a developer, I want the Runner to extract `new_gotchas` emitted in completion signals and append them directly to `## Global Gotchas & Lessons Learned` in `tickets.md`, so that subsequent Tickets automatically benefit from newly discovered runtime pitfalls.
10. As a developer, I want the Runner to re-read `tickets.md` immediately before writing completion updates, so that edits I made while the Worker was running are never lost.
11. As a developer, I want skipped Tickets (resulting from Circuit Breaker escalation) to be relocated to `## Completed Tickets` with `Status: skipped` and failure details, so that the Queue continues forward without stalling.
12. As a developer, I want an empty pending Queue to trigger a graceful transition to standby or process termination per configuration, so that the Runner lifecycle behaves predictably when all work is done.

## Implementation Decisions

- **Markdown AST Parsing**: The queue manager uses a structured markdown parser to parse `tickets.md` into discrete document sections: Global Gotchas header, Active Ticket nodes, and Completed Ticket nodes. Unrecognized sections and comments are preserved verbatim.
- **Exclusive File Locking**: During active execution of any Ticket, the Runner holds an exclusive OS file handle on `tickets.md` using platform-specific locking (`msvcrt.locking` on Windows). On pause events, question prompts, or circuit breaker trips, the lock handle is closed to allow external text editor writes.
- **Atomic File Updates**: Any disk write to `tickets.md` writes to a sibling temporary file (`tickets.md.tmp`) and atomically replaces the original file, preventing partial file corruption on process termination.
- **Gotchas Injection Model**: Each Ticket prompt is composed by joining the `## Global Gotchas & Lessons Learned` section with the Ticket's own `### Gotchas` block before invoking the Worker.
- **Status Enumeration**: Ticket status values are strictly: `pending`, `running`, `completed`, and `skipped`.

## Testing Decisions

- **Testing External Behavior Only**: Tests verify that parsing extracts the expected pending Tickets in sequence, that updates correctly move sections to the completed list, that file locking blocks concurrent opens during runs, and that `new_gotchas` appear in global notes. Tests do not depend on internal AST node class types.
- **Modules Tested**: Queue file parser, markdown serializer, file lock coordinator, and gotchas aggregation manager.
- **Seams and Test Doubles**: Tests operate against real temporary markdown files on disk using `pytest` fixtures, verifying actual file locking and content preservation.

## Out of Scope

- Remote synchronization of `tickets.md` to GitHub Issues or Linear (handled by separate exporter tooling).
- Multi-branch or multi-queue concurrent execution (Ticket Runner is strictly single-queue sequential).
- Arbitrary markdown styling transformations.

## Further Notes

- On Windows, holding an exclusive file handle prevents other applications from modifying the file. Releasing the lock on pause is a critical affordance that allows developers to maintain interactive control over their queue.
