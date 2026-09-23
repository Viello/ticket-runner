# T111 — Discord Approval Adapter
Status: pending
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: T108

### Requirements
- Implement `DiscordApprovalAdapter` at `runner/adapters/discord/approval.py` implementing the `ApprovalGateway` protocol.
- On `request_approval(card)`, post the `EvidenceCard` as a Discord embed to the ticket's thread showing: ticket ID, test/harness status, evidence artifact links, and smoke scenario checklist with checkboxes.
- Register interaction listener for `/approve` and `/reject` slash commands within the thread. `/reject` must accept an optional `reason` string argument.
- Block until an approval or rejection interaction is received, then return the corresponding `ApprovalDecision`.
- Jump-start: Anchor against `runner/adapters/discord/commands.py` for slash command registration, `runner/adapters/discord/gateway.py` for message posting, and `runner/adapters/discord/thread_listener.py` for event routing within threads. Use `FakeDiscordGateway` for testing.

### Acceptance Criteria
- `DiscordApprovalAdapter` satisfies `isinstance(adapter, ApprovalGateway)`.
- Evidence Card embed contains ticket ID, test status, harness status, evidence links, and smoke scenarios.
- `/approve` interaction → `ApprovalDecision.APPROVE`.
- `/reject reason:"flaky tests"` interaction → `ApprovalDecision.REJECT(reason="flaky tests")`.
- Unit tests in `tests/unit/adapters/test_discord_approval.py` using `FakeDiscordGateway` verify embed posting, approve flow, and reject flow.

### Smoke Scenarios
**Scenario: Discord Evidence Card embed posted**
- Setup: Configure `FakeDiscordGateway` with a ticket thread ID. Construct a passing `EvidenceCard`.
- Why: The Discord card is the primary approval surface for Away mode — operators must see full verification context on mobile/browser.
- Steps:
  1. Instantiate `DiscordApprovalAdapter` with fake gateway.
  2. Call `await adapter.request_approval(card)` (with simulated `/approve` interaction queued).
  3. Inspect fake gateway's posted messages.
- Expected: One embed message posted to the ticket thread containing ticket ID, "PASSED" status, and smoke scenarios. Returns `APPROVE`.

**Scenario: Discord reject with reason**
- Setup: Queue a simulated `/reject reason:"Tests look flaky"` interaction on the fake gateway.
- Why: Rejection feedback from Away mode must propagate back as operator hint for Worker retry.
- Steps:
  1. Call `await adapter.request_approval(card)`.
  2. Inspect returned decision.
- Expected: Returns `ApprovalDecision.REJECT` with `reason="Tests look flaky"`.

### Gotchas
- Discord embeds have a 4,096-character description limit and 25-field limit — the adapter must truncate evidence paths and smoke scenarios if they exceed these bounds.
- The adapter must handle Discord rate limits gracefully (the existing `DiscordGateway` already has retry logic).
