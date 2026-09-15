# Local Agentic Ticket Runner Plan

## 1. Goal

Build a **local Python ticket runner** that orchestrates OpenCode to work through a predefined `tickets.md` queue **strictly one ticket at a time**.

The user should be able to start the runner on their PC, leave it running, and return later to review completed work or answer questions through Discord.

Core workflow:

```text
tickets.md
    ↓
Python Ticket Runner
    ↓
Ticket N
    ↓
OpenCode implementation
    ↓
Tests → Build → Self-review → Verification
    ↓
Commit
    ↓
Mark ticket complete
    ↓
Next ticket
```

The runner must never begin the next ticket until the current ticket is complete.

---

## 2. Technology

- **Orchestrator:** Python
- **Coding agent:** OpenCode
- **Communication:** Discord bot
- **Ticket source:** `tickets.md`
- **Execution environment:** User's local PC
- **Initial secondary agent:** None
- **Git strategy:** One dedicated agent branch
- **Persistence:** Local state, checkpoints, logs, and question files

Antigravity is intentionally excluded from v1. It may later be added as an independent code reviewer without changing the queue architecture.

---

## 3. Ticket Queue

Tickets are maintained in a human-readable `tickets.md`.

Example:

```markdown
# Ticket Queue

## T001 — Fix admin loading state

Status: pending

### Requirements
- Add loading state to verified datasets
- Prevent duplicate loading indicators
- Preserve existing table behavior

### Acceptance Criteria
- Loading state appears while fetching
- No double scrollbar
- Existing CRUD still works

---

## T002 — Add dataset search

Status: pending

### Requirements
...

### Acceptance Criteria
...
```

The runner automatically updates ticket status and relevant execution metadata.

The user does not need to manually maintain execution state.

---

## 4. Strict Sequential Execution

Only one ticket may be active at any time.

Possible states:

```text
PENDING
  ↓
PLANNING
  ↓
WORKING
  ├── WAITING_FOR_USER
  ├── HANDOFF_REQUIRED
  └── PAUSE_REQUESTED
  ↓
TESTING
  ↓
SELF_REVIEW
  ↓
VERIFICATION
  ↓
COMPLETED
  ↓
NEXT TICKET
```

If the current ticket requires clarification, the entire queue pauses.

The runner must not work on later tickets while waiting for the user's response.

---

## 5. OpenCode Worker

Python is the orchestrator; OpenCode is the engineer.

OpenCode is responsible for:

- Inspecting the repository
- Understanding the ticket
- Planning the implementation
- Editing code
- Running tests
- Running builds
- Debugging failures
- Reviewing its own changes
- Checking acceptance criteria
- Requesting clarification when requirements are ambiguous

The OpenCode worker must be explicitly instructed:

- Work only on the assigned ticket.
- Do not start another ticket.
- Do not guess ambiguous requirements.
- Ask the user when clarification is required.
- Do not mark work complete prematurely.
- Test and verify changes before completion.
- Use the ticket handoff skill when a context handoff is required.

---

## 6. Context Management

The runner enforces a **150,000-token maximum working context budget**.

Thresholds:

```text
120,000 tokens → warning
135,000 tokens → automatic handoff
150,000 tokens → hard ceiling
```

The configured limit is a runner-level maximum, not an assumption that every OpenCode model supports 150k context.

The effective limit should be:

```text
min(configured_runner_limit, model_context_limit)
```

The runner should initiate handoff before reaching the hard limit so the agent has enough context to create a checkpoint safely.

---

## 7. Ticket Handoff Skill

Create a project-local OpenCode skill:

```text
.opencode/
└── skills/
    └── ticket-handoff/
        └── SKILL.md
```

The skill creates a durable checkpoint when a ticket requires a fresh session.

Checkpoint location:

```text
.agent/
└── checkpoints/
    └── T001/
        ├── checkpoint.md
        └── state.json
```

The checkpoint must contain:

- Current ticket
- Requirements
- Acceptance criteria
- Completed work
- Files modified
- Important implementation details
- Architectural decisions
- User decisions
- Tests performed
- Test results
- Known failures
- Known constraints
- Remaining work
- Exact next steps for the next session

The handoff must not mark the ticket complete.

---

## 8. Automatic Context Handoff

When the runner detects the handoff threshold:

```text
OpenCode Session A
        ↓
~135k tokens
        ↓
Ticket Handoff Skill
        ↓
Checkpoint
        ↓
New OpenCode Session
        ↓
Load checkpoint
        ↓
Continue same ticket
```

A ticket may span multiple OpenCode sessions.

The new session must inspect the checkpoint and current repository state before continuing.

The user does not need to intervene for an automatic context handoff.

Discord should receive a notification such as:

```text
T015 context handoff

Session reached approximately 135k tokens.
Checkpoint created.
Starting a fresh OpenCode session and continuing T015.
```

---

## 9. User-Initiated Pause / Agent Pause

The agent can request a pause when continuing safely requires user input.

State:

```text
PAUSE_REQUESTED
```

Example reasons:

- Manual verification is required
- A potentially destructive operation needs approval
- The agent cannot safely determine the intended behavior
- A significant architectural decision is required

The runner pauses and notifies the user through Discord.

---

## 10. Clarification Workflow

When requirements are ambiguous, the agent must stop rather than guess.

State:

```text
WAITING_FOR_USER
```

Discord message example:

```text
T015 needs your decision.

I found two valid approaches:

A. Reuse the existing dataset endpoint
B. Create a new admin-specific endpoint

I will not continue until you choose.

Reply A or B.
```

The user's Discord response resumes the same ticket.

The runner must preserve the question and answer in persistent state.

---

## 11. Discord Integration

Discord serves as the remote communication interface.

It must support:

### Notifications

- Ticket started
- Ticket completed
- Context handoff
- Agent pause
- Question requiring user input
- Runner errors
- Queue paused
- Queue completed

### User responses

The user can answer agent questions directly in Discord.

Example:

```text
Runner:
T005 needs clarification.
Should this use the existing endpoint or a new endpoint?

User:
existing
```

The runner associates the response with the active ticket and resumes execution.

---

## 12. Testing and Verification

A ticket cannot be considered complete merely because the agent believes implementation is finished.

Required process:

```text
Implementation
    ↓
Run tests
    ↓
Run build
    ↓
Investigate failures
    ↓
Fix failures
    ↓
Run tests/build again
    ↓
Inspect git diff
    ↓
Self-review
    ↓
Check acceptance criteria
    ↓
Final verification
```

If verification fails:

```text
FAIL
 ↓
Diagnose
 ↓
Fix
 ↓
Verify again
```

Only a successful verification allows the ticket to proceed to completion.

---

## 13. Git Strategy

The runner works on one dedicated agent branch:

```text
main
  │
  └── agent/ticket-runner
```

All tickets are processed sequentially on this branch.

`main` is never directly modified by the autonomous runner.

After a ticket passes verification, OpenCode automatically creates a commit.

Recommended commit flow:

```text
Implement
    ↓
Test
    ↓
Self-review
    ↓
Verification
    ↓
Commit
    ↓
Update ticket status
```

The runner should not automatically push to the remote repository in v1.

---

## 14. Git and System Safety

Normal development operations can run automatically.

Recommended permissions:

```text
Read files              ALLOW
Edit project files      ALLOW
Run tests               ALLOW
Run builds              ALLOW
Git status              ALLOW
Git diff                ALLOW
Normal commits          ALLOW

Git push                DENY
Force push              DENY
Database reset          ASK
Destructive DB actions  ASK
Dangerous migrations    ASK
Security/auth changes   ASK
Other destructive ops  ASK
```

The goal is unattended development without unrestricted destructive access.

---

## 15. Persistent Runner State

The runner must survive interruptions and resume safely.

Suggested structure:

```text
.agent/
├── state.json
├── checkpoints/
│   ├── T001/
│   │   ├── checkpoint.md
│   │   └── state.json
│   └── T002/
├── questions/
│   └── T003.md
└── logs/
    ├── T001.jsonl
    └── T002.jsonl
```

`state.json` should record at minimum:

- Active ticket
- Ticket status
- OpenCode session ID
- Current branch
- Context/token state
- Current checkpoint
- Pending question
- Last successful operation
- Runner state

If the PC crashes or the runner stops unexpectedly, restarting the runner should recover the active ticket instead of restarting the entire queue.

---

## 16. Automatic Ticket Updates

The runner automatically updates `tickets.md`.

For example:

```markdown
## T001 — Fix admin loading state

Status: completed

Completed:
2026-09-15 14:32

Commit:
8f31c2a
```

The runner should preserve the original ticket requirements and acceptance criteria while updating execution metadata.

---

## 17. Runner Commands

The initial interface should be simple.

Primary command:

```bash
python ticket_runner.py start
```

Useful future commands:

```bash
python ticket_runner.py status
python ticket_runner.py pause
python ticket_runner.py resume
python ticket_runner.py stop
python ticket_runner.py recover
```

The runner should display its current state locally while also reporting important events to Discord.

---

## 18. Initial Project Structure

Recommended structure:

```text
ticket-runner/
├── ticket_runner.py
├── config.yaml
├── requirements.txt
│
├── runner/
│   ├── queue.py
│   ├── state.py
│   ├── opencode.py
│   ├── context.py
│   ├── handoff.py
│   ├── git.py
│   ├── verification.py
│   └── recovery.py
│
├── discord/
│   ├── bot.py
│   ├── questions.py
│   └── notifications.py
│
├── .agent/
│   ├── state.json
│   ├── checkpoints/
│   ├── questions/
│   └── logs/
│
└── .opencode/
    └── skills/
        └── ticket-handoff/
            └── SKILL.md
```

The exact module boundaries can be adjusted during implementation, but the responsibilities should remain separated.

---

## 19. V1 Scope

V1 should focus exclusively on making the sequential autonomous workflow reliable.

### Included

- Python ticket runner
- `tickets.md` queue
- Strict sequential execution
- OpenCode integration
- 150k context policy
- Automatic context handoff
- Handoff skill
- Persistent checkpoints
- Discord notifications
- Discord question/answer flow
- Agent pause functionality
- Testing/build verification
- Self-review
- Automatic commits
- Automatic ticket status updates
- Crash recovery
- Git safety controls
- Local logs

### Not included initially

- Multiple simultaneous agents
- Antigravity integration
- Automatic PR creation
- Automatic merging
- Cloud execution
- Web dashboard
- Multiple repositories
- Parallel ticket queues
- Automatic modification of ticket requirements
- Automatic push to `main`

These can be added after the core runner is reliable.

---

## 20. Target User Experience

The final v1 experience should be:

```text
User:
python ticket_runner.py start

Runner:
Queue loaded: 12 tickets
Starting T001...

        [User leaves PC]

Runner:
✓ T001 completed
✓ T002 completed
✓ T003 completed
↻ T004 handoff completed
✓ T004 completed
⚠ T005 requires your decision
⏸ Queue paused
```

The user answers from Discord:

```text
A
```

Runner:

```text
✓ Answer received
▶ Resuming T005
```

The runner continues:

```text
✓ T005 completed
✓ T006 completed
...
```

The user ultimately returns to a dedicated agent branch containing sequentially implemented, tested, self-reviewed, and committed tickets, with any decisions or unresolved issues clearly surfaced through Discord.