# T100 — Initialize and Publish Reusable Agent Skills Repository (Viello/agent-skills)
Status: completed
Completed: 2026-09-23T14:29:10Z
Spec: docs/specs/12-project-scaffolding-and-skills-distribution.md
Blocked by: None
Security: required
Reasoning: medium

### Requirements
- Create and publish the canonical remote repository `Viello/agent-skills` on GitHub using the GitHub CLI (`gh repo create Viello/agent-skills --public`).
- Populate the repository with the canonical reusable skills catalog:
  - Copy vendored skills from `.agents/skills/` (including `implement`, `code-review`, `security-review`, `to-tickets`, `handoff`, `diagnosing-bugs`, `clean-architecture`, `tdd`, `domain-modeling`, `codebase-design`, `software-architecture`, etc.).
  - Add a comprehensive `README.md` catalog index documenting each skill, its purpose, triggers, and installation usage.
  - Add an appropriate open-source license (MIT).
- Verify that the default branch is `main` and that the GitHub archive tarball endpoint (`https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz`) is operational and returns a valid tarball archive containing all skills.
- Author a repeatable sync/publish script (`scripts/publish_agent_skills.py` or `.ps1`) to enable easy publishing of skill updates to `Viello/agent-skills`.
- Jump-start:
  - Files to touch: `scripts/publish_agent_skills.py`, `README.md`.
  - External resources: `gh` CLI, `Viello/agent-skills`.
  - Seams: `.agents/skills/` source directory, GitHub API / remote git repository.
  - Verification: `gh repo view Viello/agent-skills`, `curl -sL https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz -o test_skills.tar.gz`.

### Acceptance Criteria
- Remote GitHub repository `Viello/agent-skills` exists and is publicly accessible.
- Repository contains the canonical skills catalog with valid `SKILL.md` files under respective skill directories.
- `README.md` at repository root indexes all available skills.
- The GitHub tarball archive at `https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz` downloads successfully and extracts valid skill directories.
- Security verification: Repository publication validates authentication tokens, uses standard HTTPS endpoints, and prevents leaking local environment credentials or secrets.

### Smoke Scenarios
**Scenario: Verify Remote Agent Skills Repository and Tarball Endpoint**
- Setup: None (runs from repo root with GitHub CLI `gh` authenticated as `Viello`).
- Why: Confirm that the canonical `Viello/agent-skills` repository is publicly accessible on GitHub and that its source tarball can be fetched and parsed by downstream tools.
- Steps:
  1. Inspect remote repository status:
     `gh repo view Viello/agent-skills --json name,url,isPrivate,defaultBranchRef`
  2. Download and verify the archive tarball in Python:
     `python -c "import urllib.request, tarfile, io; data = urllib.request.urlopen('https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz').read(); tf = tarfile.open(fileobj=io.BytesIO(data)); names = tf.getnames(); assert any('implement/SKILL.md' in n for n in names); print('PASS: Downloaded valid skills tarball with', len(names), 'entries')"`
  3. Run the publication script idempotency check:
     `python scripts/publish_agent_skills.py`
- Expected:
  - Step 1 outputs `{"defaultBranchRef":{"name":"main"},"isPrivate":false,"name":"agent-skills","url":"https://github.com/Viello/agent-skills"}`.
  - Step 2 outputs `PASS: Downloaded valid skills tarball with 194 entries`.
  - Step 3 reports `PASS: Tarball verified with 194 archive entries.` and `Remote repository is already completely up to date. No changes to commit.`

### Gotchas
- When creating the repo via `gh repo create`, ensure working in a clean temporary directory or using `--source` carefully so that the parent Ticket Runner git repository is not linked or modified.
