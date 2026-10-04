# T107 — Evidence Triage Extractor & Domain Models
Status: completed
Completed: 2026-09-24T01:59:30Z
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
- Setup: None (runs from repo root).
- Why: The core invariant of Spec 13 is that verification output never blows up the LLM context. We simulate a huge 50,000-line test log and verify that the extracted failure excerpt never exceeds the 30-line and 1,000-character ceiling.
- Steps:
  1. Run the following self-contained Python command in PowerShell to generate a 50k-line log with a failure at line 40,000, extract the excerpt, and verify the summary:
     ```powershell
     python -c @"
     import tempfile, json
     from pathlib import Path
     from runner.application.evidence_triage import EvidenceTriage

     with tempfile.TemporaryDirectory() as td:
         log_file = Path(td) / 'large.log'
         lines = [f'passing line {i}' for i in range(50000)]
         lines[40000:40003] = [
             'FAILED test_mod::test_fail - AssertionError: test failed',
             'E   AssertionError: test failed',
             'tests/test_mod.py:10: AssertionError'
         ]
         log_file.write_text('\n'.join(lines), encoding='utf-8')
         res = EvidenceTriage.extract(log_file, exit_code=1, duration=42.0, ticket_id='T107')
         summary = json.loads((Path(td) / 'summary.json').read_text(encoding='utf-8'))
         print(f'Lines: {len(res.failure_excerpt.splitlines())}, Chars: {len(res.failure_excerpt)}')
         assert len(res.failure_excerpt.splitlines()) <= 30
         assert len(res.failure_excerpt) <= 1000
         assert summary['exit_code'] == 1
         assert summary['duration'] == 42.0
         assert 'large.log' in summary['artifacts']
         print('SUCCESS: Large log triage bounded correctly!')
     "@
     ```
- Expected:
  - Prints `Lines: 30, Chars: 638` (or lines <= 30 and chars <= 1000).
  - Prints `SUCCESS: Large log triage bounded correctly!`.

**Scenario: Clean pass produces empty excerpt**
- Setup: None (runs from repo root).
- Why: On successful test runs, no failure excerpt should pollute the summary or retry prompts — only duration, exit code, and artifacts should be recorded.
- Steps:
  1. Run the following self-contained Python command in PowerShell to generate a passing log and verify the summary:
     ```powershell
     python -c @"
     import tempfile, json
     from pathlib import Path
     from runner.application.evidence_triage import EvidenceTriage

     with tempfile.TemporaryDirectory() as td:
         log_file = Path(td) / 'clean.log'
         lines = [f'passing line {i}' for i in range(100)]
         log_file.write_text('\n'.join(lines), encoding='utf-8')
         res = EvidenceTriage.extract(log_file, exit_code=0, duration=5.0, ticket_id='T107')
         summary = json.loads((Path(td) / 'summary.json').read_text(encoding='utf-8'))
         assert res.failure_excerpt == ''
         assert summary['exit_code'] == 0
         assert summary['duration'] == 5.0
         assert summary['failure_excerpt'] == ''
         assert 'clean.log' in summary['artifacts']
         print('SUCCESS: Clean pass produced empty failure excerpt!')
     "@
     ```
- Expected:
  - Prints `SUCCESS: Clean pass produced empty failure excerpt!`.

### Gotchas
- The 1,000-character limit is on the extracted text, not the JSON envelope. Measure characters after stripping ANSI escape codes.
- `RuntimePaths.evidence_dir(ticket_id)` must enforce the same ticket ID allowlist pattern as signals — reuse `TICKET_ID_PATTERN`.
