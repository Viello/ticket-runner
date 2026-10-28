# T125: Gatekeeper Dispatch-Baseline Tick Boundary and Evidence Card Unticked Criteria

**Status:** ready-for-agent
**Labels:** ready-for-agent, security
**Security:** required (trust boundaries: Gatekeeper dispatch baseline comparison preventing unauthorized Worker mutation of ticket requirements, headers, or acceptance criteria text)
**Parent:** docs/specs/17-human-first-ticket-document-format.md

**What to build:** Enforce the strict checkbox tick boundary in the Gatekeeper so an autonomous Worker may flip `- [ ]` to `- [x]` under `## Acceptance criteria` in the active ticket file and change nothing else, while any unauthorized edit restores the pre-dispatch baseline and consumes a Verification Attempt, and any unticked criteria are surfaced on the `EvidenceCard` for human review.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `runner/domain/evidence.py`
  - `runner/application/gatekeeper.py`
  - `runner/adapters/ui/terminal_approval.py`
  - `runner/adapters/discord/approval.py`
  - `tests/unit/domain/test_evidence.py`
  - `tests/unit/application/test_verification_loop.py`
  - `tests/unit/adapters/test_terminal_approval.py`
  - `tests/unit/adapters/test_discord_approval.py`
- **Seams:** `VerificationLoop.run` ready-signal inspection seam in `runner/application/gatekeeper.py` and `EvidenceCard` rendering in `runner/domain/evidence.py`, `TerminalApprovalAdapter.render_card`, and `build_evidence_card_embed`.
- **Existing-code anchors:** `VerificationLoop` ready-signal handling in `runner/application/gatekeeper.py`; `EvidenceCard` in `runner/domain/evidence.py`; `TerminalApprovalAdapter.render_card` in `runner/adapters/ui/terminal_approval.py`; `build_evidence_card_embed` in `runner/adapters/discord/approval.py`.
- **Verify:** `py -3 -m pytest tests/unit/application/test_verification_loop.py tests/unit/adapters/test_terminal_approval.py tests/unit/adapters/test_discord_approval.py -x`

**Blocked by:** T124 (Canonical `to-ticket-runner` Document Model, Parser, Dialect Guard, and In-Place Bold-Label Serializer)

- [ ] Before each Worker cycle in `VerificationLoop`, the Gatekeeper snapshots the active ticket file on disk (when present) as the dispatch baseline.
- [ ] Security verification: When a ready Signal arrives, the Gatekeeper compares the current on-disk ticket file against the dispatch baseline and permits **only** flipping `- [ ] ` to `- [x] ` (or `- [X] `) on existing lines inside `## Acceptance criteria`. Any other edit (header fields, `## What to build`, `## Jump-start`, criterion wording, `## Smoke scenarios`, `## Gotchas`, or added/deleted lines) is rejected, atomically restores the dispatch baseline on disk, refuses the ready Signal with actionable diagnostics, and consumes a Verification Attempt (ADR 0002, ADR 0012, ADR 0017).
- [ ] `EvidenceCard` gains `unticked_criteria: tuple[str, ...] = ()`, populated by `VerificationLoop` from the active ticket's remaining `- [ ]` acceptance criteria after re-parsing the verified ticket file.
- [ ] `TerminalApprovalAdapter.render_card` and `DiscordApprovalAdapter` (`build_evidence_card_embed`) render `unticked_criteria` on the Evidence Card whenever one or more acceptance criteria remain unticked so the operator sees unacknowledged criteria before approving.
