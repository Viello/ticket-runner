# T107 — Evidence Triage Extractor & Domain Models
Status: pending
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: None

### Requirements
- Build the `EvidenceTriage` application interactor that parses harness and test log files, identifies failure markers (`FAILED`, `AssertionError`, non-zero exit code), extracts the first failing test name and error message, and produces a bounded ≤30-line / 1,000-character failure excerpt.
- `EvidenceTriage` writes `summary.json` to `.agent/evidence/<ticket_id>/` containing: exit code, duration, artifact file list, and sanitized failure excerpt. Only the sanitized excerpt is ever injected into the Worker retry prompt.
- Introduce domain value objects: `EvidenceCard(ticket_id, test_status, harness_status, evidence_paths, smoke_scenarios)` and `ApprovalDecision` enum (`APPROVE`, `REJECT`, `DIAGNOSE`) with optional rejection reason.
- Jump-start: Create `runner/application/evidence_triage.py` (file listed in ARCHITECTURE.md but not yet on disk). Add domain models to `runner/domain/signal.py` or a new `runner/domain/evidence.py`. Use `RuntimePaths` for evidence directory resolution. Anchor against `runner/domain/runtime_paths.py` for path patterns and `runner/application/gatekeeper.py` for existing diagnostic extraction patterns (`_format_diagnostic`, `TAIL_LINE_LIMIT`).

### Acceptance Criteria
- `EvidenceTriage.extract(log_path, exit_code, duration)` returns a structured result never exceeding 30 lines and 1,000 characters.
- `summary.json` is written atomically via existing `atomic_write_text` utility.
- `EvidenceCard` is a frozen dataclass with all fields from the spec.
- `ApprovalDecision` is an enum with `APPROVE`, `REJECT`, `DIAGNOSE` variants and optional `reason: str`.
- Unit tests in `tests/unit/application/test_evidence_triage.py` cover: multi-megabyte log truncation, clean-pass (no failures), multiple failures (only first extracted), edge cases (empty log, binary content).

### Smoke Scenarios
**Scenario: Large log triage stays bounded**
- Setup: Create a synthetic 50,000-line log file with a `FAILED` marker at line 40,000.
- Why: The core invariant of Spec 13 is that verification output never blows up the LLM context. This confirms the 30-line / 1,000-char ceiling holds even for massive logs.
- Steps:
  1. Write a 50k-line log to a temp file with `FAILED` and `AssertionError` markers.
  2. Call `EvidenceTriage.extract(log_path, exit_code=1, duration=42.0)`.
  3. Inspect the returned excerpt and the written `summary.json`.
- Expected: Excerpt is ≤30 lines and ≤1,000 characters. `summary.json` contains `exit_code: 1`, `duration: 42.0`, non-empty `failure_excerpt`, and the artifact file list.

**Scenario: Clean pass produces empty excerpt**
- Setup: Create a passing log file (no failure markers).
- Why: On green runs, no failure excerpt should pollute the summary — only metadata.
- Steps:
  1. Write a 100-line passing log.
  2. Call `EvidenceTriage.extract(log_path, exit_code=0, duration=5.0)`.
  3. Read `summary.json`.
- Expected: `summary.json` has `exit_code: 0`, empty `failure_excerpt`, and the artifact list.

### Gotchas
- The 1,000-character limit is on the extracted text, not the JSON envelope. Measure characters after stripping ANSI escape codes.
- `RuntimePaths.evidence_dir(ticket_id)` must enforce the same ticket ID allowlist pattern as signals — reuse `TICKET_ID_PATTERN`.
