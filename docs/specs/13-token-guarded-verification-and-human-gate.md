# Spec 13: Token-Guarded Verification Subsystem & Human-in-the-Loop Gate

## Problem Statement

Current AI code generation workflows frequently suffer from two critical failure modes:
1. **Shallow Verification ("Trust Me, It Passes")**: Agents rely on unit tests or compile passes, which often pass even when real user-facing behavior, CLI ergonomics, or web interfaces are broken.
2. **Context Blowout from Verification Sprawl**: Naive attempts to add end-to-end verification (e.g. dumping Playwright browser logs, full stdout transcripts, or terminal traces into LLM prompts) exhaust the model's token context window within 2–3 turns, causing session degradation and expensive restarts.
3. **Missing Human-in-the-Loop Gate**: Autonomous agents that commit directly without human sign-off can push undesirable architectural changes, while purely manual setups lack the automated evidence collection needed for fast human decisions.

## Solution

1. **Evidence-Based Verification Subsystem**:
   - Provide a `create-verification-skill` meta-skill that inspects a target project and scaffolds `.agents/skills/verify-<app>/`:
     - Implements the 5-step lifecycle contract: `Launch` $\rightarrow$ `Doctor` $\rightarrow$ `Drive` $\rightarrow$ `Evidence` $\rightarrow$ `Cleanup`.
     - Maintains a structured feature map under `features/<feature-name>.md` following the 4-section contract: Sub-features, User POV Path, Driving Harness, and Gotchas.
     - Supports detected project surfaces: Playwright CLI for Web UIs, interactive PTY / subprocess scripts for CLIs, and curl/HTTP scripts for APIs.
   - Companion `maintain-verification-skill` audits the feature map against active code to prevent documentation and harness rot.
2. **Strict Token-Preserving Guardrails**:
   - Out-of-band execution: Verification harnesses run outside the LLM context.
   - Disk-only persistence: Full logs, terminal traces, and visual artifacts (screenshots, traces) are saved strictly to `<project-dir>/.agent/evidence/<ticket_id>/`.
   - Bounded Failure Excerpts: On verification failure, the Runner extracts a maximum of **30 lines / 1,000 characters** (first failing test and minimal error trace) for the LLM prompt. Full output is never dumped into context.
   - Conditional Execution: Behavioral verification is optional and only executed when the ticket explicitly modifies observable user-facing behavior (`Verification: required` or smoke scenarios present).
3. **Unified Human-in-the-Loop Gate**:
   - When configured in Human-in-the-Loop mode (`lifecycle.mode: "human"` or presence-driven), Gatekeeper verifies tests and behavioral harnesses first.
   - Upon green verification, Gatekeeper pauses execution, generates an **Evidence Card**, and presents it through the active presence channel:
     - **Nearby Mode (Terminal)**: Interactive Rich prompt showing Evidence Card, evidence links, and smoke scenarios with actions: `[y] approve & commit`, `[n] reject & retry`, `[d] open diagnostic session`.
     - **Away Mode (Discord)**: Posts the Evidence Card and smoke scenario checklist to the Ticket's Discord thread; waits for operator slash commands (`/approve`, `/reject`).
   - Commits are strictly blocked until human approval is confirmed.

## User Stories

1. As an operator, I want behavioral verification to execute real application code through an automated harness, so that I have tangible proof features work beyond unit tests.
2. As a developer, I want `create-verification-skill` to inspect my project and scaffold `.agents/skills/verify-<app>/`, so that my project has a tailored verification contract.
3. As a developer, I want `.agents/skills/verify-<app>/features/` to organize user-facing features into lean, standardized markdown files (under 40 lines), so that the feature map stays maintainable.
4. As an operator, I want full verification logs, screenshots, and terminal transcripts saved to disk in `.agent/evidence/<ticket_id>/`, so that I can inspect evidence without burning LLM tokens.
5. As an AI coding agent, I want verification failure prompts to contain only a concise 30-line / 1,000-character failure excerpt, so that my context window is preserved for debugging rather than flooded with raw logs.
6. As an AI coding agent, I want behavioral harness execution to be optional during implementation, so that pure refactors or internal domain edits do not waste tokens running unnecessary UI or CLI harnesses.
7. As an operator running in Human-in-the-Loop mode, I want the Gatekeeper to verify the ticket automatically before asking for my approval, so that my time is never wasted on broken code.
8. As an operator in Terminal (Nearby) mode, I want a clean interactive prompt presenting the Evidence Card, so that I can approve or reject the ticket with a single keystroke.
9. As an operator in Discord (Away) mode, I want the Evidence Card and smoke checklist posted to the ticket thread, so that I can review artifacts and send `/approve` from my phone or browser.
10. As a security-conscious operator, I want the Gatekeeper to enforce that no commit is authored in Human-in-the-Loop mode without an explicit approval signal, so that unreviewed code is never committed.
11. As a developer running interactively without Ticket Runner, I want `implement/SKILL.md` to instruct the agent to present the same Evidence Card format and wait for confirmation before committing, so that the workflow is identical across tools.
12. As an operator, I want the final ticket of this spec queue to audit implementation against Spec 13 and update living documents if any architectural details shifted during development.

## Implementation Decisions

1. **Verification Skill Contract (`.agents/skills/verify-<app>/SKILL.md`)**:
   - Defines standard CLI commands:
     - `harness/launch`: Spawns local app instance or dev server.
     - `harness/doctor`: Polls health endpoint or process vitality until ready.
     - `harness/drive <feature-name>`: Executes the targeted feature scenario.
     - `harness/cleanup`: Terminates background processes and cleans up test data.
   - The harness outputs evidence to `.agent/evidence/<ticket_id>/`.

2. **Evidence Triage Extractor (`runner/application/evidence_triage.py`)**:
   - `EvidenceTriage` interactor parses harness and test logs:
     - Identifies failure markers (`FAILED`, `AssertionError`, exit code $\neq 0$).
     - Extracts the first failing test name, error message, and a capped 30-line excerpt.
     - Writes `summary.json` containing exit code, duration, artifact file list, and sanitized failure excerpt.
     - Only the sanitized excerpt is injected into the Worker retry prompt.

3. **Gatekeeper Approval Interactor (`runner/application/gatekeeper.py`)**:
   - Extend `Gatekeeper` with an `approval_mode: "autonomous" | "human"`.
   - In `"human"` mode, after tests and harness pass:
     - State transitions to `AWAITING_APPROVAL`.
     - Generates `EvidenceCard(ticket_id, test_status, harness_status, evidence_paths, smoke_scenarios)`.
     - Dispatches notification to `ApprovalGateway` port.
     - Suspends queue execution until approval event is received.

4. **Approval Gateway Port & Adapters (`runner/ports/approval_gateway.py`)**:
   ```python
   class ApprovalGateway(Protocol):
       async def request_approval(self, card: EvidenceCard) -> ApprovalDecision:
           ...
   ```
   - `TerminalApprovalAdapter`: Renders Rich card and awaits console input.
   - `DiscordApprovalAdapter`: Posts embed to thread, registers interaction listener for `/approve` and `/reject` commands.

5. **Closing Alignment Ticket Requirement**:
   - The final ticket `T<last>` in `docs/tickets/13-token-guarded-verification-and-human-gate/` is explicitly designated as `Spec Alignment & Living Docs Audit`. It verifies that `ARCHITECTURE.md`, `CONTEXT.md`, and `AGENTS.md` reflect any adjustments made during the verification implementation.

## Testing Decisions

- **Fast Isolated Tests**:
  - `tests/unit/application/test_evidence_triage.py`: Feed mock multi-megabyte log files into `EvidenceTriage`; verify that extracted output never exceeds 30 lines or 1,000 characters.
  - `tests/unit/application/test_gatekeeper_human_approval.py`: Test `Gatekeeper` with a `FakeApprovalGateway`; verify that queue pauses, presents evidence card, and respects approve/reject decisions.
  - `tests/unit/adapters/test_terminal_approval.py`: Test keyboard interaction handling for terminal approval.
- **Spec Verification**:
  - `tests/specs/test_spec_13_verification_and_approval.py`: End-to-end test simulating a ticket execution with behavioral harness execution, failure triage extraction, and mock human approval.

## Out of Scope

- Integrating third-party cloud test farms or remote device labs.
- Video recording of headless browser sessions (static screenshot and trace capture only).

## Further Notes

- In autonomous mode (`lifecycle.mode: "autonomous"`), the Gatekeeper skips the human approval pause and commits immediately upon passing tests and harness, preserving high-throughput unattended queue runs.
