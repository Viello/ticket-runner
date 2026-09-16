# T021 — Handoff coordinator A: threshold reaction and single handoff cycle
Status: pending
Security: required
Spec: docs/specs/03-worker-orchestration-and-handoff.md

### Requirements
- Add `runner/application/handoff_coordinator.py` driving one Worker Session chain step on top of the T019/T020 supervisor: build the initial ticket prompt through T017 (Spec Excerpt from `ticket.spec_path`, global gotchas via `GotchasStore.load()`, execution skill path from `WorkerConfig`, ticket contents, security-conditional review instruction), run it, and react to budget actions while the stream is consumed.
- On `HANDOFF` (occupancy `>= 135000`): record `handoff_requested_at`, call `request_kill(KILLED_HANDOFF)`, then start the handoff instruction run on the *same* session (the only session id available was learned from the stream — never invent one) with the Spec 03 wording: threshold reached at 135k tokens; execute `.agents/skills/handoff/SKILL.md`; save the handoff document to `.agent/checkpoints/{ticket_id}/handoff.md`; include modified files, architectural decisions, test status, immediate next steps; then exit.
- On `CEILING` (occupancy `>= 150000`): `request_kill(KILLED_CEILING)` and return the failure reason without launching a handoff run.
- Checkpoint acceptance (ADR 0014): file exists and `mtime >= handoff_requested_at - 2s` (clock slack), resolved through T015 runtime paths. A stale file from a previous cycle must fail validation.
- On an accepted Checkpoint, launch a fresh Worker Session (no `--session`; id learned from the stream) with the resume prompt: read the handoff at the checkpoint path, inspect `git status`, then continue the ticket.
- Return a single-cycle result: `READY`, or a failure reason (`CEILING`, `CHECKPOINT_MISSING`, `CHECKPOINT_STALE`) for T022 to route; chain looping is T023.
- Security: required — resumes Worker processes under `--auto` and validates filesystem paths. Explicitly verify: the checkpoint path is built only through `RuntimePaths` (no traversal), the resumed `--session` value is stream-learned and allowlist-validated, and prompts contain repo/ticket data only (no secrets, no env expansion).
- Jump-start:
  - Files to touch: `runner/application/handoff_coordinator.py`, `tests/unit/application/test_handoff_coordinator.py`.
  - Seams: T017 `PromptBuilder`, T019/T020 `WorkerSupervisor`, T015 `RuntimePaths`, `GotchasStore`.
  - Anchor patterns: prompt-instruction text is fixed in Spec 03 ("Handoff Protocol Execution"); `tests/unit/application/test_queue_orchestrator.py` shows scripted delegation style.
  - Verification: `pytest tests/unit/application/test_handoff_coordinator.py`.

### Acceptance Criteria
- A scripted run crossing 135k is killed, the handoff run is spawned with `--session <learned-id>` and the fixed instruction text, a fresh checkpoint satisfies freshness, and Session B launches with the checkpoint path and git-status instruction in its prompt.
- A checkpoint written before `handoff_requested_at` fails validation and returns `CHECKPOINT_STALE`; a missing one returns `CHECKPOINT_MISSING`.
- Crossing 150k kills with `KILLED_CEILING` and launches no handoff run.
- A run that exits under thresholds with a ready signal returns `READY` with no extra spawns.

### Gotchas
- The Worker may write the checkpoint only as its instruction run is exiting — validate after the process exits, not on first sight of the file.
- `opencode run --session <unknown>` exits 1 (`Session not found`); resumed runs must reuse a previously observed id only.
- Freshness slack exists because filesystem timestamps can round to a second; keep the 2s constant documented at module scope.
- Do not parse ready-signal contents (Spec 04) and do not implement the retry/nudge/escalation paths (T022).
