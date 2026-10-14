---
name: status
description: "Track project state, bootstrap STATUS.md, orient across sessions, and prevent context loss."
argument-hint: "[save|update|clean]"
---

Manage project status and orient coding agents across sessions using a root `STATUS.md` file.

## Invocations & Subcommands

- `/status` (default): If `STATUS.md` does not exist, run **Bootstrap Mode**. If `STATUS.md` exists, run **Resume Mode**.
- `/status save` or `/status update`: Run **Save / Checkpoint Mode** to snapshot current WIP, uncommitted changes, active file/symbol, and next steps into `STATUS.md`.
- `/status clean`: Archive completed items and refresh `STATUS.md` for fresh work.

---

## 1. Shared Repo Safeguard Check

Before creating `STATUS.md` in any repository for the first time, execute the safeguard check:

1. **Ask the User**:
   Prompt the user:
   > "Is this a **shared team repository** or a **personal / solo project**?"

2. **If Shared Team Repository**:
   Ensure personal status files never pollute the team's working tree or shared `.gitignore`:
   - Append `STATUS.md` to `.git/info/exclude` (create `.git/info/exclude` if missing).
   - Check if `.agents/` is tracked by git:
     ```bash
     git ls-files --error-unmatch .agents/
     ```
     If it exits with non-zero (untracked by team), also append `.agents/` to `.git/info/exclude`.
   - Inform the user:
     > "Configured `.git/info/exclude` to keep `STATUS.md` (and local `.agents/`) 100% private to your machine."

3. **If Personal / Solo Project**:
   Prompt the user:
   > "Would you like `STATUS.md` tracked in git (to sync WIP across workstations) or kept local in `.git/info/exclude`?"
   Apply their choice accordingly.

---

## 2. Bootstrap Mode (When `STATUS.md` Does Not Exist)

When invoked without an existing `STATUS.md`:

1. **Run the Safeguard Check** above.
2. **Inspect Git Environment**:
   - Run `git status -sb` to inspect the current branch, tracked upstream, and modified/untracked files.
   - Run `git log --author="$(git config user.name)" -n 5 --oneline` to inspect the user's most recent commits.
3. **Discover Active Task / Ticket (Universal Ladder)**:
   Evaluate in order without assuming any single project framework:
   - **Step 3a (Branch Slug)**: Check current branch name. If formatted with an identifier (e.g., `feat/T012-...`, `fix/42-auth`, `task/user-profile`), extract the ticket ID and topic.
   - **Step 3b (GitHub Issues)**: If `gh` is installed and authenticated, run `gh issue list --assignee @me --state open --limit 5`. If open assigned issues are returned, display them to the user for rapid selection.
   - **Step 3c (Universal Project Trackers)**: Search for local tracking files in the workspace:
     - `docs/agents/issue-tracker.md`
     - `TODO.md`
     - `ROADMAP.md`
     - `docs/tickets/` (or ticket queues)
     If found, inspect for active or in-progress entries.
   - **Step 3d (Interactive Fallback)**: If no active ticket was found, prompt the user:
     > "What ticket, issue, or goal are you currently focusing on in this project?"
4. **Locate Last Touchpoint**:
   Identify the primary file and symbol/function being edited based on `git diff --stat` and `git diff`.
5. **Generate Root `STATUS.md`**:
   Write `STATUS.md` adhering strictly to the [STATUS.md Schema](#statusmd-schema) below.
6. **Offer AGENTS.md Setup**:
   Check if `AGENTS.md` exists in the project root. If it exists and does not already contain a STATUS rule, ask:
   > "Would you like me to add the Session Orienting rule to your `AGENTS.md` so future agent sessions automatically read `STATUS.md` on startup?"
   If accepted, append the snippet from [AGENTS.md Rule Snippet](#agentsmd-rule-snippet).
7. **Present Welcome Back Briefing**:
   Conclude by presenting the 4-bullet briefing.

---

## 3. Resume Mode (When `STATUS.md` Exists)

When `/status` is called and `STATUS.md` already exists:

1. **Read `STATUS.md`**:
   Parse both the YAML frontmatter and markdown sections.
2. **Verify Against Working Tree**:
   Run `git status -sb` and `git branch --show-current`.
   - Compare the current branch against `branch` in frontmatter.
   - Compare modified files against `stopped_at.file` and `uncommitted files`.
   - If a discrepancy exists (e.g., user switched branches or committed files outside the agent), note the discrepancy.
3. **Present 4-Bullet "Welcome Back" Briefing**:
   Output the briefing in clean markdown:
   ```markdown
   ### ⚡ Welcome Back Briefing
   - 🎯 **Current Focus**: [Active Ticket / Goal from STATUS.md]
   - 🚧 **Last Touchpoint**: [File:line or function] on branch `[branch]` ([clean / X uncommitted files])
   - ⚠️ **Active Blockers / Gotchas**: [Blockers or 'None']
   - ⏭️ **Immediate Next Step**: [Concrete 1st action from STATUS.md]
   ```
4. **Confirm Action**:
   Ask the user to confirm proceeding with the immediate next step or if priorities have shifted.

---

## 4. Save / Checkpoint Mode (`/status save` or `/status update`)

When invoked explicitly or called during session wrap-up:

1. **Inspect Working Tree**:
   Run `git status -sb` and `git diff --cached --stat` / `git diff --stat`.
2. **Determine Exact Touchpoint**:
   Identify the specific file and function/class where work was paused or is in flight.
3. **Draft Next 1–3 Actionable Steps**:
   Ensure each step is concrete, imperative, and actionable without requiring re-exploration.
4. **Update `STATUS.md`**:
   Rewrite `STATUS.md` with updated timestamp, branch, active ticket, diff details, touchpoint, and next steps.
5. **Confirm**:
   Report:
   > "✅ Updated `STATUS.md` with current branch (`<branch>`), touchpoint (`<file>`), and next steps."

---

## 5. Clean Mode (`/status clean`)

When invoked to clear finished work:
- Move items marked completed `[x]` under `Active Tickets & Progress` into `Recent Completed Work`.
- Reset `stopped_at` pointers and update `last_updated`.

---

## Reference & Templates

### STATUS.md Schema

```markdown
---
project: <project-name>
last_updated: YYYY-MM-DDTHH:MM:SS
author: <git user.name>
branch: <current-branch>
active_ticket: <ticket-or-goal-id>
status: in_progress | blocked | ready_to_verify | paused
stopped_at:
  file: <relative/path/to/file>
  symbol: <function_or_symbol_name>
---

# Project Status: <project-name>

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: <short active ticket or goal summary>
- **Last Touchpoint**: `<file>` (`<symbol>`) on branch `<branch>` (<clean or N uncommitted files>)
- **Blockers**: None (or brief description)
- **Next Step**: <immediate next action>

## 🎯 Active Tickets & Progress
- [ ] `<ticket-id>`: <summary of current work>
  - Context / Spec: <link or path>
  - Subtasks:
    - [x] Completed subtask
    - [ ] Pending subtask

## 🚧 Exact Work-In-Progress
- **Branch**: `<current-branch>`
- **Uncommitted Files**:
  - `path/to/file`: <summary of changes in flight>
- **Last Stopped At**: `<path/to/file>` at line `<line>` inside `<symbol>()`

## 📦 Recent Completed Work & Key Decisions
- **<Date/Commit>**: <Key decision or milestone reached>

## ⚠️ Blockers & Gotchas
- <Any gotchas, fragile tests, environment requirements, or blockers>

## ⏭️ Next 1–3 Actionable Steps
1. `<Step 1>`: <Specific action to execute next>
2. `<Step 2>`: <Following action>
3. `<Step 3>`: <Following action>
```

### AGENTS.md Rule Snippet

```markdown
## Session Orienting & Status
- At the start of every session or when resuming, read root `STATUS.md` if present.
- Present the 4-bullet "Welcome Back" briefing and confirm the active ticket and immediate next step before modifying code.
- Before concluding a session or handing off, invoke `/retro`, `/handoff`, or `/status save` to refresh `STATUS.md`.
```
