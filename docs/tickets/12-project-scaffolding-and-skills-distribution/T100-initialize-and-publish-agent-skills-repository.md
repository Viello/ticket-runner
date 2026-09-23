# T100 — Initialize and Publish Reusable Agent Skills Repository (Viello/agent-skills)
Status: pending
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
- Setup: GitHub CLI (`gh`) authenticated with repository permissions for account `Viello`.
- Why: Ensure the remote skills catalog exists on GitHub and provides a downloadable tarball archive for downstream runners and projects to synchronize.
- Steps:
  1. Inspect remote repository status:
     `gh repo view Viello/agent-skills --json name,url,isPrivate,defaultBranchRef`
  2. Download the tarball archive:
     `python -c "import urllib.request, tarfile, io; data = urllib.request.urlopen('https://github.com/Viello/agent-skills/archive/refs/heads/main.tar.gz').read(); tf = tarfile.open(fileobj=io.BytesIO(data)); names = tf.getnames(); assert any('implement/SKILL.md' in n for n in names); print('PASS: Downloaded valid skills tarball with', len(names), 'entries')"`
- Expected: Repository is found, `isPrivate` is false, default branch is `main`, and the tarball archive contains canonical skills like `implement/SKILL.md`.

### Gotchas
- When creating the repo via `gh repo create`, ensure working in a clean temporary directory or using `--source` carefully so that the parent Ticket Runner git repository is not linked or modified.
