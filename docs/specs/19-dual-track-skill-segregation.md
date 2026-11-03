---
spec_id: 19-dual-track-skill-segregation
triage: ready-for-agent
status: settled
date: 2026-11-03
author: Gab
target_project: D:\Projects (Runner), D:\Repos\agent-skills (Skills Catalog), and D:\Repos\ticket-runner-site (Documentation Site)
related_adrs:
  - ADR 0002 (Independent Gatekeeper Verification)
  - ADR 0004 (Explicit Signal Files)
  - ADR 0008 (Configurable Worker Execution Skill) — amended by this spec
  - ADR 0013 (Ticket-Driven Security Review) — amended by this spec
  - ADR 0014 (Interrupt-and-Resume Context Handoff) — amended by this spec
  - ADR 0020 (Direct File-Read Skill Protocol and Telemetry) — amended by this spec
  - ADR 0026 (Dual-Track Skill Segregation and Human Control Routing) — proposed by this spec
---

# Spec 19: Dual-Track Skill Segregation — Isolating Interactive Human + AI Skills from Autonomous Ticket Runner Skills

## Problem Statement

Work across this ecosystem runs in two distinct operating modes: interactive **Human + AI pair programming** (where a developer and an AI collaborate directly in a live chat session) and **autonomous Ticket Runner execution** (where the Runner spawns headless Worker subprocesses under independent Gatekeeper supervision).

Although Spec 17 separated ticket authoring (`to-tickets` versus `to-ticket-runner`) and primary implementation (`implement` versus `implement-ticket-runner`), four supporting skills remained shared between both tracks: `code-review`, `security-review`, `diagnosing-bugs`, and `handoff`. Sharing those four skills across incompatible execution models has caused recurring cross-contamination:

1. **Autonomous Worker rules bleed into interactive pair programming.** Recent fixes to make autonomous runs work — such as instructing `code-review` to diff the uncommitted working tree against `HEAD` without asking for a fixed point, instructing `code-review` and `security-review` to emit `.agent/questions/<ticket_id>.json` on blockers, and instructing `diagnosing-bugs` to withhold ready Signals during a stuck test suite — live directly inside the default skills a human invokes during everyday pair programming.
2. **Interactive chat assumptions bleed into headless Worker sessions.** Because the autonomous Worker reads those same four skills from disk, its context is polluted with interactive instructions that fail or mislead in a headless subprocess: asking the user in chat for a git comparison ref, showing ranked bug hypotheses in chat before testing, setting ticket frontmatter to `ready-for-human`, or prompting `[y/n]` to bootstrap `STATUS.md` during a 135k-token Context Handoff.
3. **Human control in Ticket Runner uses a different channel than interactive chat.** In interactive sessions, the agent talks to the human in the chat turn. In Ticket Runner, human control is mediated by the Gatekeeper via durable Question Signals (`.agent/questions/<ticket_id>.json`) that transition the run to `WAITING_FOR_USER` and prompt the operator on Discord or the Terminal. Stuffing both interaction models into one skill obscures when and how the Worker should escalate to the human operator.
4. **No documented rule prevents future regressions.** Nothing in the repository's operating contract forbids patching a shared Human + AI skill to fix a Ticket Runner behaviour, so each new autonomous edge case risks further corrupting the interactive skill catalog.
5. **Downstream catalog and documentation site drift.** Both the canonical Skills Catalog (`Viello/agent-skills`) and the documentation site (`D:\Repos\ticket-runner-site`) still describe or vendor shared review, debugging, and handoff skills for the autonomous pipeline.

## Solution

Establish a strict **Dual-Track Skill Segregation Rule** in the operating contract and complete the split across all supporting skills so that interactive Human + AI pair programming and autonomous Ticket Runner orchestration never share mutable workflow skills:

1. **Codify the segregation rule in the operating contract and ADR 0026.** Record a binding rule in the repository instructions, workflow documentation, and a new ADR: default skills (`to-tickets`, `implement`, `code-review`, `security-review`, `diagnosing-bugs`, `handoff`) belong exclusively to interactive Human + AI pair programming and must contain zero autonomous Runner rules, `.agent/` Signal instructions, or Gatekeeper constraints. Every capability invoked by the Runner or an autonomous Worker must live in a dedicated `-ticket-runner` skill.
2. **Split the four shared supporting skills into standalone `-ticket-runner` counterparts.** Create `code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, and `handoff-ticket-runner` as self-contained skills with `disable-model-invocation: true`, and restore `code-review`, `security-review`, `diagnosing-bugs`, and `handoff` to pure interactive Human + AI skills.
3. **Preserve and sharpen human control in Ticket Runner via Question Signal escalation.** Every human decision point in the `-ticket-runner` skills — un-remediable `CRITICAL`/`HIGH` code or security findings, spec ambiguities, missing credentials, inability to construct a bug reproduction loop, or stuck-suite isolation failure after one to two attempts — explicitly instructs the Worker to emit a durable Question Signal (`.agent/questions/<ticket_id>.json`). The Gatekeeper halts the queue at `WAITING_FOR_USER` and prompts the operator via Discord or the Terminal before resuming.
4. **Rewire the Runner, telemetry checks, Doctor, and sandbox scaffolder to the `-ticket-runner` suite.** Update prompt generation, ready Signal protocol rendering, Worker telemetry resource-access auditing, Context Handoff instructions, Doctor pre-flight skill verification, sandbox scaffolding, and catalog publication checks to reference and enforce only the `-ticket-runner` skill family.
5. **Synchronize the Skills Catalog and documentation site.** Update the local and upstream Skills Catalog (expanding from 50 to 54 canonical skills) and synchronize the upstream pipeline documentation and `D:\Repos\ticket-runner-site` so every stage of the autonomous pipeline names the real `-ticket-runner` skills.

## User Stories

1. As a developer pair-programming interactively with an AI, I want `/code-review` to ask me for a fixed point when I do not supply one and compare committed history without autonomous working-tree overrides, so that my interactive review workflow behaves predictably.
2. As a developer pair-programming interactively with an AI, I want `code-review`, `security-review`, `diagnosing-bugs`, and `handoff` to contain no `.agent/signals/` or `.agent/questions/` instructions, so that an interactive agent never writes Runner state files or stops to wait for a Gatekeeper.
3. As a developer pair-programming interactively with an AI, I want `/handoff` to synchronize `STATUS.md` and ask me whether to bootstrap it when missing, without autonomous checkpoint constraints interfering.
4. As a maintainer of the repository rules, I want a clear rule in the operating contract and workflow guide stating that Ticket Runner skills and Human + AI skills are strictly segregated, so that future commits never inject Runner-specific instructions into interactive skills.
5. As an autonomous Worker executing a Ticket, I want `code-review-ticket-runner` to review uncommitted working-tree changes (`git diff HEAD` plus untracked files) against the active Ticket and Spec without asking for a git ref, so that pre-signal review runs deterministically in a single pass.
6. As an operator running Ticket Runner via Discord or Terminal, I want `code-review-ticket-runner` to emit `.agent/questions/<ticket_id>.json` whenever a `CRITICAL` or `HIGH` review finding or spec ambiguity requires my architectural or policy decision, so that the Gatekeeper halts at `WAITING_FOR_USER` and prompts me for direction.
7. As an autonomous Worker executing a security-flagged Ticket, I want `security-review-ticket-runner` to audit uncommitted changes across trust boundaries and emit `.agent/questions/<ticket_id>.json` when remediation requires missing credentials or a human security decision, so that the operator retains control over security-critical choices.
8. As an autonomous Worker diagnosing a failing test or stuck suite, I want `diagnosing-bugs-ticket-runner` to guide reproduction loop construction and the Stuck-Test-Suite Protocol while escalating to the human via `.agent/questions/<ticket_id>.json` if a loop cannot be built or isolation fails after one to two attempts, so that the Worker neither guesses blindly nor emits a false ready Signal.
9. As an autonomous Worker reaching the 135k token threshold, I want `handoff-ticket-runner` to write `.agent/checkpoints/<ticket_id>/handoff.md` directly without touching `STATUS.md` or prompting `[y/n]`, so that Context Handoff completes unattended and resumes cleanly in a fresh Worker Session.
10. As a developer working in an interactive session, I want all `*-ticket-runner` skills marked with `disable-model-invocation: true`, so that my coding assistant never auto-selects an autonomous Worker skill during interactive chat.
11. As a Gatekeeper auditing Worker telemetry on both OpenCode and Antigravity CLI, I want ready-signal resource checks to verify that the Worker read `code-review-ticket-runner` and (when `Security: required`) `security-review-ticket-runner`, so that soft warnings reflect the segregated autonomous skill names.
12. As an operator running `ticket-runner doctor`, I want the pre-flight skills check to verify that `implement-ticket-runner`, `code-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`, and `security-review-ticket-runner` exist and are readable in the Target Project, so that missing autonomous skills are caught before dispatch.
13. As an operator scaffolding a sandbox or initializing a Target Project, I want the curated skill set and synced `AGENTS.md` bullets to provision the `-ticket-runner` skills, so that newly initialized projects pass Doctor immediately.
14. As a maintainer publishing the Skills Catalog, I want the publication script to verify the presence and signal-contract compliance of all 54 canonical skills (including the six `-ticket-runner` skills), so that `ticket-runner skills sync` distributes the complete segregated catalog.
15. As a maintainer, I want a repository contract test that fails if any interactive Human + AI skill (`to-tickets`, `implement`, `code-review`, `security-review`, `diagnosing-bugs`, `handoff`) references `.agent/signals/` or `.agent/questions/`, so that cross-contamination can never silently return.
16. As a reader of the Ticket Runner documentation site (`D:\Repos\ticket-runner-site`), I want the pipeline stages, vendored skills, and generated snapshot to reference the `-ticket-runner` skill family accurately, so that the site matches the authoritative Runner implementation.

## Implementation Decisions

### 1. Operating Contract & ADR 0026 (Dual-Track Skill Segregation Rule)

Record ADR 0026 establishing the **Dual-Track Skill Segregation and Human Control Routing** decision (amending ADRs 0008, 0013, 0014, and 0020), and add the rule to both the root operating contract and the interactive workflow guide:

- **Strict Skill Segregation**: Interactive Human + AI skills and autonomous Ticket Runner skills are separate skill families. Never add autonomous Worker rules, uncommitted-diff overrides, Gatekeeper prohibitions, or `.agent/` Signal paths to an interactive Human + AI skill; edit or create the corresponding `-ticket-runner` skill instead.
- **Complete Six-Pair Matrix**:

| Capability | Interactive Human + AI Skill | Autonomous Ticket Runner Skill |
| :--- | :--- | :--- |
| Ticket Authoring | `to-tickets` | `to-ticket-runner` |
| Ticket Implementation | `implement` | `implement-ticket-runner` |
| Pre-Completion Code Review | `code-review` | `code-review-ticket-runner` |
| Conditional Security Audit | `security-review` | `security-review-ticket-runner` |
| Bug & Stuck-Suite Diagnosis | `diagnosing-bugs` | `diagnosing-bugs-ticket-runner` |
| Context Handoff | `handoff` | `handoff-ticket-runner` |

- **Preserve `AGENTS.md` Extraction Prefixes**: Keep the `## Invariants`, `## Environment`, and `## Agent skills` headings and the bullet prefixes parsed by the prompt builder and sandbox scaffolder intact, updating the skill bullets and scaffolder prefix constants together so upstream-to-sandbox synchronization stays green.

### 2. Restoring Pure Interactive Human + AI Skills

Clean the four interactive skills so they contain zero autonomous Runner instructions:

- **`code-review`**: Reviews the diff between `HEAD` and a user-supplied fixed point (`git diff <fixed-point>...HEAD`). If the user did not specify a fixed point, asks for it in chat. Runs `Standards`, `Spec`, and conditional `Security` (referencing `security-review`). On un-remediable `CRITICAL`/`HIGH` blockers, sets the ticket status to `ready-for-human` and asks the operator in chat. Carries a one-line note pointing autonomous Ticket Runner runs to `code-review-ticket-runner`.
- **`security-review`**: Conducts a scoped security audit of pending changes when the ticket marks `Security: required` or the user asks. On un-remediable blockers requiring missing credentials or architectural decisions, stops and asks the human in chat (or sets `ready-for-human`). Removes all references to ready Signals and `.agent/questions/`. Carries a one-line note pointing autonomous runs to `security-review-ticket-runner`.
- **`diagnosing-bugs`**: Interactive six-phase diagnosis loop and Stuck-Test-Suite Protocol. Shows ranked hypotheses to the user, asks the user in chat when a reproduction loop cannot be built or Phase D isolation fails, and removes the trailing Ticket Runner ready-signal paragraph. Carries a one-line note pointing autonomous runs to `diagnosing-bugs-ticket-runner`.
- **`handoff`**: Compacts the current conversation into a portable handoff markdown file (saving to a user-provided path or OS temp directory) and synchronizes `STATUS.md` (prompting the user `[y/n]` to bootstrap `STATUS.md` if absent). Removes the `.agent/checkpoints/` example. Carries a one-line note pointing autonomous runs to `handoff-ticket-runner`.

### 3. Standalone `-ticket-runner` Skills with Human Control via Question Signals

Each of the four new `-ticket-runner` skills is a self-contained skill directory (with `SKILL.md` and `agents/openai.yaml`) marked `disable-model-invocation: true` in YAML frontmatter so interactive agents never auto-trigger them, while autonomous Workers read them explicitly via their file-reading tool:

- **`code-review-ticket-runner`**:
  - Evaluates the uncommitted working-tree diff (`git diff HEAD` plus untracked files from `git status --short`) against repository standards (including the 12 Fowler code smells), the active Ticket's `## What to build` and `## Acceptance criteria`, and the originating Spec.
  - Runs the `Security` axis when the Ticket header marks `Security:` as `required`, `true`, or `yes`, instructing the Worker to read `security-review-ticket-runner`.
  - **Human Control Routing**: `LOW` and `MEDIUM` findings are remediated in-pass or summarized in `self_review_notes`. `CRITICAL` and `HIGH` findings are remediated and re-tested in-session; if remediation is blocked by a required human architectural decision, policy choice, or spec contradiction, the Worker emits `.agent/questions/<ticket_id>.json` (following the task prompt's `Question Signal Protocol` section) so the Gatekeeper halts at `WAITING_FOR_USER` and prompts the human operator via Discord or Terminal.
- **`security-review-ticket-runner`**:
  - Audits uncommitted changes across authentication, network, untrusted input, secrets, storage, privacy, filesystem paths, subprocesses, serialization, dependencies, logging, and trust boundaries before emitting a ready Signal.
  - **Human Control Routing**: Applies concrete code fixes and re-verifies. If fixing a `CRITICAL` or `HIGH` security issue requires missing credentials, external secrets, or a human architectural/policy decision, emits `.agent/questions/<ticket_id>.json` (deferring to the prompt's `Question Signal Protocol`) so the Gatekeeper transitions to `WAITING_FOR_USER` and prompts the operator via Discord or Terminal.
- **`diagnosing-bugs-ticket-runner`**:
  - Guides autonomous Workers through building a red-capable feedback loop, reproducing and minimising failures, testing ranked hypotheses, and executing the four-phase Stuck-Test-Suite Protocol (`HANG`, `CASCADE`, `ENV`, `FLAKY`) when verification fails or hangs.
  - **Human Control Routing**: Never emits `.agent/signals/<ticket_id>_ready.json` while the test suite is failing or stuck. When a reproduction loop genuinely cannot be constructed (missing environment access or external artifact) or Phase D isolation fails to produce a single-test reproduction after one to two attempts, the Worker stops guessing and emits `.agent/questions/<ticket_id>.json` containing the classification (`HANG` / `CASCADE` / `ENV` / `FLAKY`), last output line or top repeating error, and isolation outcome so the Gatekeeper halts at `WAITING_FOR_USER` and prompts the human operator via Discord or Terminal.
- **`handoff-ticket-runner`**:
  - Invoked by the Runner's Context Handoff protocol at the 135k token threshold.
  - Writes a structured handoff checkpoint directly to the target path supplied in the prompt (`.agent/checkpoints/<ticket_id>/handoff.md`) covering Active Context, Completed Work, Pending State, Suggested `-ticket-runner` Skills, and Immediate Next Steps.
  - Never modifies `STATUS.md`, never commits, and never prompts `[y/n]` in stdout so the interrupt-and-resume cycle completes cleanly.
- **`implement-ticket-runner` Alignment**:
  - Update references inside `implement-ticket-runner` so Sections 1, 2, 3, and 6 direct the Worker to read `code-review-ticket-runner`, `security-review-ticket-runner`, and `diagnosing-bugs-ticket-runner`.
  - None of the `-ticket-runner` skills embed raw Signal JSON examples; all defer to the authoritative `Ready Signal Protocol` and `Question Signal Protocol` sections rendered in the task prompt (preserving Spec 18's single schema authority).

### 4. Runner Wiring, Telemetry Auditing, Doctor, and Scaffolder Alignment

Update the Runner's application and tooling layers to call and enforce the segregated `-ticket-runner` skills across both `OpenCodeWorker` and `AntigravityWorker`:

- **Prompt Builder & Ready Signal Protocol**:
  - The task prompt and ready Signal protocol instruction direct the Worker to read `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/security-review-ticket-runner/SKILL.md` (when `Security: required`), and `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md` (for non-trivial test failures), and reference `.agents/skills/handoff-ticket-runner/SKILL.md` for the 135k token handoff invariant.
- **Gatekeeper & TicketProcessor Telemetry Checks**:
  - Both `OpenCodeWorker` and `AntigravityWorker` already extract the skill directory name `<name>` from `.agents/skills/<name>/SKILL.md` into `resources_accessed`.
  - Update the ready-warning checks in `GatekeeperVerificationLoop` and `TicketProcessor` to check for `"code-review-ticket-runner"` and (when `ticket.security_required` is true) `"security-review-ticket-runner"`, emitting soft warnings naming `.agents/skills/code-review-ticket-runner/SKILL.md` and `.agents/skills/security-review-ticket-runner/SKILL.md` when omitted.
  - Update the Gatekeeper's test-failure retry diagnostic guidance to point the Worker to `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`.
- **Context Handoff Coordinator**:
  - Update the handoff prompt in `HandoffCoordinator` to invoke `.agents/skills/handoff-ticket-runner/SKILL.md`.
- **Doctor Pre-Flight Skill Verification**:
  - Update `REQUIRED_SKILL_PATHS` in `Doctor` to verify `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`, `.agents/skills/handoff-ticket-runner/SKILL.md`, and `.agents/skills/security-review-ticket-runner/SKILL.md` alongside the configured `execution_skill` (`.agents/skills/implement-ticket-runner/SKILL.md`).
- **Sandbox Scaffolder & Catalog Publisher**:
  - Update `CURATED_SKILLS`, fallback `AGENTS.md` templates, and `## Agent skills` keep-prefixes in the sandbox scaffolder to include the `-ticket-runner` skills (`implement-ticket-runner`, `code-review-ticket-runner`, `security-review-ticket-runner`, `diagnosing-bugs-ticket-runner`, `handoff-ticket-runner`, `to-ticket-runner`).
  - Update tarball verification assertions in the catalog publisher to verify the presence of the six `-ticket-runner` skills alongside `implement`.

### 5. Catalog, Upstream Docs, and `D:\Repos\ticket-runner-site` Synchronization

- **Skills Catalog (`D:\Repos\agent-skills` / `Viello/agent-skills`)**:
  - Synchronize the four new `-ticket-runner` skills and the four cleaned interactive skills (plus updated router/reference notes in `ask-matt` and `implement-ticket-runner`) into `D:\Repos\agent-skills` and regenerate its `README.md` index (54 canonical skills).
- **Upstream `README.md` & `D:\Repos\ticket-runner-site`**:
  - Update the 8-stage pipeline diagram and Stage Details in `D:\Projects\README.md` so Stage 3 names `/to-ticket-runner`, Stage 4 names `.agents/skills/implement-ticket-runner/SKILL.md`, Stage 5 names `code-review-ticket-runner`, and Stage 6 names `security-review-ticket-runner`.
  - Update `D:\Repos\ticket-runner-site` (`scripts/sync-runner.mjs` pipeline definitions, vendored `.agents/skills/`, and generated `content/snapshot.json` via `npm run sync`), then verify the static build via `npm run verify`.

## Testing Decisions

A good test observes external behaviour at public boundaries: the skill paths rendered into Worker and handoff prompts, the warnings returned when a ready Signal arrives with or without skill reads, the pre-flight verdict returned by Doctor, and the absence of autonomous Signal syntax inside interactive skill files.

Four existing seams cover the entire change; no new seam is required:

| Seam | What it proves | Prior art |
| :--- | :--- | :--- |
| **Skill Catalog & Segregation Contract** | All six `-ticket-runner` skills exist with `disable-model-invocation: true`, pass the markdown Signal contract checker, and describe `.agent/questions/<ticket_id>.json` escalation; all six interactive skills (`to-tickets`, `implement`, `code-review`, `security-review`, `diagnosing-bugs`, `handoff`) contain zero `.agent/signals/` or `.agent/questions/` references | `tests/unit/domain/test_signal_contract.py`, `tests/unit/scripts/test_publish_agent_skills.py` |
| **Prompt, Handoff & Signal Protocol** | `PromptBuilder.build_prompt`, `render_ready_signal_protocol`, and `HandoffCoordinator` render `.agents/skills/code-review-ticket-runner/SKILL.md`, `.agents/skills/security-review-ticket-runner/SKILL.md`, `.agents/skills/diagnosing-bugs-ticket-runner/SKILL.md`, and `.agents/skills/handoff-ticket-runner/SKILL.md` | `tests/unit/application/test_prompt_builder.py`, `tests/unit/application/test_handoff_coordinator.py` |
| **Worker Telemetry & Gatekeeper Warnings** | Both `OpenCodeWorker` and `AntigravityWorker` decode `.agents/skills/<name>-ticket-runner/SKILL.md` reads into `resources_accessed`; `GatekeeperVerificationLoop` and `TicketProcessor` warn when `code-review-ticket-runner` or required `security-review-ticket-runner` are unread and pass when read | `tests/unit/adapters/test_opencode_worker.py`, `tests/unit/adapters/test_antigravity_worker.py`, `tests/unit/application/test_gatekeeper.py`, `tests/unit/application/test_ticket_processor.py` |
| **Doctor, Scaffolder & Site Sync** | `Doctor.check_skills` requires the `-ticket-runner` skill files; `scaffold_sandbox` and `sync_agents_md` provision the `-ticket-runner` skills and keep-prefixes; `D:\Repos\ticket-runner-site` passes `npm run sync` and `npm run verify` | `tests/unit/application/test_doctor.py`, `tests/unit/tools/test_scaffold_sandbox.py` |

## Out of Scope

- Changing the 5-section Ticket Runner markdown format (`to-ticket-runner`) or the compact Human + AI ticket format (`to-tickets`).
- Changing the domain Signal JSON schema (`ReadySignal` and `QuestionSignal` fields remain governed by `runner/domain/signal_schema.py` per Spec 18).
- Modifying unrelated reference or standalone skills in `.agents/skills/` (such as `clean-architecture`, `domain-modeling`, `tdd`, or `wayfinder`).
- Re-capturing live Gatekeeper terminal artifacts in `D:\Repos\ticket-runner-site/content/artifacts/`.

## Further Notes

- **Why standalone `-ticket-runner` skills beat thin wrappers**: If `code-review-ticket-runner` or `diagnosing-bugs-ticket-runner` told the Worker to also read the base interactive skill, the Worker would spend two file-read tool calls and load the interactive instructions ("ask the user for a fixed point", "prompt `[y/n]` for `STATUS.md`") into its context window, re-introducing the exact confusion this spec eliminates.
- **Human control is channel-specific, not absent**: Interactive skills converse with the human in the chat turn; `-ticket-runner` skills escalate to the human through `.agent/questions/<ticket_id>.json` so the Gatekeeper halts at `WAITING_FOR_USER` and routes the prompt through Discord or the Terminal.

