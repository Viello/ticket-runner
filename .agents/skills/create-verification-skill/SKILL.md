---
name: create-verification-skill
description: Inspect a target project directory and scaffold a tailored verify-<app> verification skill implementing the 5-step lifecycle contract, harness stubs, and feature maps.
disable-model-invocation: true
---

# Create Verification Skill

Scaffold an evidence-based verification skill under `.agents/skills/verify-<app>/` tailored to the target project's tech stack and user-facing surfaces.

The generated skill equips coding agents with automated behavioral verification through a standardized 5-step lifecycle contract (`Launch` → `Doctor` → `Drive` → `Evidence` → `Cleanup`), out-of-band evidence persistence, and modular feature maps.

---

## 1. Project Surface & Heuristics Detection

Inspect the target project root using patterns anchored against `ProjectSniffer` (`runner/application/scaffolding.py`):

### A. App Name Resolution (`<app>`)
Derive `<app>` using the following priority:
1. `pyproject.toml`: `[project].name` or `[tool.poetry].name`
2. `package.json`: `"name"` field
3. `Cargo.toml`: `[package].name`
4. `go.mod`: module path terminal segment
5. Project root directory basename (sanitized: lowercase, alphanumeric and hyphens)

### B. Surface Classification
Inspect dependencies and manifest markers to classify project surfaces:

1. **Web UIs (Playwright CLI)**:
   - Markers: `package.json` with `"playwright"`, `"@playwright/test"`, `"cypress"`, `"puppeteer"`, `"next"`, `"vite"`, `"react"`, `"vue"`, `"svelte"`, `"astro"`; or `pyproject.toml` / `requirements.txt` with `playwright`, `selenium`.
   - Driver: Playwright CLI (`npx playwright test`, `playwright`).
   - Harness style: Headless browser automation targeting UI workflows, DOM state, and network calls.

2. **CLIs (Interactive PTY / Subprocess)**:
   - Markers: `pyproject.toml` with `[project.scripts]` or CLI libraries (`click`, `typer`, `argparse`); `package.json` with `"bin"` or (`commander`, `yargs`); `Cargo.toml` with `[[bin]]` or `clap`; `go.mod` with `main` packages or `cobra`.
   - Driver: Subprocess / interactive PTY wrapper.
   - Harness style: Command invocation, stdin piping, stdout/stderr validation, and exit code checks.

3. **APIs (HTTP / curl Scripts)**:
   - Markers: `pyproject.toml` / `requirements.txt` with `fastapi`, `flask`, `django`, `httpx`; `package.json` with `express`, `hono`, `koa`, `fastify`, `nest`; or OpenAPI specs (`openapi.yaml`, `swagger.json`).
   - Driver: HTTP scripts using `curl`, `httpx`, or `fetch`.
   - Harness style: Health polling, endpoint requests, payload assertions, and status code verification.

---

## 2. Directory Tree Structure

Scaffold the verification skill at `.agents/skills/verify-<app>/`:

```
.agents/skills/verify-<app>/
├── SKILL.md
├── harness/
│   ├── launch
│   ├── doctor
│   ├── drive
│   └── cleanup
└── features/
    └── <initial-feature>.md
```

---

## 3. The 5-Step Lifecycle Contract (`SKILL.md`)

Write `.agents/skills/verify-<app>/SKILL.md` defining the 5 lifecycle phases:

```markdown
---
name: verify-<app>
description: Behavioral verification skill for <app> implementing the 5-step lifecycle contract.
disable-model-invocation: true
---

# Verify <app>

Execute behavioral verification across detected surfaces for <app>.

## Lifecycle Contract

1. **Launch**:
   - Spawn the application or service under test.
   - Web / API: Start dev server or container in background, writing PID to `.agent/run/<app>.pid`.
   - CLI: Verify build binary / entry point is accessible.

2. **Doctor**:
   - Verify environment health before executing tests.
   - Web / API: Poll health endpoint (e.g. `http://localhost:<port>/health`) with a bounded timeout (max 30s).
   - CLI: Run `--help` or `--version` ensuring zero exit code.
   - Fail early if the runtime is unready to prevent cascade hangs.

3. **Drive**:
   - Run `harness/drive <feature-name>` against the targeted feature scenario.
   - Execute the test driver (Playwright CLI, PTY subprocess runner, or API script).

4. **Evidence**:
   - Persist all traces, logs, screenshots, and DOM snapshots to `.agent/evidence/<ticket_id>/`.
   - Adhere to token-preserving rules: LLM prompts receive only bounded failure excerpts (<=30 lines / 1,000 characters). Full evidence stays on disk.

5. **Cleanup**:
   - Terminate background processes cleanly using recorded PID.
   - Remove temporary test databases, files, and sockets.
```

---

## 4. Harness Stubs (`harness/`)

Create executable stub scripts in `.agents/skills/verify-<app>/harness/`. Every stub must contain comments documenting its role and targeted surface.

### A. `harness/launch`
- **Role**: Starts the application in background or prepares environment.
- **Stub Example (Web / API)**:
  ```bash
  #!/usr/bin/env bash
  # harness/launch — Starts <app> background server (Surface: Web UI / API)
  set -euo pipefail
  mkdir -p .agent/run
  # Start app (e.g., npm run dev, uvicorn app:main) and store PID
  echo "Launching <app>..."
  # npm run dev > .agent/run/<app>.log 2>&1 &
  # echo $! > .agent/run/<app>.pid
  ```
- **Stub Example (CLI)**:
  ```bash
  #!/usr/bin/env bash
  # harness/launch — Prepares <app> CLI executable (Surface: CLI / Subprocess)
  set -euo pipefail
  echo "Verifying <app> binary exists in environment..."
  # command -v <app> || python -m <app> --help
  ```

### B. `harness/doctor`
- **Role**: Polls health check until ready or times out.
- **Stub Example**:
  ```bash
  #!/usr/bin/env bash
  # harness/doctor — Verifies <app> readiness (Surface: Web UI / API / CLI)
  set -euo pipefail
  echo "Checking <app> vitality..."
  # curl -sf http://localhost:3000/api/health || exit 1
  ```

### C. `harness/drive`
- **Role**: Executes targeted behavioral test for a given feature name.
- **Accepts**: `<feature-name>` as first argument.
- **Stub Example (Playwright Web UI)**:
  ```bash
  #!/usr/bin/env bash
  # harness/drive — Executes feature verification (Surface: Web UI / Playwright CLI)
  set -euo pipefail
  FEATURE="${1:-all}"
  EVIDENCE_DIR="${EVIDENCE_DIR:-.agent/evidence/latest}"
  mkdir -p "$EVIDENCE_DIR"
  echo "Driving feature: $FEATURE"
  # npx playwright test "features/$FEATURE.spec.ts" --output="$EVIDENCE_DIR"
  ```
- **Stub Example (CLI Subprocess)**:
  ```bash
  #!/usr/bin/env bash
  # harness/drive — Executes CLI feature scenario (Surface: CLI / Subprocess PTY)
  set -euo pipefail
  FEATURE="${1:-all}"
  EVIDENCE_DIR="${EVIDENCE_DIR:-.agent/evidence/latest}"
  mkdir -p "$EVIDENCE_DIR"
  echo "Driving CLI scenario: $FEATURE"
  # python tests/cli_driver.py --scenario "$FEATURE" --output-dir "$EVIDENCE_DIR"
  ```

### D. `harness/cleanup`
- **Role**: Shuts down processes and cleans runtime state.
- **Stub Example**:
  ```bash
  #!/usr/bin/env bash
  # harness/cleanup — Shuts down <app> and cleans temp data (Surface: Common)
  set -euo pipefail
  if [ -f .agent/run/<app>.pid ]; then
    PID=$(cat .agent/run/<app>.pid)
    kill "$PID" 2>/dev/null || true
    rm -f .agent/run/<app>.pid
  fi
  echo "<app> cleaned up."
  ```

---

## 5. Feature Map Contract (`features/<name>.md`)

Every feature mapped under `.agents/skills/verify-<app>/features/<name>.md` must adhere to the following contract:
- **Maximum length**: <= 40 lines total.
- **Structure**: Exactly 4 required sections in order:
  1. `### Sub-features`: Bulleted list of specific capabilities.
  2. `### User POV Path`: Step-by-step workflow from user or client perspective.
  3. `### Driving Harness`: Exact harness invocation command.
  4. `### Gotchas`: Known timing delays, flaky selectors, or state prerequisites.

### Feature Map Template:
```markdown
# Feature: <Feature Name>

### Sub-features
- <Capability 1>
- <Capability 2>

### User POV Path
1. Navigate or invoke `<command/url>`
2. Provide input `<details>`
3. Expect output or state change `<result>`

### Driving Harness
`./harness/drive <feature-name>`

### Gotchas
- Requires prior database migration or clean cache.
- Async animations require a 200ms stabilization wait.
```
