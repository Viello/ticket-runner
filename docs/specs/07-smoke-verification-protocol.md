# Spec 07 — Smoke Verification Protocol

**Status**: Partially implemented — handoff in progress  
**Scope**: Cross-cutting — implement skill, Gatekeeper, signal schema, AGENTS.md

---

## 1. Motivation

The existing implement skill classifies smoke scenarios as either `[auto-covered]` or
`[needs human]`, and silently omits auto-covered scenarios from the human checklist. This
creates a gap: automated tests can miss runtime edge cases, UI states, or environment-specific
behaviour that only a human eye catches. The fix is an invariant — every scenario a Worker
generates must always have a human verification path.

This spec defines that invariant and the full lifecycle: how scenarios are classified,
accumulated, surfaced, and used to recover from failures.

---

## 2. Invariant

> **Every LLM-generated smoke scenario always requires human verification. Automated test
> coverage is additive metadata (`[also auto-covered]`), never a gate.**

Corollaries:

- A ticket with no `### Smoke Scenarios` section is **incomplete**. The Worker must flag it
  and must not emit a ready signal.
- A scenario tagged `[also auto-covered]` still appears in the human checklist verbatim.
- The human checklist is never empty when a ticket has smoke scenarios.

---

## 3. Coverage Audit (Worker responsibility)

After implementation and before emitting the ready signal, the Worker performs a
**coverage audit** over the ticket's `### Smoke Scenarios` section:

For each scenario, the Worker reasons — using agent judgment, not mechanical grep — about
whether the automated test suite fully exercises it end-to-end:

- `[also auto-covered]`: the scenario's Setup, Steps, and Expected outcome are exercised by
  at least one existing automated test. Tag the scenario with `"auto_covered": true` in the
  ready signal.
- No tag (default): the scenario has no automated equivalent. `"auto_covered": false`.

The audit result is informative only. It does not change which scenarios appear in the checklist.

---

## 4. Ready Signal Schema Extension

`manual_verification` entries gain two optional fields:

```json
{
  "name": "Login with expired session",
  "setup": "...",
  "steps": "...",
  "expected": "...",
  "auto_covered": true,
  "update_notes": "Updates: T041 — Session expiry redirect scenario"
}
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `auto_covered` | bool | `false` | Whether the automated suite also exercises this scenario |
| `update_notes` | string | `""` | Free-text note when this scenario supersedes a prior ticket entry |

Both fields are optional and backward-compatible.

---

## 5. Smoke Log

### Location

`.agent/smoke_log_<spec-slug>.md` — one file per spec slug, untracked runtime state
(`.agent/` is git-ignored per existing convention).

`spec-slug` is derived from `ready_signal.scope` when present; falls back to the leading
prefix of the ticket ID if scope is absent.

### Format

```markdown
# Smoke Log — <spec-slug>

## T042 — Login expiry handling
_Appended: 2026-09-22T14:30:00Z_

### Login with expired session [also auto-covered]

**Setup**: ...
**Steps**: ...
**Expected**: ...

> Updates: T041 — Session expiry redirect scenario

---

## T043 — Logout flow
_Appended: 2026-09-22T15:00:00Z_

### Clean logout clears all tokens

**Setup**: ...
**Steps**: ...
**Expected**: ...

---
```

### Append rules

1. The Gatekeeper appends after every passing verification cycle with a non-empty
   `manual_verification` array.
2. Entries are append-only. No existing entry is ever rewritten by the system.
3. When a new scenario supersedes a prior one, the Worker sets `update_notes` in the ready
   signal. The Gatekeeper renders it as `> Updates: ...` under the new scenario block.
4. The human may annotate or close entries manually at any time.

---

## 6. Discord Notification

After each passing verification, the Gatekeeper sends a names-only Discord summary:

```
✅ Gatekeeper passed — manual verification required:
• Login with expired session [also auto-covered]
• Clean logout clears all tokens
```

This is a notification surface only. The smoke log is the durable record.

---

## 7. Commit Body Injection

The commit body trailing section lists all scenario names, tagging auto-covered ones:

```
Manual verification required:
- Login with expired session [also auto-covered]
- Clean logout clears all tokens
```

---

## 8. Batch Review Ceremony

After all tickets for a spec complete:

1. The human opens `.agent/smoke_log_<spec-slug>.md`.
2. For each scenario, the human executes the Setup / Steps and confirms the Expected outcome.
3. No formal close signal is required. The log is informational.
4. `[also auto-covered]` scenarios are still manually verified — automated coverage is not
   a substitute.

---

## 9. Smoke Failure Recovery

### Today (interactive)

When a scenario fails during batch review:

1. The human opens an interactive agent session and describes the failure verbally.
2. The agent and human debug together using `/diagnosing-bugs` where applicable.
3. If a code fix is needed, the human creates a regression ticket manually under the same
   spec slug (or uses `/smoke-fail` — see below).

### /smoke-fail (stubbed this iteration)

The `/smoke-fail` skill guides the human through:

1. Selecting the failing ticket and scenario name from the smoke log.
2. Capturing observed vs expected behaviour.
3. Auto-creating a regression ticket under the same spec slug, pre-populated with context.

Full automation is deferred; the stub documents the seam and guides an interactive session.

---

## 10. Gatekeeper Implementation

New method `_append_smoke_log(ready_signal, ticket)` on `VerificationLoop`:

- Derives `spec_slug` from `ready_signal.scope or ticket.id`.
- Appends the formatted section to `.agent/smoke_log_{spec_slug}.md`.
- Called unconditionally when `manual_verification` is non-empty and verification passes.

The existing terminal print and Discord notification are retained and updated to include
`[also auto-covered]` tags.

---

## 11. Out of Scope (this iteration)

- Blocking the Ticket Runner on smoke result (no `_smoke_result.json` gate).
- Automatically detecting scenario overlap across tickets.
- Parsing smoke log entries programmatically.


---

## 12. Implementation Status (handoff)

### Completed in this session

| Item | File | Status |
|---|---|---|
| Spec | `docs/specs/07-smoke-verification-protocol.md` | ✅ Written |
| Implement skill rewrite | `.agents/skills/implement/SKILL.md` | ✅ Done — steps 5-7 replaced |
| `/smoke-fail` stub skill | `.agents/skills/smoke-fail/SKILL.md` | ✅ Written |
| `signal.py` validation extension | `runner/domain/signal.py` | ✅ Done — `auto_covered` (bool) + `update_notes` (str) fields accepted |
| `_append_smoke_log()` method | `runner/application/gatekeeper.py` | ✅ Added |
| Manual verification handler update | `runner/application/gatekeeper.py` | ✅ `[also auto-covered]` tags in terminal/Discord/commit body; smoke log appended; empty-array changed to warning |
| AGENTS.md smoke invariants | `AGENTS.md` | ✅ Two invariants added to Invariants section + Smoke log review to Quality workflow |
| Existing test updated | `tests/unit/application/test_verification_loop.py` | ✅ `test_empty_manual_verification_emits_all_covered_line` → `test_empty_manual_verification_logs_warning` |

### Not yet done — next session

- New tests for `auto_covered` tagging and `_append_smoke_log()` (were being written when handoff was called):
  - `test_auto_covered_tag_in_terminal_output`
  - `test_auto_covered_tag_in_discord_bullets`
  - `test_smoke_log_appended_after_pass` — needs `RuntimePaths` to expose `agent_dir`; check its API first
- Run full test suite: `pytest tests/unit/domain/test_signal.py tests/unit/application/test_verification_loop.py -x -q`
- Decompose this spec into tickets via `/to-tickets` targeting `docs/tickets/07-smoke-verification-protocol/`

### Known open issue

~FIXED~ _append_smoke_log() originally called `paths.agent_dir` which does not exist on `RuntimePaths`. Fixed to use `paths.root_dir` before handoff.

### Suggested next skill

`/to-tickets` — decompose `docs/specs/07-smoke-verification-protocol.md` into tracer-bullet tickets.
