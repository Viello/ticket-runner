# T022 — Recovery and escalation: nudge, crash retry, emergency synthesis
Status: completed
Completed: 2026-09-16T13:49:30Z
Security: required
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Extend `handoff_coordinator.py` with three recovery paths (Spec 03 US13/14):
  1. Exit 0 without a ready signal → exactly one nudge run on the same session: "You exited without writing `.agent/signals/{ticket_id}_ready.json`. Write it with your `self_review_notes`, or report the blocker, then exit." A signal written during the nudge ends `READY`; otherwise escalate.
  2. Crash (non-zero exit or a stream `error` event) → exactly one same-session resume-retry whose prompt includes the trimmed stderr tail; a second crash escalates.
  3. Ceiling breach, stall, missing/stale checkpoint, or crash-after-retry → escalate: emit an escalation notice through the T019 `notify` seam, call an injectable `confirm_recovery(escalation) -> bool` (default: terminal prompt mirroring `CleanSlateArchiver`'s confirmation, safely declining on closed stdin / non-interactive runs), and only on confirmation synthesize `.agent/checkpoints/{ticket_id}/handoff.md` from `git status --porcelain` plus `git diff --stat` (T015) via `atomic_write_text`, then resume with a fresh session.
- Declined or unanswered confirmation returns `WorkerRunResult.ESCALATED` with the working tree untouched and no synthesis file written.
- The synthetic Checkpoint includes ticket id, reason, timestamp, source session id, porcelain status, diff stat, and an explicit "synthesized — no Worker handoff" marker.
- Security: required — spawns recovery runs and writes checkpoint files. Explicitly verify: the decline path performs no writes/resets; synthesis output is data only (no command execution, no shell interpolation); the checkpoint path cannot traverse; confirmation defaults to decline when stdin is unavailable.
- Jump-start:
  - Files to touch: `runner/application/handoff_coordinator.py`, `runner/application/clean_slate.py` (confirmation pattern to mirror), `tests/unit/application/test_handoff_coordinator.py`.
  - Seams: T019 `notify`, T020 `SessionRunResult`/`request_kill`, T015 `GitOperations.status_porcelain`/`diff_stat` + `RuntimePaths`, `runner/adapters/markdown/atomic_write.py`.
  - Anchor patterns: `default_terminal_confirmation` non-interactive safety in `clean_slate.py`; gotchas.md "Non-Interactive Terminal Prompt Fallback Safety".
  - Verification: `pytest tests/unit/application/test_handoff_coordinator.py`.

### Acceptance Criteria
- Missing ready signal triggers exactly one nudge spawn; a signal appearing on disk during the nudge returns `READY`; otherwise `ESCALATED`.
- One crash retry spawns with the stderr tail embedded; a second crash goes to escalation without a third spawn.
- With `confirm_recovery` returning True, the synthetic checkpoint is written with status + diff stat content and a fresh session resumes; with False or no default input, the result is `ESCALATED`, the tree is untouched, and no file was written.
- Ceiling and stall failures route through the same confirmation flow.

### Gotchas
- Emergency synthesis must not overwrite a valid Checkpoint from the current cycle — it runs only when freshness validation failed or no handoff was requested.
- The terminal default must never raise on captured/closed stdin (tests run headless).
- Escalation is presentation-free here: no Discord, no Rich (Specs 05/06 swap the notified layer); keep the notice payload structured.
- Reuse the T020 bounded-run marking for nudge/retry runs so their wall-clock cap applies.
