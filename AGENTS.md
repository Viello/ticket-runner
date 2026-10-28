# AGENTS.md

Ticket Runner is an external Python orchestrator that drives AI coding agents (OpenCode, Antigravity CLI) through a sequential ticket queue in a Target Project. Work on this repository is interactive Human + AI pair programming, not an autonomous Runner run.

## Start here
- `STATUS.md` — active ticket, blockers, next step. Read at session start; confirm the active ticket before editing.
- `CONTEXT.md` — canonical domain terms. Use them exactly; never substitute the listed synonyms.
- `ARCHITECTURE.md` — layer boundaries and module map.
- `docs/adr/` — binding decisions. Read before contradicting; new ADRs use the next `NNNN-*.md` and the existing one-paragraph format.
- `docs/tickets/gotchas.md` — recurring pitfalls. Read before touching subprocess, Discord, prompt, or ticket-parser code.
- Load only what the task needs; don't paste these files into chat.

## Verification
Run from the repo root with the Windows launcher:
- Single test file: `py -3 -m pytest tests/unit/domain/test_runtime_paths.py -q`
- Single test: `py -3 -m pytest tests/unit/domain/test_runtime_paths.py::test_ready_signal_path_embeds_ticket_id -q`
- Changed area: `py -3 -m pytest tests/unit/<area> -q`
- Lint changed file: `py -3 -m ruff check <file>`
- Typecheck changed file: `py -3 -m mypy <file>`
- Full suite — only before commit/handoff: `py -3 -m pytest -q` (live CLI tests stay skipped unless `TICKET_RUNNER_LIVE=1`).

Ruff and mypy are dev tools configured in `pyproject.toml`; install them with `py -3 -m pip install -r requirements-dev.txt`. Their repo-wide baselines still carry legacy debt, so gate the files you changed and leave unrelated findings alone.
A green subset does not excuse a red full suite. Report unrelated failures with their test id.
Suite hangs or cascades: follow `/diagnosing-bugs` § Stuck-Test-Suite Protocol before retrying.

## Architecture
Entry points: `ticket_runner.py` (CLI), `runner/` (engine), `tests/` (pytest), `scripts/` (repo tooling), `docs/` (ADRs, specs, tickets).
- Dependencies point inward: `domain` ← `ports` ← `application` ← `adapters`. `runner/container.py` is the only composition root.
- `runner/domain/` imports stdlib and `runner.domain` only. Orchestration goes in `application/`; OS, network, and library calls go in `adapters/`.
- New capability = protocol in `runner/ports/` + adapter in `runner/adapters/<tech>/`. Call libraries through the adapter, not the interactor.
- Mirror these files: `runner/domain/runtime_paths.py` (frozen value object), `runner/ports/agent_worker.py` (protocol), `runner/adapters/opencode/opencode_worker.py` (adapter), `runner/application/state_coordinator.py` (interactor), `tests/unit/domain/test_runtime_paths.py` (unit test).
- Use `tests/fakes/` for doubles; reach for an existing fake before writing a mock.
- Known drift: some interactors still import adapters directly (`runner/application/gatekeeper.py`, `doctor.py`, `handoff_coordinator.py`). Keep new code clean; fix opportunistically when editing that file.

## Worker adapter parity
- OpenCode and Antigravity CLI are equal `AgentWorker` adapters. Changes to invocation, supervision, telemetry, model/reasoning selection, sessions, Doctor, or TUI must work on both.
- Normalize CLI differences in `runner/adapters/opencode/` and `runner/adapters/antigravity/`; keep `WorkerEvent` and `AgentWorker` adapter-neutral. Examples: `--variant` vs `--effort`, `--session` vs `--conversation`, `ses_…` vs `conversation_id` UUID.
- If one adapter truly cannot support a capability, gate it with an explicit log or fallback so the Runner keeps going.
- Agent-facing changes need tests for both `OpenCodeWorker` and `AntigravityWorker`.

## Invariants
- Agent backends (OpenCode, Antigravity CLI) are invoked as subprocesses, never daemons. Resumption uses the session id each emits (`ses_…` or `conversation_id` UUID).
- Worker implements via configured `worker.execution_skill` (defaulting to `.agents/skills/implement-ticket-runner/SKILL.md`); Worker may tick `- [ ]` to `- [x]` in `## Acceptance criteria`, while commits, ticket moves, and `docs/tickets/gotchas.md` edits stay with the Runner.
- Pre-Dispatch HITL gate: Tickets with `**Mode:** HITL` (or `**Status:** blocked`) halt before worker dispatch, transitioning to `WAITING_FOR_USER` to prompt the operator via Discord or Terminal.
- Worker ↔ Runner state is durable JSON: `.agent/signals/{ticket_id}_ready.json` and `.agent/questions/{ticket_id}.json`. State comes from those files, not model stdout.
- Only the Gatekeeper passes a ticket by running configured test/build commands. Worker self-reports don't count; 3 failed attempts trip the Circuit Breaker.
- Verification evidence stays out-of-band in `.agent/evidence/<ticket_id>/`; the Worker sees at most a 30-line / 1,000-character excerpt.
- In human mode (`lifecycle.approval_mode: "human"`), green checks produce an Evidence Card and the commit waits for human approval.
- Before signaling ready, confirm the suite is not stuck per `/diagnosing-bugs` § Stuck-Test-Suite Protocol.
- Token budget: warn 120k, handoff 135k, ceiling 150k. Handoff writes `.agent/checkpoints/{ticket_id}/handoff.md` via `.agents/skills/handoff/SKILL.md`.
- Gatekeeper approval authors exactly one commit containing code, tests, gotchas, and the relocated ticket. Ticket frontmatter records `**Status:** completed` and `**Completed:** <timestamp>`; the commit SHA stays in git.
- All automated work happens on `agent/ticket-runner`; commit locally. `.git/hooks/pre-push` blocks pushes (ADR 0005).
- `.agent/` is untracked runtime state; git-ignore it.
- Human verification runs after green checks in a human-invoked `/live-qa` session; the human records the verdict.
- Target Project paths (`.agent/`, `docs/tickets/`, `docs/specs/`, `.agents/skills/`) resolve from `--project-dir`, not from the Runner install.
- Source of truth: working code, tests, and CLI behavior are authoritative over markdown; specs and tickets are scaffolding.
- Every queue under `docs/tickets/<spec-slug>/` ends with a spec-closing alignment ticket.

## Working rules
- Interactive only: ask the user in chat. Never emit `.agent/signals/*` or `.agent/questions/*`, and never wait for a Gatekeeper in this repo.
- TDD at the agreed seam: write the failing test, run that file, implement, re-run. Don't batch untested changes.
- Commit automatically once targeted tests and `/code-review` pass. Title: `<type>(<scope>): <Title>`; `<scope>` is the layer/subsystem (`packaging`, `domain`, `ports`, `adapters`, `git`, `doctor`, `queue`, `discord`, `ui`), never a ticket number. Body: blank line, then `- imperative change` bullets; no ticket numbers, no trailing periods.
- Run `/security-review` before commit when the ticket says `Security: required` or the user asks.

## Ask first
- Install or upgrade dependencies; edit `pyproject.toml` or `requirements*.txt`.
- Change `config.example.yaml`, `config.yaml`, `.env*`, or the `DISCORD_BOT_TOKEN` contract.
- Run destructive git (`reset --hard`, `clean -fd`, `branch -D`, forced checkout), or delete/move tracked files.
- Touch protected skills (`handoff`, `claude-handoff`, `to-tickets`) or bulk-reformat `.agents/skills/`.
- Edit root living docs or `docs/tickets/gotchas.md`.

## Loop breaker
If a test or build fails twice after a fix attempt: stop editing, summarize the failing command, root cause, and evidence, and ask before a third approach. Keep the change scoped to the failing seam.

## Environment
- Target platform is Windows/PowerShell; the pre-push hook runs under Git for Windows' bundled sh. Pass subprocess argv as lists; the Windows command ceiling is 32,767 chars.
- Python >= 3.11 (local 3.14.5); use `py -3`. pytest >= 8 (local 9.1.1); `pyproject.toml` sets `testpaths=["tests"]` and `pythonpath=["."]`.
- Stack is stdlib + `discord.py` 2.x + `PyYAML` 6.x + `Rich` 15.x. No web framework, JS/TS, ORM, or database. Use `yaml.safe_load` only.
- Async tests use `@pytest.mark.anyio`; `pytest-asyncio` marks do not run here.
- `AGENTS.md` is a runtime input: `prompt_builder.extract_invariants`, `runner/tools/scaffold_sandbox.py`, and `scripts/sync_agents_md.py` read the exact `## Invariants` heading plus the `## Environment` / `## Agent skills` bullet prefixes. Keep those headings and prefixes intact.

## Agent skills
- `.agents/skills/` vendors the user's global skill catalog; `handoff`, `claude-handoff`, `to-tickets` have project-specific edits. Edit only the named skill; don't bulk-reformat or overwrite local copies with the global ones.
- `.agents/skills/handoff/SKILL.md` is load-bearing; the Runner's handoff protocol calls it by path. Keep it at that path.
- `.agents/skills/implement-ticket-runner/SKILL.md` defines the default worker implementation discipline (`worker.execution_skill`).
- `.agents/skills/implement/SKILL.md` defines the interactive Human+AI worker implementation discipline.
- `.agents/skills/security-review/SKILL.md` defines the ticket-driven security review discipline (ADR 0013).

## More detail
- Changing Target Project orchestration, evidence capture, or HITL: read `docs/ai/product-invariants.md`.
- Changing ticket lifecycle, review gates, live QA, or handoff: read `docs/ai/workflow.md`.
- Changing tests, fakes, or the full-suite policy: read `docs/ai/testing.md`.
