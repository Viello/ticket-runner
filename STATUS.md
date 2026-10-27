---
project: ticket-runner
last_updated: 2026-10-25T21:30:00
author: Gab
branch: agent/ticket-runner
active_ticket: T121-unify-antigravity-token-occupancy-and-ready-signal-precedence
status: in_progress
stopped_at:
  file: "D:/Projects/docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation/T121-unify-antigravity-token-occupancy-and-ready-signal-precedence.md"
  symbol: "T120 completed; ready to execute T121"
---

# Project Status: ticket-runner

## ⚡ Quick Resume (4-Bullet Briefing)
- **Focus**: Implement Spec 16 (`16-live-run-gatekeeper-and-antigravity-telemetry-remediation` — `T120` → `T123`) to remediate the three architectural defects surfaced during the live `orchestrate-runner` `T101` run against `D:\Repos\agent-skills` (`cmd.exe /d /s /c` quote escaping, Antigravity per-step context occupancy & ready-signal precedence, and autonomous `docs/tickets/` ownership), then sanitize `D:\Repos\agent-skills` and re-run `T101` → `T102`.
- **Last Touchpoint**: [`docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation/`](file:///D:/Projects/docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation) (`T120`–`T123` authored and verified via `DirectoryTicketStore.list_pending`) from [`docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md`](file:///D:/Projects/docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md) on branch `agent/ticket-runner`.
- **Blockers**: Three live-run remediation slices (`T120`, `T121`, `T122`) and Target Project sanitization (`T123`) must land before re-running `start --local-only` on `D:\Repos\agent-skills`.
- **Next Step**: Execute `T120` (`T120-preserve-windows-shell-quoting-in-gatekeeper-commands.md`), `T121` (`T121-unify-antigravity-token-occupancy-and-ready-signal-precedence.md`), `T122` (`T122-enforce-gatekeeper-ticket-ownership-and-idempotent-finalization.md`), and `T123` (`T123-sanitize-target-project-and-audit-spec-16-alignment.md`), then re-run `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only` in a real console.

## 🎯 Active Tickets & Progress
- [ ] `Spec 16 Queue` (`16-live-run-gatekeeper-and-antigravity-telemetry-remediation`): Remediate live-run Gatekeeper shell quoting, Antigravity telemetry parity, and autonomous ticket boundary ownership
  - Context / Spec: [docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md](file:///D:/Projects/docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md)
  - Subtasks:
    - [x] Author and settle Spec 16 (`docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md`)
    - [x] Decompose Spec 16 into tracer-bullet tickets (`T120`–`T123`) under `docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation/`
    - [x] `T120`: Preserve Windows shell quoting in Gatekeeper verification commands (`SubprocessRunner`, `GatekeeperCommandExecutor`; `Security: required`)
    - [ ] `T121`: Unify Antigravity token occupancy, stall heartbeat, and ready-signal precedence (`AntigravityWorker`, `WorkerSupervisor`, `HandoffCoordinator`)
    - [ ] `T122`: Enforce Gatekeeper ownership of `docs/tickets/` and idempotent ticket finalization (`.agents/skills/implement/SKILL.md`, `PromptBuilder`, `DirectoryTicketStore`)
    - [ ] `T123`: Sanitize `agent-skills` Target Project (`6912328` baseline + synced `implement/SKILL.md`) and audit Spec 16 alignment (`tests/specs/test_spec_16_live_run_remediation.py`, `AGENTS.md`, `gotchas.md`)
- [ ] `orchestrate-runner-first-run`: Execute the canonical first-run sequence (Phases 1–9) against `D:\Repos\agent-skills` — **PAUSED pending Spec 16 (`T120`–`T123`)**
  - Context / Spec: `D:\Repos\agent-skills\docs\specs\orchestrate-runner.md`
  - Investigation: `docs/tickets/gotchas_prompt_swallowed_under_live_display.md`
  - Subtasks:
    - [x] Phases 1–4 environment verification, Doctor 11/11 green, pre-flight predictions (`observations/T101.md` + `T102.md`)
    - [x] Fix startup & live-run blockers A–F + `agy` `--model`/`--effort` normalizer + Rich Live display pause guards (`b1bf1d2`)
    - [x] Live run 2 executed with Overseer monitoring → Worker authored all 8 missing `*/agents/openai.yaml` files (37 → 45), surfacing the 3 Spec 16 defects (Windows `cmd.exe /c` quote corruption, inert Antigravity telemetry / cumulative `result.usage`, and premature Worker `completed/` move)
    - [ ] Complete Spec 16 (`T120`–`T123`) and re-run Phases 5–9 on clean `D:\Repos\agent-skills`

## 🚧 Exact Work-In-Progress
- **Branch**: `agent/ticket-runner` (both `D:\Projects` and `D:\Repos\agent-skills`)
- **Uncommitted Files**:
  - `docs/specs/16-live-run-gatekeeper-and-antigravity-telemetry-remediation.md`: Settled Spec 16 specification
  - `docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation/`: `T120`–`T123` ticket queue and `completed/.gitkeep`
- **Last Stopped At**: `docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation/T120-preserve-windows-shell-quoting-in-gatekeeper-commands.md` — ticket queue written and verified via `DirectoryTicketStore`.

## 📦 Recent Completed Work & Key Decisions
- **Spec 16 Decomposed into `T120`–`T123` (2026-10-25)**:
  - `T120-preserve-windows-shell-quoting-in-gatekeeper-commands.md` (`Blocked by: None`, `Security: required`)
  - `T121-unify-antigravity-token-occupancy-and-ready-signal-precedence.md` (`Blocked by: None`)
  - `T122-enforce-gatekeeper-ticket-ownership-and-idempotent-finalization.md` (`Blocked by: None`)
  - `T123-sanitize-target-project-and-audit-spec-16-alignment.md` (`Blocked by: T120, T121, T122`)
- **`agy` model/effort normalizer and Rich Live display pause guards landed (`b1bf1d2`)**:
  - Normalized embedded effort suffixes (`-high`, `-medium`, `-low`, `-xhigh`, `-max`) in `build_antigravity_run_command` when both `model_id` and `variant` are present.
  - Added `paused_display` context manager across `TerminalInterventionGateway`, `HandoffCoordinator`, and `TerminalApprovalAdapter`.

## ⚠️ Blockers & Gotchas
- **Windows `cmd.exe /d /s /c` Quote Corruption (`T120`)**: `asyncio.create_subprocess_exec` passes `cmd.exe` args through `subprocess.list2cmdline`, turning `"` into `\"`, which `cmd.exe` does not unescape.
- **Antigravity Per-Step Occupancy vs. Cumulative `result.usage` (`T121`)**: `step_update.usage.total_tokens` omits `cache_read_tokens` (~35k tokens), while `result.usage` sums across all steps in the turn (~174.6k `total_tokens` on a 39.7k context window). Also, a valid `.agent/signals/<ticket_id>_ready.json` on disk must take precedence over late `KILLED_HANDOFF` / `KILLED_CEILING` triggers.
- **Autonomous `docs/tickets/` Ownership (`T122`)**: `.agents/skills/implement/SKILL.md` Step 4 must be scoped to interactive mode only so autonomous Workers leave ticket relocation and `docs/tickets/gotchas.md` updates to the Gatekeeper.
- **Dirty `D:\Repos\agent-skills` Tree (`T123`)**: Before re-running `T101` → `T102`, `D:\Repos\agent-skills` must be reset to `6912328` with `.agents/skills/implement/SKILL.md` synchronized and stale `.agent/` state removed.

## ⏭️ Next 1–3 Actionable Steps
1. `Implement T120–T122`: Execute the three frontier tickets in `docs/tickets/16-live-run-gatekeeper-and-antigravity-telemetry-remediation/` (`T120` Windows shell quoting, `T121` Antigravity telemetry & ready-signal precedence, `T122` autonomous ticket ownership & idempotent `finalize_completed`).
2. `Execute T123`: Sync `.agents/skills/implement/SKILL.md` to `D:\Repos\agent-skills`, sanitize `D:\Repos\agent-skills` back to `6912328`, add `tests/specs/test_spec_16_live_run_remediation.py`, and complete the Spec 16 alignment audit.
3. `Re-run the live sequence (human-gated)`: Run `py -3 D:\Projects\ticket_runner.py --project-dir D:\Repos\agent-skills start --local-only` in an interactive console, `[y]` per Evidence Card (`T101` → `T102`), and complete Phases 6–9 (`observations/T101.md`, `T102.md`, `debug-report.md`, `/live-qa`).
