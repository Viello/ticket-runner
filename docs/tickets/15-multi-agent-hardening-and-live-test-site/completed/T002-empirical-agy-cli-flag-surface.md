# T002 — Empirical `agy` CLI Flag Surface
**Type:** wayfinder:research (AFK)
Status: completed
Completed: 2026-10-04T16:54:00Z
Spec: docs/specs/15-multi-agent-hardening-and-live-test-site.md
Blocked by: none
Reasoning: low

### Question

What is the empirical, source-of-truth flag surface, JSONL envelope shape, and exit
code behavior of the `agy` CLI binary that this repo ships against? The current
adapter assumes `agy run --auto <prompt> [--session <id>] [-m <model>] [--variant
<reasoning>]` (see `runner/adapters/antigravity/antigravity_worker.py:55`) but no
ADR records *why* those flags were chosen or what `agy` actually accepts.

### Why this matters

The `AntigravityWorker` adapter hardcodes the argv structure. If the real `agy` CLI
differs:

- Flag names drift silently, breaking tests on the next `agy` release.
- Output event types (`step_start`, `step_finish`, `text`, `tool_call`, `tool_use`,
  `tool_result`, `error`) may not match — see
  `runner/adapters/opencode/opencode_worker.py:16-24` for the OpenCode allowlist.
- Token usage may surface in a different key (`tokens` vs `usage` vs `part.tokens`) —
  see `runner/adapters/antigravity/antigravity_worker.py:82-110` for the dual-mode
  fallback already in place.

T003 needs a verified flag surface to assert what the smoke test expects.

### Resolution (research subagent)

Empirical surface (`agy` 1.2.16, this host, `where agy` →
`C:\Users\Acer\AppData\Local\agy\bin\agy.exe`):

- **No `agy run` subcommand, no `--auto` flag.** The hardcoded argv at
  `runner/adapters/antigravity/antigravity_worker.py:55`
  (`["agy", "run", "--auto", prompt]`) fails immediately with
  `Error: unexpected argument "run"` and exit code `2`. The adapter is
  non-functional on every flag it assumes. **This requires a full adapter
  rewrite — see new ticket T018.**
- **Canonical headless invocation**: `agy -p "<prompt>" --output-format stream-json`
  with `--effort low|medium|high|xhigh|max` for reasoning depth, `--model <slug>` for
  model selection, `--continue`/`--conversation <uuid>` for session resume,
  `--print-timeout <dur>` (default `0s` waits indefinitely — recommended to set
  for any non-interactive use).
- **NDJSON envelope**: top-level `event` field with three closed values
  (`init`, `step_update`, `result`). The OpenCode `KNOWN_EVENT_TYPES` allowlist
  (`step_start`, `step_finish`, `text`, `tool_call`, `tool_use`, `tool_result`,
  `error`) does NOT overlap with agy's vocabulary.
- **Token usage**: at `step_update.usage` and `result.usage` with keys
  `input_tokens` / `output_tokens` / `thinking_tokens` / `cache_read_tokens` /
  `total_tokens`. Session id is `conversation_id`.
- **Exit codes**: `0` success (incl. soft-deny), `1` invalid input / bad schema /
  unknown model, `2` unexpected positional argument or unsupported stdin event
  (`control_request`, `/model`, etc.), `3` agent/model error during headless with
  `AGY_ERROR: {...}` JSON line on stderr.

### Drift in current adapter

| Adapter assumption | Empirical surface | Status |
|---|---|---|
| `agy run --auto <prompt>` | `agy -p "<prompt>" --output-format stream-json` | **Hard-broken** |
| `--session <id>` | `--continue` / `--conversation <uuid>` | Wrong flag |
| `-m <model>` | `--model <slug>` | Wrong flag (and `-m` is short for `--continue`) |
| `--variant <reasoning>` | `--effort low|medium|high|xhigh|max` | Wrong flag |
| `tokens` / `part.tokens` / `usage` | `step_update.usage` / `result.usage` | Token loss |
| `input` / `output` / `reasoning` / `cache.read` / `cache.write` keys | `input_tokens` / `output_tokens` / `thinking_tokens` / `cache_read_tokens` / `total_tokens` | Key mismatch |
| `part.tool_name` / `part.state.input` | `step_update.tool_info.parameters.<arg>` | Dead structured detection |
| No `--print-timeout` set | Default `0s` waits indefinitely | Runaway-risk |
| No `is_known` allowlist (`is_known=True` set unconditionally) | agy emits `init`, `step_update`, `result` only | Asymmetric telemetry |

### New ticket required

T018 — Rewrite Antigravity adapter to match empirical CLI surface. **Added by chart
session** per the wayfinder skill's "graduate newly-specifiable work into fresh
tickets" discipline.

### Full research file

Branch `research/agy-flag-surface` (commit `0c30f9a`), file
`.agents/skills/research/out/agy-flag-surface.md` (317 lines).

### Acceptance Criteria (now satisfied)

- ✅ `research/agy-flag-surface` branch exists with research note.
- ✅ Resolution comment links to research branch.
- ✅ Adapter audited; drift recorded above; T018 added to address.

### Gotchas

- The drift is comprehensive — T018 is a substantial rewrite, not a patch.
- The empirical surface was captured against `agy` 1.2.16. Future agy versions may
  add or rename flags; ADR-0023 + T018 should reference the research file as the
  single source of truth, with a follow-up ticket to refresh if drift recurs.