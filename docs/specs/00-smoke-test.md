# Spec 00 — Ticket Runner Smoke Test & Model Validation

## 1. Overview
This specification provides a lightweight verification suite designed to smoke-test the Ticket Runner orchestration pipeline and validate model execution (such as `opencode/nemotron-3.5-lightning-free`) without modifying core production code or triggering context handoffs.

## 2. Goals
- Verify end-to-end autonomous ticket execution: OpenCode invocation, worker implementation, signal emission (`.agent/signals/{ticket_id}_ready.json`), and Gatekeeper verification.
- Verify single-commit authoring (ADR 0012) and ticket completion relocation to `completed/`.
- Validate sequential queue progression from `T001` to `T002`.
- Verify Gatekeeper verification failure handling and operator intervention circuit breaker on attempt exhaustion.

## 3. Tickets
- **T001 — Smoke test helper and passing unit test**: Adds `runner/smoke.py` and `tests/unit/test_smoke.py`, passes verification, and authors a clean commit.
- **T002 — Circuit breaker drill**: Adds an intentional failing assertion in `tests/unit/test_smoke.py` to trigger 3 failed verification attempts and the operator intervention menu.
