# T044 — Stream tool-use and resource access detection
Status: pending
Spec: docs/specs/08-worker-skill-protocol-and-telemetry.md
Blocked by: None

### Requirements
- Update `runner/adapters/opencode/opencode_worker.py` to add `"tool_use"` to `KNOWN_EVENT_TYPES`, ensuring live OpenCode tool invocations are recognized and not discarded as unknown events.
- Implement dual resource access detection that identifies when the Worker consults project-local skills under `.agents/skills/<name>/SKILL.md` or `AGENTS.md`:
  - Structured detection: inspect `tool_use` event payloads for `read` tool `filePath` arguments and `bash` tool shell commands (e.g. `cat`, `Get-Content`, `type`), normalizing path separators and case.
  - Stream line fallback: scan raw JSONL lines for substring occurrences of `.agents/skills/<name>/SKILL.md` or `AGENTS.md` to ensure resilient detection across varied formatting.
- Map detected accesses to canonical identifiers: skill folder name (e.g. `"implement"`, `"code-review"`, `"security-review"`, `"diagnosing-bugs"`) and `"AGENTS.md"`.
- Jump-start:
  - Files to touch: `runner/adapters/opencode/opencode_worker.py`, `tests/unit/adapters/test_opencode_worker.py`.
  - Seams: `OpenCodeWorkerCli.decode_event()`, `extract_resource_access()`.
  - Anchor patterns: `_extract_token_usage()` in `opencode_worker.py`.
  - Verification: `python -m pytest tests/unit/adapters/test_opencode_worker.py`.

### Acceptance Criteria
- `decode_event` returns `OpenCodeEvent` with `is_known=True` for `"tool_use"` events.
- `extract_resource_access` detects `read` tool invocations targeting `.agents/skills/<name>/SKILL.md` regardless of Windows (`\`) or POSIX (`/`) separators.
- `extract_resource_access` detects `read` tool invocations targeting `AGENTS.md`.
- `extract_resource_access` detects `bash` tool commands inspecting skill files or `AGENTS.md`.
- Fallback scanning identifies skill and `AGENTS.md` references in raw event strings when tool payloads are unstructured.
- Full `test_opencode_worker.py` suite passes.

### Gotchas
- On Windows, OpenCode emits absolute paths with mixed separators (e.g. `D:\Projects\.agents\skills\implement\SKILL.md` or `D:/Projects/...`). Always normalize via `.replace("\\", "/").lower()` before substring or regex evaluation.
