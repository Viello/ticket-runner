# T012: Decide: Does Each Site Need a `verify-<app>` Skill?

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/15-multi-agent-hardening-and-live-test-site.md

**What to build:** Evaluate each of the four live-test sites to decide whether each needs a dedicated `verify-<app>` skill or if `--local-only smoke` / Gatekeeper test commands are sufficient. Record the decision per site with justification and verification contracts.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `docs/agents/live-test-sites.md`
  - `.agents/skills/`
- **Seams:** Per-site verification strategy and documentation.
- **Existing-code anchors:** `docs/tickets/15-multi-agent-hardening-and-live-test-site/T011-write-docs-agents-live-test-sites.md`.
- **Verify:** Decisions recorded for all 4 sites with justifications.

**Blocked by:** T006, T008, T015

- [ ] A per-site decision recorded: site name, yes/no decision, justification, and contract if yes.
- [ ] For each `yes` site: the `verify-<app>` skill is created per the `create-verification-skill` discipline and reachable from `docs/agents/live-test-sites.md`.
- [ ] For each `no` site: a one-line justification recorded in `docs/agents/live-test-sites.md`.
