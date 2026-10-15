---
project: ticket-runner
last_updated: 2026-10-16T00:28:31
author: Gab
branch: agent/ticket-runner
active_ticket: orchestrate-runner-first-run
status: paused
stopped_at:
  file: "D:/Repos/agent-skills/ticket-runner.yaml"
  symbol: "model.models (Doctor requires >=1 model; agy models probe pending)"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Execute the `orchestrate-runner` first-run sequence against `D:\Repos\agent-skills` (T101 → T102). This session: Blocker A **fixed and committed** (`16b2785` — human mode now defaults to `TerminalApprovalAdapter` in `build_container`; full suite green) and the target **prepared and committed** (`18b2176` — overlay, `.agents/skills/` provisioning, spec move, scaffold commit). Doctor now passes env/git/queue/config but fails the **new model check**: `model.models: []` violates Doctor's ≥1-model rule (`doctor.py:583`); one agy-valid slug is required.
- **Last Touchpoint**: `D:\Repos\agent-skills\ticket-runner.yaml` → `model:` block, with the `agy models` probe interrupted by the session pause. Both repos clean on `agent/ticket-runner` (`D:\Projects` `16b2785`; clone `18b2176`).
- **Blockers**: (1) **Blocker C** — Doctor model check: land one agy-valid model slug in the overlay, commit in the clone, Doctor all-green; (2) `start` remains human-interactive-console-only (HITL); (3) minor: superseded observer-protocol plan file still to delete
- **Next Step**: `agy models` → single slug in the overlay → commit in the clone → `doctor --local-only` green → Phase-4 predictions (`observations/T101.md`, `T102.md`) → interactive `start --local-only`

## 🎯 Active Tickets & Progress
- [ ] `orchestrate-runner-first-run`: Execute the canonical first-run sequence (Phases 1–9) against `D:\Repos\agent-skills` — **PAUSED pre-flight; target prepared**
  - Context / Spec: `D:\Repos\agent-skills\docs\specs\orchestrate-runner.md` (moved to canonical home this session)
  - Handoff: `C:\Users\Acer\AppData\Local\Temp\opencode\handoff-orchestrate-runner-first-run-target-prepared.md`
  - Subtasks:
    - [x] Phase 1 environment verification (branch, `agy` path, `.agent` writable + ignored, overlay loads, queue, clean tree, 37-file pre-T101 state)
    - [x] Discover + reproduce Blocker A (HITL approval gate unwired: `ticket_runner.py:456` → `container.py:291` → `gatekeeper.py:1107`)
    - [x] Fix Blocker A: terminal approval gateway default in `build_container` + regression test — committed `16b2785`; full suite 1892 passed / 3 skipped; two-axis review done (Away-mode Discord unwired = separate future work)
    - [x] Blocker B resolved: `.agents/skills/` provisioned (targeted copies of `implement`, `code-review`, `diagnosing-bugs`, `handoff`, `security-review`, each stripped of its `agents/` subfolder — keeps T101's recursive `openai.yaml` count measurable; baseline 37 verified)
    - [x] Overlay edits applied (`provider: antigravity`; `lifecycle.approval_mode: human`; `model.models: []` — model entry **now pending re-fix**, see Blocker C)
    - [x] Spec moved to `D:\Repos\agent-skills\docs\specs\orchestrate-runner.md`; scaffold committed in clone `18b2176` (docs/, overlay, `.gitignore` += `.agents/` + `observations/`); clone tree clean
    - [ ] NEW (**Blocker C**): replace `models: []` with one agy-valid model slug; commit in clone; `doctor --local-only` all green
    - [ ] Phase 4 by hand (+ `observations/T101.md` / `T102.md` predictions)
    - [ ] Phases 5–6 `start --local-only` in an interactive console (HITL `[y]` per Evidence Card)
    - [ ] Phases 7–9 post-mortem, `/live-qa`, cleanup
- [ ] `env-prep-agent-skills`: Prepare `D:\Repos\agent-skills` to run the seeded demo queue — NO TICKET (session work)
  - Context / Spec: `D:\Repos\agent-runner-driver\docs\specs\01-runner-live-test-bootstrap.md`
  - Subtasks:
    - [x] Scaffold clone via `init --yes --no-skills` (avoids clobbering the catalog source)
    - [x] Restore `.gitignore` (removed scaffolder's BOM-induced duplicate `.agent/` line)
    - [x] Prune scaffolder noise: `docs/tickets/00-welcome/`, `src/`, `tests/`, generated `AGENTS.md`
    - [x] One-time copy of spec + T101/T102 into the clone's `docs/specs/` + `docs/tickets/01-runner-live-test-bootstrap/`
    - [x] Override `test_cmd` (schema forbids empty; `python -m pytest` exits 5 with no tests) → YAML-integrity one-liner
    - [x] Decide worker provider → `antigravity` (settled; overlay applied and committed in `18b2176`)
    - [ ] Run `doctor --local-only`, then `start --local-only` — carried into `orchestrate-runner-first-run` (paused pre-flight)
- [x] `T017-seed-demo-ticket-queue`: Seed the demo ticket queue (conditional) — CLOSED via `ec2c590`
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T017-seed-demo-ticket-queue.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T017-seed-demo-ticket-queue.md)
  - Subtasks:
    - [x] Author 1-paragraph spec at `D:\Repos\agent-runner-driver\docs\specs\01-runner-live-test-bootstrap.md`
    - [x] Author 2 demo tickets under `D:\Repos\agent-runner-driver\docs\tickets\01-runner-live-test-bootstrap\`
    - [x] Demo tickets carry standard sections + no T<NNN> in H1 titles + standard tags
    - [x] Seed tickets describe real catalog hygiene gaps observed at chart-time (not Round-1 stale candidates)
    - [x] Initialize driver-local gotchas log capturing cluster-layout reconciliation + Unicode-tree discipline
    - [x] Demo tickets `pending`; execution is the user's decision in a subsequent session
- [x] `T016-decide-starter-ticket-queue-and-publish-migration`: Decide starter ticket queue and publish-script migration — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T016-decide-starter-ticket-queue-and-publish-migration.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T016-decide-starter-ticket-queue-and-publish-migration.md)
  - Subtasks:
    - [x] Decide starter-queue option: **Yes** — pre-seed 2 demo tickets in driver under `01-runner-live-test-bootstrap`
    - [x] Decide publication script: **Coexist** — keep `scripts/publish_agent_skills.py`; no relocation follow-up
    - [x] Decide queue location: **Driver** — `D:\Repos\agent-runner-driver\docs\tickets\01-runner-live-test-bootstrap\`
    - [x] Decide spec file: **Yes** — 1-paragraph spec alongside the queue scaffold
    - [x] Reconcile prior cluster-layout discipline: bootstrap `--project-dir` indirection preserves the spirit; prior ticket stays as historical record
    - [x] Defer specific ticket content to next ticket in chain (Round-1 candidates partly stale)
- [x] `T022-fix-doctor-provider-resolution`: Fix Doctor worker-provider resolution under single-tier config load — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T022-fix-doctor-provider-resolution.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T022-fix-doctor-provider-resolution.md)
  - Subtasks:
    - [x] Resolve provider from merged two-tier config in `Doctor._check_worker_binary`
    - [x] Avoid swallowing load errors into silent `opencode` default
    - [x] Update `runner/tools/scaffold_sandbox.py` template with `discord.token_env` default
    - [x] Add regression tests in `tests/unit/application/test_doctor.py`
- [x] `T015-scaffold-agent-runner-driver`: Scaffold the Agent-Skills Driver Minimal Stub — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T015-scaffold-agent-runner-driver.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T015-scaffold-agent-runner-driver.md)
  - Subtasks:
    - [x] Create `D:\Repos\agent-runner-driver\` directory
    - [x] Initialize git repo on branch `agent/ticket-runner`
    - [x] Install pre-push guardrail hook
    - [x] Add defensive `.gitignore`
    - [x] Author `scripts/start.ps1` targeting `--project-dir D:\Repos\agent-skills`
    - [x] Commit initial scaffold `6214c1e`
- [x] `T014-clone-viello-agent-skills-and-install-pre-push`: Clone Viello/agent-skills and install pre-push hook — CLOSED
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T014-clone-viello-agent-skills-and-install-pre-push.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T014-clone-viello-agent-skills-and-install-pre-push.md)
  - Subtasks:
    - [x] Clone `https://github.com/Viello/agent-skills` into `D:\Repos\agent-skills` (HEAD `727a94f`)
    - [x] Create and checkout branch `agent/ticket-runner`
    - [x] Install standalone pre-push guardrail hook into `.git/hooks/pre-push`
    - [x] Add `.gitignore` covering `.agent/` and `docs/tickets/.queue.lock`
    - [x] Verify smoke scenario: push attempt blocked by pre-push hook
- [x] `T013-lock-agent-skills-cluster-layout`: Lock Agent-Skills Cluster Layout — CLOSED via `aa3bd9c`
  - Context / Spec: [docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T013-lock-agent-skills-cluster-layout.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/completed/T013-lock-agent-skills-cluster-layout.md)
  - Subtasks:
    - [x] Decide GitHub remotes and driver-to-skills layout (driver = no remote, skills clone = real clone)
    - [x] Decide branch and pre-push hook conventions (`agent/ticket-runner` + `DEFAULT_STANDALONE_HOOK` on both)
    - [x] Decide worker.provider for driver overlay (`antigravity`; locked; CLI-only `--project-dir`)
    - [x] Decide parent `D:\Repos\` hygiene (5-line README; cluster index)
    - [x] Decide discipline rule (driver carries no file the runner parses)
    - [x] Decide D:\Repos\agent-runner-driver\ scripts/start.ps1 as canonical bootstrap

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner` (both `D:\Projects` — HEAD `16b2785` — and `D:\Repos\agent-skills` — HEAD `18b2176`)
- **Uncommitted Files**: `D:\Projects`: only `STATUS.md` (this refresh — committed with this update). `D:\Repos\agent-skills`: clean; runtime state (`.agent/`, `.agents/`, `observations/`) is gitignored
- **Last Stopped At**: `D:\Repos\agent-skills\ticket-runner.yaml` → `model:` block (needs one agy-valid slug; the `agy models` probe was interrupted by the pause). Handoff: `C:\Users\Acer\AppData\Local\Temp\opencode\handoff-orchestrate-runner-first-run-target-prepared.md`

## 📦 Recent Completed Work & Key Decisions
- **orchestrate-runner first-run target preparation (this session)**: Fixed Blocker A in `D:\Projects` — human mode now defaults to `TerminalApprovalAdapter` in `build_container` when no gateway is injected (autonomous stays `None`; injected gateways win), with a regression test matching the container suite's style. Full suite 1892 passed / 3 skipped; committed `16b2785`. Prepared `D:\Repos\agent-skills` per user-approved plan: overlay edited to `provider: antigravity` + `lifecycle.approval_mode: human` + `model.models: []` (two-tier load verified); `.agents/skills/` provisioned via targeted copies of `implement`, `code-review`, `diagnosing-bugs`, `handoff`, `security-review` **with each skill's `agents/` subfolder stripped** (keeps T101's recursive `openai.yaml` acceptance count measurable — baseline 37 re-verified, 0 under `.agents/`); `.gitignore` += `.agents/` + `observations/` (BOM/CRLF preserved); spec moved to `docs/specs/orchestrate-runner.md`; scaffold committed `18b2176` so Doctor's clean-tree check passes. Doctor progressed to a **new blocker**: `check_model` unconditionally requires ≥1 `model.models` entry (`doctor.py:583–616`) — `models: []` fails; resolution needs one agy-valid slug (see Blockers). Model resolution facts for the fix: exactly 1 configured model → silent auto-select and `--model <slug>` is passed to `agy` (`antigravity_worker.py:105–110`); unknown slug → agy exit 1.
- **orchestrate-runner first-run (prior session)**: Resumed the canonical sequence; Phase 1 verification green (target branch, `agy` path, `.agent` writable + ignored, overlay loads, T101/T102 queue, 37-file pre-T101 state, README anatomy block at `README.md:87`). Discovered and empirically reproduced **Blocker A**: no production path constructs an `ApprovalGateway` — `run_start` builds the container without one (`ticket_runner.py:456`), `container.py:291` resolves `None`, and `gatekeeper.py:1107` fail-closes at the first green check in human mode (so `start --local-only` would abort in human mode or commit without cards in autonomous mode). Also found **Blocker B**: the `--no-skills` scaffold left the target without `.agents/skills/`, so Doctor's `skills` check will fail (`implement`, `code-review`, `diagnosing-bugs` required). Per user decision: **no Runner edits, no execution — session paused**; decided by-hand protocol invocation (Skill file remains future work) and spec home `D:\Repos\agent-skills\docs\specs\`. Full details: `C:\Users\Acer\AppData\Local\Temp\opencode\handoff-orchestrate-runner-first-run-paused.md`.
- **env-prep-agent-skills (prior session)**: Prepared `D:\Repos\agent-skills` to execute the seeded T101/T102 queue. Ran `ticket_runner.py init --yes --no-skills` (skills sync suppressed so the catalog source isn't clobbered). Restored `.gitignore` after the scaffolder appended a duplicate `.agent/` (a BOM on line 1 defeated its dedupe check). Pruned `00-welcome/`, `src/`, `tests/`, and the generated `AGENTS.md` (the Runner preamble is irrelevant to a markdown/YAML catalog). One-time copied the spec + T101/T102 into the clone (the spec copy is required because tickets reference `docs/specs/01-runner-live-test-bootstrap.md` relative to the target root). Overrode `test_cmd`: the schema forbids an empty value and the scaffolder's `python -m pytest` exits 5 with no tests, so it was replaced with a YAML-integrity one-liner (`python -c "... yaml.safe_load over */agents/openai.yaml ..."`), verified live to validate 37 files at exit 0 and resolve its leading token on PATH. **No ticket execution, no commits.** Full details: `C:\Users\Acer\AppData\Local\Temp\opencode\handoff-agent-skills-runner-setup.md`.
- **b38c2c5**: Formatted [T000-wayfinder-map.md](file:///d:/Projects/docs/tickets/15-multi-agent-hardening-and-live-test-site/T000-wayfinder-map.md) with `# T000 — Multi-Agent Hardening & External Live-Test Site` and `Status: completed` metadata; formatted driver demo tickets [T101](file:///D:/Repos/agent-runner-driver/docs/tickets/01-runner-live-test-bootstrap/T101-add-codex-interface-metadata-to-skills-lacking-it.md) and [T102](file:///D:/Repos/agent-runner-driver/docs/tickets/01-runner-live-test-bootstrap/T102-document-agents-openai-yaml-in-skill-anatomy.md) with standard `# T<NNN> — <Title>` headers. Unblocked queue verification across Doctor and Ticket Store parsers.
- **T017**: Seeded the live-test bootstrap spec (`D:\Repos\agent-runner-driver\docs\specs\01-runner-live-test-bootstrap.md`) and 2 demo tickets under `D:\Repos\agent-runner-driver\docs\tickets\01-runner-live-test-bootstrap\` (`T101` adds `agents/openai.yaml` to 8 catalog skills lacking it; `T102` documents the interface file in the catalog anatomy README block). Both H1s are T<NNN>-free per the demo-ticket title constraint; both carry standard wayfinder sections; both target real chart-time catalog hygiene (8 of 45 skills missing Codex interface metadata; README silent on `agents/`). Initialized driver-local `docs/tickets/gotchas.md` with the cluster-layout reconciliation narrative and the Unicode-tree-character discipline. Demo tickets are seeded (not executed) — execution is the next step. Driver commit landed at `9af978e`; runner-source relocation at `ec2c590`.
- **T016**: Decided starter-queue (yes, 2 demo tickets in driver under `01-runner-live-test-bootstrap`) and publication-script (coexist, no follow-up). Reconciled prior cluster-layout discipline via bootstrap `--project-dir` indirection (driver's `docs/tickets/` permitted as a queue home; runner never reads it). Authored 1-paragraph spec alongside queue scaffold (per agent-guidelines pattern). Defer specific ticket content to next ticket in chain.
- **T022**: Resolved Doctor worker-provider resolution by unifying configuration loading in `Doctor._load_configuration` with two-tier resolution (`load_two_tier`). Suppressed silent `"opencode"` fallback on unloadable configs so errors surface via `check_config` without masquerading as valid providers. Added `discord.token_env: "DISCORD_BOT_TOKEN"` default to sandbox template and added regression tests in `tests/unit/application/test_doctor.py`. Verified on `D:\Sandbox\ticket-runner-live-target` and `D:\Projects\live-test-target`.
- **T015**: Scaffolded `D:\Repos\agent-runner-driver\` minimal stub (`git init -b main`, branch `agent/ticket-runner`, pre-push hook, defensive `.gitignore`, and `scripts/start.ps1` / `scripts/start.bat` pointing `--project-dir D:\Repos\agent-skills`). Root scaffold commit authored as `6214c1e`.
- **T014**: Cloned `Viello/agent-skills` into `D:\Repos\agent-skills\`, checked out `agent/ticket-runner`, installed pre-push guardrail, added `.gitignore` (`.agent/`, `docs/tickets/.queue.lock`), and verified push blocking. Upstream HEAD recorded as `727a94f70cad35438cd89ccb896174b44f2ff38a`.
- **aa3bd9c**: Lock agent-skills cluster layout and amend driver scaffold — T013 relocated to `completed/`, T015 amended to minimal-stub shape, gotcha + STATUS synced
- **T013 Resolution**: `D:\Repos\agent-runner-driver\` = minimal invocation stub (git + pre-push + `.gitignore` + `scripts/start.ps1`; no `ticket-runner.yaml`, no `.agent/`; `docs/tickets/` permitted per the live-test queue decision); `D:\Repos\agent-skills\` = real clone of `Viello/agent-skills` on `agent/ticket-runner` with `.agent/` & `docs/tickets/.queue.lock` added to `.gitignore` only if upstream doesn't already cover; `D:\Repos\README.md` = 5-line cluster index. Provider: `antigravity`. Bootstrap: `pwsh D:\Repos\agent-runner-driver\scripts/start.ps1` (or `scripts/start.bat`). `scripts/publish_agent_skills.py`: **Coexist** (decided via the live-test queue ticket; script remains manual bulk-reset path).
- **cc14f8b**: Lock empty-starter design, add session orienting rule, and track STATUS.md
- **c080555**: Add status skill and integrate session status tracking into retro and handoff
- **cb0a0f0**: Scaffold runnable artifacts from init (`AGENTS.md`, welcome ticket, sample app, smoke test)
- **039b1d0**: Create empty starter fresh-slate target at `D:\Repos\empty-starter` (T010)

## ⚠️ Blockers & Gotchas
- **Blocker C — Doctor requires ≥1 model (OPEN — the pause reason)**: `check_model` (`doctor.py:583–616`) unconditionally fails when `model.models` is empty; the queued `models: []` (chosen to avoid the machine-default two-model prompt and a bogus `--model` passthrough) cannot pass. Resolution: pick one agy-valid slug (run `agy models`; the probe was interrupted by the pause), commit it in the clone, re-run Doctor. Exactly 1 configured model → silent auto-select, and `--model <slug>` is passed to `agy` (`antigravity_worker.py:105–110`); unknown slug → agy exits 1 (T002).
- **Blocker A — HITL approval gate unwired: RESOLVED** (`16b2785`). Human mode now builds a default `TerminalApprovalAdapter` when no gateway is injected (injected gateways still win; autonomous stays `None`); regression test `test_build_container_human_mode_defaults_terminal_approval_gateway`. Discord/away-mode approval remains unwired — separate future work (recorded by the standards review; not a regression).
- **Blocker B — target `.agents/skills/` missing: RESOLVED**. Provisioned via targeted copies of `implement`, `code-review`, `diagnosing-bugs`, `handoff`, `security-review`, each stripped of its `agents/` subfolder (keeps T101's recursive `openai.yaml` count measurable). Doctor `check_skills` requires `implement` (from `worker.execution_skill`) + `code-review` + `diagnosing-bugs`; the Worker prompt (`prompt_builder.py:170`) also reads `.agents/skills/implement/SKILL.md`.
- **`start` requires an interactive console (HITL)**: terminal approval reads raw keys via `msvcrt` + `isatty`; piped/background shells fail closed (and REJECT loops burn verification attempts). The human runs `start --local-only`; the orchestrator observes `.agent/`.
- **Doctor check order matters**: the git-clean-tree check (`doctor.py:484`) halts **before** skills; the target tree must be committed-clean before every Doctor run (scaffold committed as `18b2176`; the Blocker-C overlay fix needs its own small commit in the clone).
- **Gatekeeper commits with `git add .`** (`git_operations.py:214`): target runtime dirs must stay gitignored — `.agent/`, `.agents/`, `observations/` all verified ignored via `git check-ignore`.
- **Worker-provider mismatch: RESOLVED** — overlay now `provider: antigravity` (committed `18b2176`).
- **`test_cmd` cannot be empty**: `runner/domain/config.py:64` raises `ConfigError` on a blank `test_cmd`. The scaffolder default `python -m pytest` exits **5** ("no tests ran") on this catalog — the Gatekeeper treats nonzero as failure (`gatekeeper.py:262`). Current value is a YAML-integrity one-liner (validates `*/agents/openai.yaml`).
- **`init` has a BOM bug**: on a `.gitignore` whose first line carries a UTF-8 BOM, the dedupe check (`scaffolder.py:176–184`) fails and appends a duplicate `.agent/`. Fix is `git checkout -- .gitignore` (done). Possible upstream bug worth a ticket.
- **Spec 15 spec file is missing**: every ticket in `docs/tickets/15-multi-agent-hardening-and-live-test-site/` references `docs/specs/15-multi-agent-hardening-and-live-test-site.md` which does not exist; the de facto spec lives at `T000-wayfinder-map.md`. ADR-0011 spec-context-excerpt injection would FileNotFoundError on every Spec-15 Worker prompt. T099 owns this fix.
- `scripts/start.ps1` (per T013 resolution) requires `pwsh` (PowerShell 7); boxes with only `powershell.exe` 5.1 will fail silently. Consider dual `scripts/start.bat` fallback or a pure-Python `scripts/start.py`.
- Never `git push` on `agent/ticket-runner` — pre-push hook is installed.
- All external path resolution inside `.agent/`, `docs/tickets/`, `ticket-runner.yaml` resolves relative to Target Project root.

## ⏭️ Next 1–3 Actionable Steps
1. `Resolve Blocker C`: run `& C:\Users\Acer\AppData\Local\agy\bin\agy.exe models` → set exactly one valid slug in `D:\Repos\agent-skills\ticket-runner.yaml` → commit in the clone → `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills doctor --local-only` until all green.
2. `Phase 4 (by hand)`: run the enumerated pre-flight checks and write `observations/T101.md` + `observations/T102.md` (single-file form; Prediction populated, Observation empty; note the spec's `*_prediction.md` discrepancy for the post-mortem).
3. `Resume the run`: human runs `start --local-only` in an interactive console (HITL `[y]` at each Evidence Card) while the orchestrator observes `.agent/` and maintains the observation MDs → post-mortem (`observations/debug-report.md`) → `/live-qa` → cleanup.
