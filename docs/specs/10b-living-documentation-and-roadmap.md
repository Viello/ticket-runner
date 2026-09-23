# Spec 10b: Living Documentation, Domain Model & Architecture Roadmap

## Problem Statement

Ticket Runner was originally designed and documented as a project-local orchestrator operating directly inside its own repository. As the system evolves into a reusable, agent-agnostic development framework capable of targeting any external project directory, the existing living documentation (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`, and `README.md`) no longer accurately reflects the target architecture.

Developers and AI agents consulting the repository face discrepancies regarding:
1. Whether Ticket Runner runs locally inside a target repository or as an external standalone orchestrator.
2. How different coding agents (OpenCode, Antigravity CLI) interface with the system.
3. How verification evidence is captured and bounded to prevent token exhaustion.
4. How the three decoupled repositories (reusable skills, ticket runner core, and target user project) relate.
5. The roadmap of upcoming specifications (Specs 11–13) and the protocol for keeping documentation aligned.

Without reconciling living documentation first, subsequent specifications and tickets risk introducing conflicting architectural assumptions and non-standard domain vocabulary.

## Solution

Update all root living documents (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`, and `README.md`) to establish the canonical, authoritative foundation for Ticket Runner as an external, multi-agent orchestrator.

The updated documentation will:
- Clearly define the Clean Architecture layout for an external runner targeting an arbitrary `--project-dir`.
- Formalize new domain terms in `CONTEXT.md` (Target Project, AgentWorker, Project Overlay Config, Verification Harness, Feature Map, Evidence Card, Skills Catalog).
- Codify invariants in `AGENTS.md` regarding external path resolution, token-budgeted verification guardrails, dual-mode human approval gates, and the mandatory spec-alignment gotchas ticket at the end of each spec.
- Document the ecosystem triad (`Viello/agent-skills`, `Viello/ticket-runner`, target projects) and provide a comprehensive architectural roadmap for Specs 11, 12, and 13.

## User Stories

1. As a framework developer, I want `ARCHITECTURE.md` to reflect the Clean Architecture structure of an external runner targeting `--project-dir`, so that I understand where new ports, adapters, and domain entities belong.
2. As a framework developer, I want `ARCHITECTURE.md` to define the `AgentWorker` port and its relation to `WorkerSupervisor`, so that multiple agent providers can be cleanly integrated.
3. As a framework developer, I want `ARCHITECTURE.md` to define the Verification Subsystem architecture, so that evidence capture and harness execution remain decoupled from the runner core.
4. As an AI coding agent, I want `CONTEXT.md` to provide precise domain definitions for Target Project, AgentWorker, Verification Harness, and Evidence Card, so that I use authoritative terminology without coining synonyms.
5. As an AI coding agent, I want `CONTEXT.md` to explicitly forbid synonyms for newly introduced domain terms, so that cross-session variance is eliminated.
6. As a human operator, I want `AGENTS.md` to document the invariants for external project execution, so that agents never assume the current working directory is the runner's source repository.
7. As a human operator, I want `AGENTS.md` to enforce the Token-Preserving Verification Guardrails contract, so that agents never inject megabytes of raw browser or CLI logs into the LLM context.
8. As a human operator, I want `AGENTS.md` to define the Human-in-the-Loop gate protocol across both interactive and autonomous modes, so that approval behavior is completely consistent.
9. As a human operator, I want `AGENTS.md` to require a closing "spec alignment and living documentation update" ticket as the final ticket of every future spec, so that documentation drift is caught before specs are archived.
10. As a prospective user, I want `README.md` to explain the high-level architecture and how Ticket Runner orchestrates external repositories, so that I understand how to integrate it into my existing workflow.
11. As a prospective user, I want `README.md` to display the planned architectural roadmap (Specs 11–13), so that I know the delivery sequence of multi-agent support, scaffolding, and verification.
12. As a developer using an AI assistant, I want `README.md` to feature an LLM-friendly setup prompt template, so that I can instruct any AI agent to inspect my project and configure `ticket-runner.yaml` immediately.

## Implementation Decisions

1. **Clean Architecture Boundary Updates (`ARCHITECTURE.md`)**:
   - The directory tree in `ARCHITECTURE.md` will be updated to show `--project-dir` runtime separation.
   - Introduce `runner/ports/agent_worker.py` as the abstract port for spawning and decoding agent processes.
   - Position `runner/adapters/opencode/` and future `runner/adapters/antigravity/` as concrete adapters implementing `AgentWorker`.
   - Update `runner/domain/config.py` to reflect two-tier configuration overlay (`global_config` + `project_config`).
   - Add the Verification Subsystem layout (`.agents/skills/verify-<app>/`, `harness/`, `features/`, and `.agent/evidence/`).

2. **Domain Glossary Expansion (`CONTEXT.md`)**:
   - Define **Target Project**: The external codebase directory containing source code, `ticket-runner.yaml`, `docs/tickets/`, and `.agent/` runtime state being operated on by the Runner. Avoid: Client project, working directory, target repo.
   - Define **AgentWorker**: The abstract port and lifecycle adapter responsible for spawning, streaming, and decoding an AI coding agent subprocess or SDK session. Avoid: Agent runner, LLM backend, agent client.
   - Define **Project Overlay Config**: The lightweight `ticket-runner.yaml` located in the Target Project root that overrides machine-level defaults with project-specific test, build, and branch rules. Avoid: Local config, project settings, runner override.
   - Define **Verification Harness**: A project-specific script or runner suite (Playwright, PTY/CLI, HTTP) executed out-of-band by the Gatekeeper to drive real application behaviors. Avoid: Test script, driver, test harness.
   - Define **Evidence Card**: The structured summary of behavioral verification outcomes (status, exit code, bounded failure excerpt, artifact links) presented on Discord or terminal for human sign-off. Avoid: Test report, verification summary, result block.
   - Define **Skills Catalog**: The centralized repository of reusable, agent-agnostic development skills (`Viello/agent-skills`) distributable to any project. Avoid: Plugin repo, skill store, prompt library.
   - Define **LLM Config Prompt**: The standardized markdown prompt generated by `ticket-runner init --ai-prompt` or provided in docs that instructs an AI to inspect a codebase and author its `ticket-runner.yaml`. Avoid: AI template, setup prompt, config assistant.

3. **Operational Invariants & Guardrails (`AGENTS.md`)**:
   - **External Path Invariant**: The Runner's working directory (`CWD`) is the Target Project. The Runner executable and global configuration reside independently. Paths inside `.agent/` and `docs/` always resolve relative to the Target Project root.
   - **Token-Preserving Verification Contract**: Full verification output (logs, screenshots, DOM traces) must be written directly to `.agent/evidence/<ticket_id>/`. The LLM prompt must only receive a bounded triage excerpt (maximum 30 lines / 1,000 characters of error output).
   - **Spec-Closing Alignment Ticket**: Every spec queue decomposed under `docs/tickets/<spec-slug>/` must include a final ticket tasked with auditing implementation against the spec and updating root living documents (`ARCHITECTURE.md`, `CONTEXT.md`, `AGENTS.md`) if any architectural reality shifted during implementation.
   - **Interactive Human Approval Invariant**: In Human-in-the-Loop mode, the Gatekeeper pauses and posts an Evidence Card via the active presence channel (Terminal prompt or Discord Status Card); commits are strictly blocked until human approval is registered.

4. **Public Documentation & Roadmap (`README.md`)**:
   - Revise `README.md` to articulate the triad ecosystem: reusable skills, external runner, and target project.
   - Outline the 8-stage workflow: Planning $\rightarrow$ Specs $\rightarrow$ Tickets $\rightarrow$ Implementation $\rightarrow$ Reviews $\rightarrow$ Security $\rightarrow$ Verification $\rightarrow$ Completion.
   - Include the specification roadmap: Spec 10b (Documentation & Roadmap), Spec 11 (Decoupled Root & Multi-Agent), Spec 12 (Scaffolding & LLM Config), Spec 13 (Verification & Human Gate).
   - Add the standalone LLM-friendly project configuration prompt.

## Testing Decisions

- A good test for documentation updates validates structural completeness and consistency across all files:
  - All new domain glossary terms in `CONTEXT.md` follow the canonical bold title, description, and italicized `Avoid:` list.
  - Cross-references in `AGENTS.md` and `ARCHITECTURE.md` use identical terminology.
  - CLI usage examples in `README.md` accurately match the CLI arguments planned for Spec 11 and Spec 12.
- Testing will be verified by automated markdown linting and manual link/consistency review.

## Out of Scope

- Modifying Python code in `runner/` (deferred to Spec 11).
- Implementing the `ticket-runner init` CLI command logic (deferred to Spec 12).
- Implementing the verification harness generation scripts (deferred to Spec 13).

## Further Notes

- Authoring this spec before Specs 11–13 locks in the domain vocabulary and architectural contracts, ensuring that subsequent specs do not diverge from the agreed-upon design.
