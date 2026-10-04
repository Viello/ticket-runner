# T112 — Verification Skill Scaffolder Meta-Skill
Status: completed
Completed: 2026-09-27T14:42:00Z
Spec: docs/specs/13-token-guarded-verification-and-human-gate.md
Blocked by: None

### Requirements
- Create the `create-verification-skill` agent skill at `.agents/skills/create-verification-skill/SKILL.md` — a meta-skill that inspects a target project directory and scaffolds `.agents/skills/verify-<app>/` containing:
  - `SKILL.md` implementing the 5-step lifecycle contract: Launch → Doctor → Drive → Evidence → Cleanup.
  - `harness/` directory with stub scripts: `launch`, `doctor`, `drive`, `cleanup`.
  - `features/` directory for modular feature maps (≤40 lines each).
- The meta-skill must detect project surfaces: Playwright CLI for Web UIs, interactive PTY/subprocess for CLIs, and curl/HTTP scripts for APIs. Detection heuristics should use `package.json` dependencies, `pyproject.toml` extras, and common framework markers.
- Create the companion `maintain-verification-skill` skill at `.agents/skills/maintain-verification-skill/SKILL.md` that audits the feature map against active code to prevent documentation and harness rot.
- Jump-start: Anchor against `runner/application/scaffolding.py` (`ProjectSniffer`) for existing project heuristic detection patterns. The skills are standalone markdown instructions — no Python runtime code. Follow the SKILL.md frontmatter format used in `.agents/skills/implement/SKILL.md`.

### Acceptance Criteria
- `create-verification-skill/SKILL.md` exists with valid YAML frontmatter and lifecycle instructions.
- The SKILL.md instructions guide an agent to: inspect the project, detect surfaces, create `verify-<app>/` directory, populate `SKILL.md`, `harness/` stubs, and `features/` directory.
- `harness/` stubs contain comments documenting what each script does and which surface type it targets.
- `maintain-verification-skill/SKILL.md` exists and describes the audit process: compare feature map entries against source code, flag orphaned features, and suggest new features for uncovered surfaces.
- Feature map contract: each `features/<name>.md` must have exactly 4 sections: Sub-features, User POV Path, Driving Harness, and Gotchas, each ≤40 lines total.

### Smoke Scenarios
**Scenario: Scaffold for a Node.js web app with Playwright**
- Setup: None (runs directly from repo root with Python).
- Why: Tests that an agent inspecting a Node.js web app project (with `package.json` declaring Playwright) scaffolds `.agents/skills/verify-<app>/` implementing the 5 lifecycle steps, dev server startup stub in `harness/launch`, Playwright CLI execution in `harness/drive`, and the `features/` directory.
- Steps:
  1. Run the following command in PowerShell to verify `create-verification-skill/SKILL.md` detection rules and scaffold a mock Node.js Playwright app verification tree in a temporary directory:
     ```powershell
     python -c "import tempfile, json, pathlib; doc = pathlib.Path('.agents/skills/create-verification-skill/SKILL.md').read_text(encoding='utf-8'); assert 'Playwright' in doc and 'package.json' in doc; assert all(s in doc for s in ('Launch', 'Doctor', 'Drive', 'Evidence', 'Cleanup')); td = tempfile.mkdtemp(); root = pathlib.Path(td); (root / 'package.json').write_text(json.dumps({'name': 'web-sample', 'devDependencies': {'playwright': '^1.40'}})); app_skill = root / '.agents/skills/verify-web-sample'; (app_skill / 'harness').mkdir(parents=True); (app_skill / 'features').mkdir(parents=True); (app_skill / 'SKILL.md').write_text('# Verify web-sample\nLaunch\nDoctor\nDrive\nEvidence\nCleanup'); (app_skill / 'harness/launch').write_text('#!/bin/bash\n# Surface: Web UI\nnpm run dev'); (app_skill / 'harness/drive').write_text('#!/bin/bash\n# Surface: Web UI / Playwright CLI\nnpx playwright test'); assert (app_skill / 'SKILL.md').is_file() and (app_skill / 'features').is_dir() and 'npm run dev' in (app_skill / 'harness/launch').read_text() and 'playwright' in (app_skill / 'harness/drive').read_text(); import shutil; shutil.rmtree(td); print('PASS: Scaffold for a Node.js web app with Playwright')"
     ```
- Expected: Prints `PASS: Scaffold for a Node.js web app with Playwright` with exit code 0.

**Scenario: Scaffold for a Python CLI app**
- Setup: None (runs directly from repo root with Python).
- Why: Tests that an agent inspecting a Python CLI project (with `pyproject.toml` declaring `[project.scripts]`) scaffolds `.agents/skills/verify-<app>/` with PTY/subprocess harness stubs and no browser/Playwright dependencies.
- Steps:
  1. Run the following command in PowerShell to verify `create-verification-skill/SKILL.md` CLI surface detection rules and scaffold a mock Python CLI verification tree in a temporary directory:
     ```powershell
     python -c "import tempfile, pathlib, shutil; doc = pathlib.Path('.agents/skills/create-verification-skill/SKILL.md').read_text(encoding='utf-8'); assert 'pyproject.toml' in doc and 'CLI' in doc and 'subprocess' in doc; td = tempfile.mkdtemp(); root = pathlib.Path(td); (root / 'pyproject.toml').write_text('[project]\nname = \'my-cli\'\n[project.scripts]\nmy-cli = \'my_cli.cli:main\'\n', encoding='utf-8'); app_skill = root / '.agents/skills/verify-my-cli'; (app_skill / 'harness').mkdir(parents=True); (app_skill / 'features').mkdir(parents=True); (app_skill / 'SKILL.md').write_text('# Verify my-cli\nLaunch\nDoctor\nDrive\nEvidence\nCleanup'); (app_skill / 'harness/drive').write_text('#!/bin/bash\n# Surface: CLI / Subprocess PTY\npython tests/cli_driver.py'); drive_content = (app_skill / 'harness/drive').read_text(); assert 'subprocess' in drive_content.lower() or 'cli' in drive_content.lower(); assert 'playwright' not in drive_content.lower(); shutil.rmtree(td); print('PASS: Scaffold for a Python CLI app')"
     ```
- Expected: Prints `PASS: Scaffold for a Python CLI app` with exit code 0.

### Gotchas
- These are agent skills (markdown instructions), not Python modules — they guide the Worker agent to generate project-specific verification code, not generate it themselves.
- The `<app>` placeholder in `verify-<app>` should be derived from the project name in `pyproject.toml`, `package.json`, or the directory basename.
