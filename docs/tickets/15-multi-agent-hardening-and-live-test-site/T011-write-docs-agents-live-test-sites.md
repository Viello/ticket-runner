# T011: Write `docs/agents/live-test-sites.md`

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/15-multi-agent-hardening-and-live-test-site.md

**What to build:** Document the four live-test sites (external sandbox, in-repo harness, agent-skills driver, empty starter) in a single reference file `docs/agents/live-test-sites.md` to serve as the entry point for operators and agents. Frame the external sandbox as the user-facing onboarding site and the others for diagnostics and integration testing. Include install hints for `agy` and `opencode` and cross-links from `AGENTS.md` and `README.md`.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `docs/agents/live-test-sites.md`
  - `AGENTS.md`
  - `README.md`
- **Seams:** Documentation reference and cross-links.
- **Existing-code anchors:** `docs/adr/0023-wayfinder-ticket-type-label-convention.md`, `runner/tools/scaffold_sandbox.py`.
- **Verify:** Confirm file exists, sections 1–6 complete, and cross-links resolve.

**Blocked by:** T006, T008, T010, T015

- [ ] `docs/agents/live-test-sites.md` exists and covers all four sites (external sandbox, in-repo harness, agent-skills driver, empty starter).
- [ ] The External sandbox section is framed for a first-time user, with install hints for the worker binary (`AGENT_ANTIGRAVITY_BIN` / `AGENT_OPENCODE_BIN`).
- [ ] The decision matrix section is concrete enough to answer "which site should I use for X?" for at least five common scenarios, including "I'm trying Ticket Runner for the first time" → External sandbox.
- [ ] Cross-links from `AGENTS.md` and `README.md` resolve correctly.
