---
name: maintain-verification-skill
description: Audit and synchronize a project's verify-<app> verification skill and feature maps against active source code to prevent documentation and harness rot.
disable-model-invocation: true
---

# Maintain Verification Skill

Audit and update the project's verification skill (`.agents/skills/verify-<app>/`) and its modular feature maps (`features/*.md`) against active source code.

This skill prevents documentation rot, detects orphaned or outdated feature maps, flags uncovered user-facing surfaces, and ensures driving harnesses remain aligned with code changes.

---

## 1. Audit Process

When invoked, execute the following audit sequence across the project:

### Step 1: Discover Active Surfaces and Routes
Scan the codebase to catalog currently active user-facing entry points:
- **Web UIs**: Scan route files (e.g. Next.js `app/`, `pages/`, Vue/Svelte router configs, or template endpoints).
- **CLIs**: Scan command definitions (e.g. Click/Typer commands, Argparse subcommands, or Commander actions).
- **APIs**: Scan controller routes and route decorators (e.g. `@app.get`, `router.post`, Express `app.use`).

### Step 2: Enforce Feature Map Contract
Inspect every existing file in `.agents/skills/verify-<app>/features/*.md`:
1. **Length check**: Ensure the file contains **<= 40 lines** total. If a feature file exceeds 40 lines, split it into modular sub-features.
2. **Section check**: Verify each file contains exactly the 4 required sections:
   - `### Sub-features`
   - `### User POV Path`
   - `### Driving Harness`
   - `### Gotchas`
3. If sections are missing or out of order, reformat the feature map to restore the contract.

### Step 3: Flag Orphaned Features
Compare mapped features against active source code:
- Identify feature files whose referenced endpoints, routes, or CLI commands have been deleted or renamed.
- Mark orphaned files: propose removing or archiving them to prevent failing verification runs.

### Step 4: Suggest New Features for Uncovered Surfaces
Identify public routes, CLI subcommands, or UI views that lack a corresponding feature map:
- Highlight newly added features or endpoints without verification coverage.
- Generate new feature map drafts under `.agents/skills/verify-<app>/features/<feature-name>.md` adhering to the 4-section contract (<=40 lines).

### Step 5: Audit Driving Harness Health
Review `harness/launch`, `harness/doctor`, `harness/drive`, and `harness/cleanup`:
- Confirm server startup commands match current build tools (e.g. port configuration, script names in `package.json` or `pyproject.toml`).
- Confirm health check endpoints in `harness/doctor` match active health routes.
- Confirm `harness/drive` commands match active test runners and CLI signatures.
- Confirm `harness/cleanup` properly handles PIDs and teardown for any new background processes.

---

## 2. Remediation Guide

For any discrepancies found during the audit:

1. **Orphaned Feature Maps**:
   - Delete stale `.md` files under `features/` if the code was removed.
   - Update driving commands if the route or CLI flag was merely renamed.

2. **Uncovered Surfaces**:
   - Create a concise `features/<feature-name>.md` following the template below:

   ```markdown
   # Feature: <Name>

   ### Sub-features
   - <List key capabilities>

   ### User POV Path
   1. User action or request
   2. Expected interaction
   3. Observable outcome

   ### Driving Harness
   `./harness/drive <feature-name>`

   ### Gotchas
   - <Timing, auth, or prerequisite notes>
   ```

3. **Harness Updates**:
   - Update environment variables, endpoints, and timeouts in `harness/` stubs as needed.
