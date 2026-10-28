# T019: Push the Wayfinder Skill Fix to Viello/agent-skills Main

**Status:** ready-for-agent
**Labels:** ready-for-agent
**Parent:** docs/specs/15-multi-agent-hardening-and-live-test-site.md

**What to build:** Mirror the patched wayfinder skill and worked example into the `Viello/agent-skills` repository, commit on the `agent/ticket-runner` branch, and push directly to `main` so the public catalog inherits the type-label convention.

**Jump-start:** (orientation starts here — follow the code where it leads)
- **Files/areas to touch:**
  - `D:\Repos\agent-skills\wayfinder\SKILL.md`
  - `D:\Projects\.agents\skills\wayfinder\SKILL.md`
- **Seams:** Remote repository synchronization and git push.
- **Existing-code anchors:** `docs/adr/0023-wayfinder-ticket-type-label-convention.md`, `scripts/publish_agent_skills.py`.
- **Verify:** `git diff` against upstream `main` and verify GitHub file visibility.

**Blocked by:** T014, T018

- [ ] `D:\Repos\agent-skills\wayfinder\SKILL.md` (or `.agents/skills/wayfinder/SKILL.md`) exists and matches the patched local vendor.
- [ ] Worked example ticket types file exists in the repository.
- [ ] Commit authored and pushed to `main` on `https://github.com/Viello/agent-skills`.
- [ ] Public catalog reflects the patched wayfinder skill.
