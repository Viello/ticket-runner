# Testing

The suite is the Gatekeeper's evidence. Run the narrowest check that proves the change, then the full suite before commit.

## Layout
- `tests/unit/` — one module, fast, no network. Mirror the source tree: `runner/domain/x.py` → `tests/unit/domain/test_x.py`.
- `tests/specs/` — spec acceptance tests spanning modules.
- `tests/integration/` — Discord end-to-end tests.
- `tests/fakes/` — protocol doubles shared across suites.

## Commands
The exact commands live in `AGENTS.md` § Verification. Run them from the repo root with `py -3`.

Done when the targeted file is green and the full suite is green, or the unrelated failure is named with its test id.

## Policy
- Single file first. The full suite exists for the commit gate, not for every edit.
- A green subset is not a green suite. Report unrelated failures instead of hiding them.
- After two failed fix attempts, stop and use the Loop Breaker in `AGENTS.md`.
- Ruff and mypy are dev-only (`requirements-dev.txt`). Their repo-wide baselines still carry legacy debt; gate the files you changed and file separate work for unrelated debt.
- `mypy` checks the file you name (`follow_imports = "silent"`); it does not audit the whole import graph.

## Async tests
Use `@pytest.mark.anyio`. The repository runs async tests through anyio; `pytest-asyncio` marks do not run.

## Live tests
`tests/unit/adapters/test_live_opencode_smoke.py` and `test_live_antigravity_smoke.py` are opt-in: they run only when `TICKET_RUNNER_LIVE=1`. The Antigravity smoke test also skips when `agy` is not on PATH. Leave the env var unset for routine runs.

## Fakes
`tests/fakes/` holds protocol doubles such as `FakeAgentWorker`, `FakeDiscordGateway`, and `FakeStateStore`. Reach for an existing fake before writing a mock; the fakes record calls and keep tests deterministic.
