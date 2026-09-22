# T078 — Smoke log path domain helper and Gatekeeper verification tests
Status: pending
Spec: docs/specs/07-smoke-verification-protocol.md
Blocked by: None
Security: required

### Requirements
- Add `smoke_log_path(spec_slug: str) -> Path` method to `RuntimePaths` in `runner/domain/runtime_paths.py`. Sanitize `spec_slug` against directory traversal (replace non-alphanumeric, non-hyphen characters with underscores and prevent directory traversal escaping `root_dir`). Return `self.root_dir / f"smoke_log_{safe_slug}.md"`.
- Refactor `VerificationLoop._append_smoke_log` in `runner/application/gatekeeper.py` to call `paths.smoke_log_path(spec_slug)` rather than manual string path concatenation.
- Add unit tests for `RuntimePaths.smoke_log_path` in `tests/unit/domain/test_runtime_paths.py`, testing standard slugs, character sanitization, and path containment security.
- Implement the `mixed_scenarios` fixture and the three missing verification loop tests in `tests/unit/application/test_verification_loop.py`:
  1. `test_auto_covered_tag_in_terminal_output`: asserts terminal output contains `"Auto-covered scenario [also auto-covered]"` while manual-only line has no tag.
  2. `test_auto_covered_tag_in_discord_bullets`: asserts Discord send call contains `"• Auto-covered scenario [also auto-covered]"`.
  3. `test_smoke_log_appended_after_pass`: verifies `.agent/smoke_log_test-spec.md` is created with `# Smoke Log — test-spec`, `### Auto-covered scenario [also auto-covered]`, and `> Updates: T001 — Old scenario name`.
- Jump-start:
  - Files to touch: `runner/domain/runtime_paths.py`, `runner/application/gatekeeper.py`, `tests/unit/domain/test_runtime_paths.py`, `tests/unit/application/test_verification_loop.py`
  - Seams: `RuntimePaths.smoke_log_path`, `VerificationLoop._append_smoke_log`
  - Anchor patterns: `RuntimePaths.diagnostic_log_path` in `runner/domain/runtime_paths.py`
  - Verification: `python -m pytest tests/unit/domain/test_runtime_paths.py tests/unit/application/test_verification_loop.py -x -q`

### Acceptance Criteria
- `RuntimePaths.smoke_log_path("07-smoke-verification")` returns `<root_dir>/smoke_log_07-smoke-verification.md`.
- Explicit security verification: Spec slug values with path traversal sequences (e.g. `../../evil`) are sanitized and strictly contained within `root_dir`.
- `VerificationLoop._append_smoke_log` delegates path computation to `RuntimePaths.smoke_log_path`.
- The three new verification loop tests pass and assert correct tagging in terminal output, Discord messages, and appended Markdown smoke logs.
- All existing domain and application tests continue to pass.

### Smoke Scenarios
**Scenario: Gatekeeper appends smoke log and decorates outputs**
- Setup: Ensure clean working tree and no lingering `.agent/smoke_log_*.md` test artifacts.
- Steps: Run `python -m pytest tests/unit/application/test_verification_loop.py -k "smoke_log or auto_covered" -v`
- Expected: All targeted tests pass, confirming terminal output decoration, Discord bullet tagging, and file generation.

### Gotchas
- `RuntimePaths` root_dir can be instantiated as relative (`Path(".agent")`) or absolute (e.g. `tmp_path / ".agent"` in tests). Ensure path resolution and containment checks handle both consistently without throwing `ValueError` on cross-drive checks in Windows.
- `ReadySignal.scope` may be empty or None; fallback to `ticket.id` must be preserved.
