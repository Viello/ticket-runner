# T111 — Discord Approval Adapter
Status: completed
Completed: 2026-09-27T14:27:00Z
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: T108
Security: required

### Requirements
- Implement `DiscordApprovalAdapter` at `runner/adapters/discord/approval.py` implementing the `ApprovalGateway` protocol.
- On `request_approval(card)`, post the `EvidenceCard` as a Discord embed to the ticket's thread showing: ticket ID, test/harness status, evidence artifact links, and smoke scenario checklist with checkboxes.
- Register interaction listener for `/approve` and `/reject` slash commands within the thread. `/reject` must accept an optional `reason` string argument.
- Authenticate interaction sender against `config.discord.notify_user_id` when configured, and enforce that interactions only process if originating within the matching ticket thread channel. Reject unauthorized interactions ephemerally.
- Sanitize and length-bound the untrusted `reason` string parameter from `/reject` before creating `ApprovalDecision`.
- Clamp embed description and field values to Discord API size limits (≤4,096 char description, ≤1,024 char per field value, ≤25 fields) and ensure bot tokens/secrets are never leaked.
- Block until an authorized approval or rejection interaction is received, then return the corresponding `ApprovalDecision`.
- Jump-start: Anchor against `runner/adapters/discord/commands.py` for slash command registration, `runner/adapters/discord/gateway.py` for message posting, and `runner/adapters/discord/thread_listener.py` for event routing within threads. Use `FakeDiscordGateway` for testing.

### Acceptance Criteria
- `DiscordApprovalAdapter` satisfies `isinstance(adapter, ApprovalGateway)`.
- Evidence Card embed contains ticket ID, test status, harness status, evidence links, and smoke scenarios.
- `/approve` interaction → `ApprovalDecision.APPROVE`.
- `/reject reason:"flaky tests"` interaction → `ApprovalDecision.REJECT(reason="flaky tests")`.
- Security verification: interactions from unauthorized users (non-matching `notify_user_id` when configured) or outside the target ticket thread are rejected with an ephemeral error and never return an approval decision.
- Security verification: untrusted `reason` input from `/reject` is sanitized against control/injection characters and bounded in length.
- Security verification: bot token and environment secrets are never logged or exposed in embed content or error traces.
- Security verification: embed fields enforce Discord limits (≤4,096 char description, ≤1,024 char per field, ≤25 fields) without raising unhandled Discord API validation errors.
- Unit tests in `tests/unit/adapters/test_discord_approval.py` using `FakeDiscordGateway` verify embed posting, approve flow, reject flow, unauthorized user rejection, and payload size bounds.

### Smoke Scenarios
**Scenario: Discord Evidence Card embed posted and approved**
- Setup: None (runs from repo root using standard project Python environment).
- Why: The Discord Evidence Card is the primary approval surface for Away mode, allowing operators to review test status, harness status, artifact paths, and smoke checklists on mobile/browser before authoring a commit.
- Steps:
  1. Run the following command in PowerShell:
     ```powershell
     python -c @"
     import asyncio
     from runner.adapters.discord.approval import DiscordApprovalAdapter
     from runner.domain.evidence import EvidenceCard, ApprovalDecision
     from tests.fakes.fake_discord_gateway import FakeDiscordGateway

     g = FakeDiscordGateway(thread_id='thread-111')
     a = DiscordApprovalAdapter(g, thread_id='thread-111')
     g.queue_interaction('/approve')
     c = EvidenceCard(
         ticket_id='T111',
         test_status='passed',
         harness_status='passed',
         evidence_paths=('.agent/evidence/T111/log.txt',),
         smoke_scenarios=({'name': 'Check UI', 'auto_covered': True},),
     )
     d = asyncio.run(a.request_approval(c))
     assert d == ApprovalDecision.APPROVE
     assert len(g.calls) == 1
     assert g.calls[0].embed['title'] == 'Verification Approval — T111'
     print('Smoke check 1 passed: Embed posted with approval confirmed')
     "@
     ```
- Expected: Output prints `Smoke check 1 passed: Embed posted with approval confirmed`. Discord gateway records a posted message to `thread-111` containing the EvidenceCard embed, and `request_approval` returns `ApprovalDecision.APPROVE`.

**Scenario: Discord reject with sanitized reason**
- Setup: None (runs from repo root using standard project Python environment).
- Why: Rejection feedback submitted through Discord `/reject reason:"..."` must propagate back cleanly to the Gatekeeper and Worker as a retry hint without leaking secrets or allowing control character injections.
- Steps:
  1. Run the following command in PowerShell:
     ```powershell
     python -c @"
     import asyncio
     from runner.adapters.discord.approval import DiscordApprovalAdapter
     from runner.domain.evidence import EvidenceCard, ApprovalDecision
     from tests.fakes.fake_discord_gateway import FakeDiscordGateway

     g = FakeDiscordGateway(thread_id='thread-111')
     a = DiscordApprovalAdapter(g, thread_id='thread-111')
     g.queue_interaction('/reject reason:\"Tests look flaky\"')
     c = EvidenceCard(ticket_id='T111', test_status='passed')
     d = asyncio.run(a.request_approval(c))
     assert d == ApprovalDecision.REJECT
     assert d.reason == 'Tests look flaky'
     print('Smoke check 2 passed: Reject with sanitized reason returned')
     "@
     ```
- Expected: Output prints `Smoke check 2 passed: Reject with sanitized reason returned`. Returned decision is `ApprovalDecision.REJECT` with `.reason` equal to `'Tests look flaky'`.

### Gotchas
- Discord embeds have a 4,096-character description limit and 25-field limit — the adapter must truncate evidence paths and smoke scenarios if they exceed these bounds.
- The adapter must handle Discord rate limits gracefully (the existing `DiscordGateway` already has retry logic).
