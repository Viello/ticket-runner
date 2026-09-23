# T112 — Verification Skill Scaffolder Meta-Skill
Status: pending
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
- Setup: Create a temp directory with `package.json` containing `"playwright"` in devDependencies and a `src/` directory.
- Why: Web apps are the most common Playwright surface — the scaffolder must detect the framework and generate appropriate harness stubs.
- Steps:
  1. Follow `create-verification-skill/SKILL.md` instructions against the temp directory.
  2. Verify `verify-<app>/SKILL.md` was created with Launch → Doctor → Drive → Evidence → Cleanup sections.
  3. Verify `harness/launch` contains a `npm run dev` or similar stub.
  4. Verify `harness/drive` references Playwright CLI invocation.
  5. Verify `features/` directory exists.
- Expected: Complete `verify-<app>/` tree with Playwright-specific harness stubs and lifecycle contract SKILL.md.

**Scenario: Scaffold for a Python CLI app**
- Setup: Create a temp directory with `pyproject.toml` containing a `[project.scripts]` entry and no web framework deps.
- Why: CLI apps use PTY/subprocess harnesses instead of browser drivers — the scaffolder must detect this and adjust.
- Steps:
  1. Follow `create-verification-skill/SKILL.md` instructions.
  2. Verify `harness/drive` references subprocess/PTY invocation patterns.
  3. Verify no Playwright references appear.
- Expected: PTY/subprocess harness stubs generated. No web-specific content.

### Gotchas
- These are agent skills (markdown instructions), not Python modules — they guide the Worker agent to generate project-specific verification code, not generate it themselves.
- The `<app>` placeholder in `verify-<app>` should be derived from the project name in `pyproject.toml`, `package.json`, or the directory basename.
