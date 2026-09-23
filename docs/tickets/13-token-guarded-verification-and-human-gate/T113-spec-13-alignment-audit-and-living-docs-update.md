# T113 — Spec 13 Alignment Audit & Living Docs Update
Status: pending
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: T107, T108, T109, T110, T111, T112

### Requirements
- Audit the full Spec 13 implementation against the specification document to ensure all user stories, implementation decisions, and testing decisions are satisfied.
- Update `ARCHITECTURE.md` to document any new files, directories, or architectural patterns introduced during Spec 13 implementation (e.g., `evidence_triage.py`, `approval_gateway.py`, `terminal_approval.py`, `discord/approval.py`).
- Update `CONTEXT.md` to add or refine glossary entries for any new domain terms introduced during implementation (e.g., `Verification Harness`, `Evidence Card`, `ApprovalDecision` — some may already exist).
- Update `AGENTS.md` if any workflow invariants or environment notes changed during development.
- Mark Spec 13 as implemented in the project roadmap.
- Jump-start: Read `docs/specs/13-token-guarded-verification-and-human-gate.md` user stories (§ User Stories) and cross-reference each against the implemented code. Read `ARCHITECTURE.md` §3 and §4 for the file layout. Read `CONTEXT.md` §Language for existing glossary.

### Acceptance Criteria
- Every user story in Spec 13 has a corresponding implemented feature or documented deferral.
- `ARCHITECTURE.md` §3 (Runner Repository Layout) lists all new files from Spec 13.
- `ARCHITECTURE.md` §4 (Target Project Layout) reflects the `verify-<app>/` skill directory tree.
- `ARCHITECTURE.md` §5 (Architectural Invariants) documents the token-preserving verification and dual-mode approval gate patterns (may already be present from forward-looking entries).
- `CONTEXT.md` glossary contains entries for all Spec 13 domain terms.
- No living document references stale file paths or removed interfaces.

### Smoke Scenarios
**Scenario: Architecture doc consistency check**
- Setup: None (runs from repo root).
- Why: Living docs that reference non-existent files or miss new modules silently erode agent navigation accuracy over time.
- Steps:
  1. Grep `ARCHITECTURE.md` for `evidence_triage.py` — should be present.
  2. Grep for `approval_gateway.py` — should be present.
  3. Grep for `terminal_approval.py` — should be present.
  4. Grep for `verify-<app>` or `verify-` — should be present in §4.
  5. Cross-check every Python file path in §3 against the actual filesystem.
- Expected: All new Spec 13 files are documented. No stale paths reference removed files.

**Scenario: Context glossary completeness**
- Setup: None (runs from repo root).
- Why: Missing glossary entries cause agents to use wrong synonyms, creating confusion in tickets and code.
- Steps:
  1. Search `CONTEXT.md` for "Evidence Card", "Verification Harness", "Approval".
  2. Verify each has a definition and _Avoid_ synonyms list.
- Expected: All Spec 13 domain terms present with correct definitions.

### Gotchas
- Some terms like `Evidence Card` and `Verification Harness` were already forward-declared in `CONTEXT.md` and `ARCHITECTURE.md` — verify they still match the actual implementation, don't blindly re-add them.
- This ticket must not modify any Python source code — it is a documentation-only audit.
