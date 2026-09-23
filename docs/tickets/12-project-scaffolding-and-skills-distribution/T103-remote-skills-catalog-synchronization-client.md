# T103 — Remote Skills Catalog Synchronization Client
Status: pending
Spec: docs/specs/12-project-scaffolding-and-skills-distribution.md
Blocked by: T100
Security: required
Reasoning: medium

### Requirements
- Define `SkillsClient` protocol in `runner/ports/skills_client.py`:
  - `sync_skills(project_dir: Path, repo: str = "Viello/agent-skills", ref: str = "main", force: bool = False) -> SkillsSyncResult`
  - `SkillsSyncResult`: dataclass reporting `installed_skills: tuple[str, ...]`, `updated_skills: tuple[str, ...]`, `preserved_skills: tuple[str, ...]`, `errors: tuple[str, ...]`.
- Implement concrete adapter in `runner/adapters/skills/skills_client.py`:
  - Downloads skills archive from GitHub: `https://github.com/{repo}/archive/refs/heads/{ref}.tar.gz` (with git clone fallback via `CommandRunner` if download or tar extraction fails).
  - Safe tar extraction: checks every file path in the archive to prevent Zip Slip / path traversal vulnerabilities (rejects `..` or absolute paths).
  - Extracts skill directories into `<project_dir>/.agents/skills/`.
  - Preserves custom project-specific skills: any skill folder already existing in `<project_dir>/.agents/skills/` that is not present in the incoming catalog is untouched.
  - If `force=False`, preserves existing skills that already have local modifications, or overwrites if `force=True`.
- Implement `FakeSkillsClient` in `tests/fakes/fake_skills_client.py` for deterministic in-memory testing.
- Unit tests in `tests/unit/adapters/test_skills_client.py` verifying download, extraction, path traversal defense, and preservation of custom skills.
- Jump-start:
  - Files to touch: `runner/ports/skills_client.py`, `runner/adapters/skills/skills_client.py`, `tests/fakes/fake_skills_client.py`, `tests/unit/adapters/test_skills_client.py`.
  - Seams: `SkillsClient(Protocol)`, `GitHubSkillsClient(SkillsClient)`.
  - Verification: `pytest tests/unit/adapters/test_skills_client.py`.

### Acceptance Criteria
- `GitHubSkillsClient` successfully downloads and extracts the skills catalog into `<project_dir>/.agents/skills/`.
- Pre-existing custom skills in `.agents/skills/` that do not exist in the remote catalog are completely preserved.
- Security verification: Safe tar extraction inspects member paths, immediately rejecting any entry attempting path traversal outside the target directory (Zip Slip mitigation).
- Network failures or invalid HTTP responses raise descriptive `SkillsSyncError` without corrupting existing skills directory.
- `FakeSkillsClient` correctly implements `SkillsClient` protocol for test isolation.

### Smoke Scenarios
**Scenario: Skills Catalog Synchronization and Custom Skill Preservation**
- Setup: None (runs with synthetic directory containing a custom skill).
- Why: Ensure remote skills can be downloaded and extracted while strictly preserving existing custom skills and rejecting path traversal attacks.
- Steps:
  1. Run Python script creating a mock custom skill `.agents/skills/custom-tool/SKILL.md` and executing skills synchronization:
     `python -c "import tempfile, pathlib; from runner.adapters.skills.skills_client import GitHubSkillsClient; td = pathlib.Path(tempfile.mkdtemp()); custom_skill = td / '.agents' / 'skills' / 'custom-tool'; custom_skill.mkdir(parents=True); (custom_skill / 'SKILL.md').write_text('# Custom Tool', encoding='utf-8'); client = GitHubSkillsClient(); res = client.sync_skills(project_dir=td); assert (custom_skill / 'SKILL.md').exists(); assert (td / '.agents' / 'skills' / 'implement' / 'SKILL.md').exists(); print('PASS: Skills synchronized and custom skill preserved')"`
- Expected: Custom skill is intact, standard skills are populated, and output reports `PASS: Skills synchronized and custom skill preserved`.

### Gotchas
- GitHub tarballs nest archive contents inside a root folder like `agent-skills-main/`. The extractor must strip the root directory when copying into `.agents/skills/`.
- File permissions on Windows must be handled safely when creating directories and writing `.md` files.
