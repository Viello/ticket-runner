# T135: `SIGNAL_FORMAT` Label and One-Shot Self-Correctable Retry

**Status:** done (reviewed; SIGNAL_FORMAT failure label, one-shot retry exemption without prompt, and status event reporting)
**Completed:** 2026-11-02T19:15:00Z
**Labels:** ready-for-agent, security
**Security:** required (changes when a ticket-boundary violation may be treated as a correctable typo)
**Parent:** docs/specs/18-signal-contract-hardening.md

**What to build:** Make a malformed Signal cheap without weakening the security boundary. A `SIGNAL_FORMAT` failure label distinguishes a self-correctable format error from a `PROTOCOL` boundary violation. The first format error per Ticket run that would otherwise escalate retries without prompting, consumes one Verification Attempt, resumes the same Worker Session with the parser error, and publishes a `SIGNAL_FORMAT_RETRY` status event naming the offending field. The second occurrence follows the configured escalation policy. Ticket deletion, unauthorized ticket mutation, and a missing Signal keep `PROTOCOL` and escalate immediately, and an operator RETRY at the Circuit Breaker does not re-arm the exemption.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/failure_analyser.py`
  - `runner/application/gatekeeper.py`
  - `tests/unit/domain/test_diagnostic_report.py`
  - `tests/unit/application/test_verification_loop_escalation.py`
  - `tests/unit/application/test_gatekeeper_loop.py`
  - `tests/unit/application/test_verification_loop_status_publishing.py`
- **Seams:** `LABEL_PROTOCOL`, `FAILURE_LABELS`, `SUGGESTED_ACTIONS`; `VerificationLoop._check_escalation`, `_protocol_diagnostic`, `_handle_failure`, and the malformed ready and malformed question parse branches.
- **Existing-code anchors:** The escalation-policy calculation in `_check_escalation`; `_publish_status` with `RunState.VERIFYING`; the attempt counter and `_handle_failure` RETRY path; `FakeInterventionGateway` escalation records.
- **Verify:** `py -3 -m pytest tests/unit/domain/test_diagnostic_report.py tests/unit/application/test_verification_loop_escalation.py tests/unit/application/test_gatekeeper_loop.py tests/unit/application/test_verification_loop_status_publishing.py -q`

**Blocked by:** T134

- [x] `SIGNAL_FORMAT` joins `FAILURE_LABELS` and `SUGGESTED_ACTIONS`; the operator report renders it, and no production branch compares label strings.
- [x] `_check_escalation` accepts `self_correctable: bool = False` and `_protocol_diagnostic` accepts a label; only the malformed ready and malformed question branches pass `SIGNAL_FORMAT` with `self_correctable=True`, while ticket deletion, unauthorized mutation, and a missing Signal keep `PROTOCOL` and prompt immediately.
- [x] One per-Ticket exemption shared by ready and question Signals applies only when the failure is self-correctable and the configured policy would otherwise escalate now; it returns without prompting, consumes the attempt, and resumes the same session with the parser error. The second occurrence follows the configured policy, and an operator RETRY at the Circuit Breaker does not re-arm the exemption.
- [x] The automatic retry publishes a `SIGNAL_FORMAT_RETRY` status event in the verifying state carrying the current attempt number and a summary naming the offending field, alongside a log line.
- [x] Tests prove: a first malformed ready Signal with an escalation policy of 1 and remaining budget does not prompt, consumes one attempt, resumes the session, and a later valid Signal passes; a second malformed Signal prompts; ticket deletion prompts on the first occurrence; a malformed question follows the same exemption; and the retry event carries the attempt and field.
- [x] Targeted tests pass; Ruff and mypy are clean on every changed file; the security review is recorded.

**Verified:** 2026-11-02 — 38 targeted verification loop, escalation, diagnostic report, and status publishing tests; full suite 2,177 passed / 4 skipped; Ruff and mypy clean on changed files. Standards, Spec, and Security code reviews completed with zero findings above Low.
