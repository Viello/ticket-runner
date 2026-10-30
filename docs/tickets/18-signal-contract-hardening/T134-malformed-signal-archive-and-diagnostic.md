# T134: Malformed Signal Archive and Diagnostic on Every Escalation

**Status:** ready-for-agent
**Labels:** ready-for-agent, security
**Security:** required (writes untrusted Signal payloads to filesystem paths derived from Ticket ids)
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** Preserve the evidence a malformed Signal carries. `RuntimePaths` gains contained archive paths for malformed ready and question Signals under the logs directory. Before consuming a malformed Signal, the Gatekeeper copies the raw payload atomically to its archive and appends the archive path to the diagnostics. The diagnostic report is written before the operator is prompted, so both a yes and a no answer leave evidence on disk.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/runtime_paths.py`
  - `runner/application/gatekeeper.py`
  - `tests/unit/domain/test_runtime_paths.py`
  - `tests/unit/application/test_verification_loop_escalation.py`
  - `tests/unit/application/test_gatekeeper_loop.py`
- **Seams:** New `malformed_ready_signal_archive_path` and `malformed_question_signal_archive_path` on `RuntimePaths`; the malformed ready and malformed question branches in `VerificationLoop.run`; `_check_escalation`.
- **Existing-code anchors:** `diagnostic_log_path` and `_check_containment` in `runner/domain/runtime_paths.py`; `atomic_write_text` in `runner/adapters/markdown/atomic_write.py`; `consume_ready` and `clean_question` on the Signal repository; the diagnostic-writing block at the end of `_check_escalation`.
- **Verify:** `py -3 -m pytest tests/unit/domain/test_runtime_paths.py tests/unit/application/test_verification_loop_escalation.py tests/unit/application/test_gatekeeper_loop.py -q`

**Blocked by:** None (can start immediately; independent of the T130–T133 contract chain)

- [ ] `RuntimePaths` exposes one stable archive path per Ticket and Signal kind under `logs_dir`; both paths validate the Ticket id and are contained within `logs_dir`.
- [ ] Before a malformed ready or question Signal is consumed or cleaned, the Gatekeeper writes its raw payload atomically to the archive and appends the archive path to the diagnostics; archiving is skipped safely when runtime paths are unavailable and processing continues.
- [ ] `_check_escalation` writes the diagnostic report before prompting the operator, so the report exists whether the operator answers yes or no; the duplicate write in the declined branch is removed.
- [ ] Tests prove the archive exists with the raw payload after a malformed Signal, the diagnostics name the archive path, and the diagnostic report exists after both escalation answers; the malformed-question path archives too.
- [ ] Security: an invalid Ticket id is rejected and no archive can be written outside `.agent/logs/`.
- [ ] Targeted tests pass; Ruff and mypy are clean on every changed file; the security review is recorded.
