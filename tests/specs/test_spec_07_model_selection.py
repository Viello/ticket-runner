"""Spec 07 Traceability Test Suite: Model Selection and Reasoning Variant.

Validates all 17 User Stories from docs/specs/07-model-selection-and-reasoning-variant.md:
  US 01: Configure named list of LLMs in config.yaml
  US 02: Human-readable labels for configured models
  US 03: Numbered interactive model selection menu with keypress selection
  US 04: Silent auto-selection when exactly one model configured
  US 05: Programmatic model selection via --model CLI flag
  US 06: Early error and exit code 1 when unconfigured model passed
  US 07: Selected model persisted in .agent/state.json (including corrupt and write-failure paths)
  US 08: Crash recovery restore notice and --model override
  US 09: Doctor pre-flight failure when model.models is missing or empty
  US 10: Selected model passed as -m provider/model to opencode run
  US 11: Ticket Reasoning: high frontmatter passed as --variant high
  US 12: Omitted Reasoning: falls back to model.default_reasoning
  US 13: Empty or omitted model.default_reasoning omits --variant
  US 14: Reasoning variant consistent across initial run, handoff resume, and answer resume
  US 15: Reasoning value passed to OpenCode without allowlist validation
  US 16: Ticket template in to-tickets skill includes Reasoning: field and example comment
  US 17: Case-insensitive extraction of Reasoning: frontmatter field
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
import pytest

from runner.adapters.config.yaml_config_loader import YamlConfigLoader
from runner.adapters.markdown.parser import TicketMarkdownParser
from runner.adapters.opencode.opencode_worker import build_opencode_run_command
from runner.adapters.ui.model_prompt import ModelPrompt
from runner.application.doctor import CHECK_MODEL, Doctor
from runner.application.model_selection import ModelSelectionInteractor
from runner.application.worker_supervisor import WorkerSupervisor
from runner.domain.config import (
    DiscordConfig,
    GitConfig,
    LifecycleConfig,
    ModelConfig,
    ModelEntry,
    PresenceConfig,
    ProjectConfig,
    RunnerConfig,
    TokenBudgetConfig,
    VerificationConfig,
    WorkerConfig,
)
from runner.domain.exceptions import ConfigError, NonInteractiveError, StateFormatError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.ticket import Ticket, TicketStatus
import ticket_runner
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_state_store import FakeStateStore


def _make_test_config(
    models: tuple[ModelEntry, ...] = (
        ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),
        ModelEntry(id="qwen/qwen-plus", label="Qwen Plus"),
    ),
    default_reasoning: str = "",
) -> RunnerConfig:
    return RunnerConfig(
        project=ProjectConfig(name="spec-07-test", branch="agent/ticket-runner", base_branch="main"),
        worker=WorkerConfig(execution_skill=".agents/skills/implement/SKILL.md"),
        verification=VerificationConfig(test_cmd="pytest"),
        tokens=TokenBudgetConfig(),
        presence=PresenceConfig(),
        discord=DiscordConfig(enabled=False),
        lifecycle=LifecycleConfig(queue_completion="terminate"),
        git=GitConfig(),
        model=ModelConfig(models=models, default_reasoning=default_reasoning),
    )


class FakeDoctorPassing(Doctor):
    def __init__(self, config: RunnerConfig) -> None:
        self._mock_config = config

    async def run(self, local_only: bool = False, halt_on_failure: bool = False) -> Any:
        self._loaded_config = self._mock_config
        from runner.application.doctor import CheckResult, DoctorReport
        checks = [
            CheckResult(name="check_opencode", passed=True, message="OpenCode available"),
            CheckResult(name="check_config", passed=True, message="Config valid"),
            CheckResult(name="check_queue", passed=True, message="Queue valid"),
            CheckResult(name="model", passed=True, message="Model configured"),
        ]
        return DoctorReport(passed=True, checks=checks)


# --- US 01: Configure named list of LLMs in config.yaml ---
def test_us_01_configure_named_models_list(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """project:
  name: "ticket-runner"
  branch: "agent/ticket-runner"
  base_branch: "main"
worker:
  execution_skill: ".agents/skills/implement/SKILL.md"
verification:
  test_cmd: "pytest"
tokens:
  warn: 120000
  handoff: 135000
  ceiling: 150000
presence:
  default_mode: "nearby"
  idle_escalation_minutes: 3
discord:
  enabled: false
  token_env: "DISCORD_BOT_TOKEN"
  channel_id: ""
lifecycle:
  queue_completion: "terminate"
git:
  commit_prefix: "feat"
model:
  default_reasoning: ""
  models:
    - id: "deepseek/deepseek-chat"
      label: "DeepSeek Chat"
    - id: "qwen/qwen-plus"
      label: "Qwen Plus"
""",
        encoding="utf-8",
    )
    loader = YamlConfigLoader()
    cfg = loader.load(config_file)
    assert len(cfg.model.models) == 2
    assert cfg.model.models[0].id == "deepseek/deepseek-chat"
    assert cfg.model.models[1].id == "qwen/qwen-plus"


# --- US 02: Human-readable labels for configured models ---
def test_us_02_model_human_readable_labels() -> None:
    config = _make_test_config()
    assert config.model.models[0].label == "DeepSeek Chat"
    assert config.model.models[1].label == "Qwen Plus"

    # Reject blank labels
    with pytest.raises(ConfigError):
        ModelEntry(id="deepseek/deepseek-chat", label="")


# --- US 03: Numbered interactive model selection menu with keypress selection ---
def test_us_03_interactive_menu_keypress_selection() -> None:
    config = _make_test_config()
    keys = ["2", "\r"]
    key_iter = iter(keys)
    output: list[str] = []

    prompt = ModelPrompt(read_key=lambda: next(key_iter), output_fn=output.append)
    menu_str = prompt.render_menu(config.model.models)

    assert "Select model for this session:" in menu_str
    assert "  [1] DeepSeek Chat    (deepseek/deepseek-chat)" in menu_str
    assert "  [2] Qwen Plus        (qwen/qwen-plus)" in menu_str
    assert "> _" in menu_str

    selected = prompt.select_model(config.model.models)
    assert selected == config.model.models[1]


# --- US 04: Silent auto-selection when exactly one model configured ---
def test_us_04_single_model_auto_selects_silently() -> None:
    single = (ModelEntry(id="anthropic/claude-3-5-sonnet", label="Claude 3.5 Sonnet"),)
    config = _make_test_config(models=single)
    store = FakeStateStore()
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        printer=output.append,
    )
    resolved = interactor.resolve_and_persist(cli_model=None)

    assert resolved == "anthropic/claude-3-5-sonnet"
    assert output == []
    assert store.write_calls[-1]["selected_model"] == "anthropic/claude-3-5-sonnet"


# --- US 05: Programmatic model selection via --model CLI flag ---
def test_us_05_cli_flag_selects_programmatically() -> None:
    config = _make_test_config()
    store = FakeStateStore(initial_state={"persisted": "data"})
    output: list[str] = []

    interactor = ModelSelectionInteractor(
        config=config,
        state_store=store,
        printer=output.append,
    )
    resolved = interactor.resolve_and_persist(cli_model="qwen/qwen-plus")

    assert resolved == "qwen/qwen-plus"
    assert not any("Resuming with" in line for line in output)
    assert store.write_calls[-1] == {
        "persisted": "data",
        "selected_model": "qwen/qwen-plus",
    }


# --- US 06: Early error and exit code 1 when unconfigured model passed ---
def test_us_06_reject_unconfigured_model_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = _make_test_config()
    fake_doc = FakeDoctorPassing(config=config)
    monkeypatch.setattr(ticket_runner, "Doctor", lambda *args, **kwargs: fake_doc)

    code = ticket_runner.main(["start", "--local-only", "--model", "unconfigured-llm"])
    assert code == 1

    captured = capsys.readouterr()
    err_out = captured.out + captured.err
    assert "Unknown model 'unconfigured-llm'" in err_out
    assert "deepseek/deepseek-chat" in err_out
    assert "qwen/qwen-plus" in err_out


# --- US 07: Selected model persisted in .agent/state.json, corrupt warning, write-failure exit ---
def test_us_07_selected_model_persisted_to_state_and_edge_cases(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    config = _make_test_config()
    fake_doc = FakeDoctorPassing(config=config)

    # 1. Normal persistence preserves unrelated keys
    store = FakeStateStore(initial_state={"step": 3, "active_ticket": "T050"})
    interactor = ModelSelectionInteractor(config=config, state_store=store)
    interactor.resolve_and_persist("deepseek/deepseek-chat")
    assert store.write_calls[-1] == {
        "step": 3,
        "active_ticket": "T050",
        "selected_model": "deepseek/deepseek-chat",
    }

    # 2. Corrupted state document emits warning and resets cleanly
    corrupt_store = FakeStateStore(read_error=StateFormatError("Malformed JSON"))
    out: list[str] = []
    interactor_corrupt = ModelSelectionInteractor(config=config, state_store=corrupt_store, printer=out.append)
    interactor_corrupt.resolve_and_persist("qwen/qwen-plus")
    assert any("corrupted" in line.lower() for line in out)
    assert corrupt_store.write_calls[-1] == {"selected_model": "qwen/qwen-plus"}

    # 3. Failing state write exits code 1 before orchestration starts
    fail_store = FakeStateStore(write_error=OSError("Disk full"))
    code = asyncio.run(
        ticket_runner.run_start(
            config_path=tmp_path / "config.yaml",
            local_only=True,
            doctor_instance=fake_doc,
            state_store=fail_store,
            model_id="qwen/qwen-plus",
        )
    )
    assert code == 1
    captured = capsys.readouterr()
    assert "persistence failed" in captured.out.lower() or "disk full" in captured.out.lower()


# --- US 08: Crash recovery restore notice and --model override ---
def test_us_08_crash_recovery_restore_notice_and_override() -> None:
    config = _make_test_config()

    # 1. Restore notice is exact verbatim contract
    store = FakeStateStore(initial_state={"selected_model": "qwen/qwen-plus"})
    out: list[str] = []
    interactor = ModelSelectionInteractor(config=config, state_store=store, printer=out.append)
    resolved = interactor.resolve_and_persist(cli_model=None)
    assert resolved == "qwen/qwen-plus"
    assert "Resuming with Qwen Plus — pass --model to override" in out

    # 2. --model flag overrides persisted state
    out_override: list[str] = []
    store_override = FakeStateStore(initial_state={"selected_model": "qwen/qwen-plus"})
    interactor_override = ModelSelectionInteractor(config=config, state_store=store_override, printer=out_override.append)
    resolved_override = interactor_override.resolve_and_persist(cli_model="deepseek/deepseek-chat")
    assert resolved_override == "deepseek/deepseek-chat"
    assert not any("Resuming with" in line for line in out_override)
    assert store_override.write_calls[-1]["selected_model"] == "deepseek/deepseek-chat"

    # 3. Model drift warns and falls through
    out_drift: list[str] = []
    store_drift = FakeStateStore(initial_state={"selected_model": "missing/legacy-model"})
    single = (ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),)
    interactor_drift = ModelSelectionInteractor(config=_make_test_config(models=single), state_store=store_drift, printer=out_drift.append)
    resolved_drift = interactor_drift.resolve_and_persist(cli_model=None)
    assert resolved_drift == "deepseek/deepseek-chat"
    assert any("missing/legacy-model" in line for line in out_drift)


# --- US 09: Doctor pre-flight failure when model.models is missing or empty ---
def test_us_09_doctor_fails_preflight_when_models_empty_or_missing() -> None:
    from runner.domain.config import ModelConfig
    from tests.unit.application.test_doctor import FakeConfigLoader, _make_config

    config = _make_config(model=ModelConfig(models=()))
    doctor = Doctor(config_loader=FakeConfigLoader(config=config))

    async def _run() -> Any:
        await doctor.check_config()
        return await doctor.check_model()

    result = asyncio.run(_run())
    assert result.passed is False
    assert result.name == CHECK_MODEL
    assert "model.models" in result.message
    assert result.remediation is not None
    assert "model:" in result.remediation


# --- US 10: Selected model passed as -m provider/model to opencode run ---
def test_us_10_selected_model_passed_to_opencode_run() -> None:
    cmd = build_opencode_run_command("Prompt text", model_id="qwen/qwen-plus")
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "-m",
        "qwen/qwen-plus",
        "--auto",
        "Prompt text",
    ]


# --- US 11: Ticket Reasoning: high frontmatter passed as --variant high ---
def test_us_11_ticket_reasoning_high_passes_variant(tmp_path: Path) -> None:
    ticket_md = """# T099 — High Reasoning Ticket
Status: pending
Reasoning: high

### Requirements
- High reasoning required
"""
    ticket_path = tmp_path / "T099.md"
    ticket_path.write_text(ticket_md, encoding="utf-8")
    parser = TicketMarkdownParser()
    ticket = parser.parse(ticket_path)
    assert ticket.reasoning == "high"

    cmd = build_opencode_run_command("Prompt text", model_id="qwen/qwen-plus", variant=ticket.reasoning)
    assert cmd == [
        "opencode",
        "run",
        "--format",
        "json",
        "-m",
        "qwen/qwen-plus",
        "--variant",
        "high",
        "--auto",
        "Prompt text",
    ]


# --- US 12: Omitted Reasoning: falls back to model.default_reasoning ---
def test_us_12_ticket_omits_reasoning_uses_config_default(tmp_path: Path) -> None:
    ticket = Ticket(
        id="T100",
        title="Default Reasoning",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=tmp_path / "T100.md",
        reasoning="",  # Omitted in frontmatter
    )
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "-m", "deepseek/deepseek-chat", "--variant", "medium", "--auto", "Prompt"],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": "ses_100"})],
    )
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        model_id="deepseek/deepseek-chat",
        default_reasoning="medium",
    )
    asyncio.run(supervisor.run(ticket=ticket, prompt="Prompt"))

    assert len(fake_runner.spawns) == 1
    spawned_cmd = fake_runner.spawns[0]
    assert spawned_cmd[4] == "-m"
    assert spawned_cmd[5] == "deepseek/deepseek-chat"
    assert spawned_cmd[6] == "--variant"
    assert spawned_cmd[7] == "medium"


# --- US 13: Empty or omitted model.default_reasoning omits --variant ---
def test_us_13_default_reasoning_empty_omits_variant(tmp_path: Path) -> None:
    ticket = Ticket(
        id="T101",
        title="No Variant Ticket",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=tmp_path / "T101.md",
        reasoning="",
    )
    fake_runner = FakeCommandRunner()
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "-m", "deepseek/deepseek-chat", "--auto", "Prompt"],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": "ses_101"})],
    )
    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        model_id="deepseek/deepseek-chat",
        default_reasoning="",
    )
    asyncio.run(supervisor.run(ticket=ticket, prompt="Prompt"))

    assert len(fake_runner.spawns) == 1
    spawned_cmd = fake_runner.spawns[0]
    assert "--variant" not in spawned_cmd


# --- US 14: Reasoning variant consistent across all session runs in ticket lifecycle ---
def test_us_14_reasoning_consistent_across_all_session_runs(tmp_path: Path) -> None:
    ticket = Ticket(
        id="T102",
        title="Consistent Variant",
        status=TicketStatus.PENDING,
        spec_path="docs/specs/test.md",
        requirements=("R1",),
        acceptance_criteria=("C1",),
        gotchas=(),
        path=tmp_path / "T102.md",
        reasoning="max",
    )
    fake_runner = FakeCommandRunner()
    # 1. Initial spawn
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "-m", "qwen/qwen-plus", "--variant", "max", "--auto", "Initial"],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": "ses_102"})],
    )
    # 2. Handoff resume spawn
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", "ses_102", "-m", "qwen/qwen-plus", "--variant", "max", "--auto", "Resume"],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": "ses_102"})],
    )
    # 3. Answer resume spawn
    fake_runner.register_spawn(
        ["opencode", "run", "--format", "json", "--session", "ses_102", "-m", "qwen/qwen-plus", "--variant", "max", "--auto", "User answered: ok"],
        stdout_lines=[json.dumps({"type": "step_start", "sessionID": "ses_102"})],
    )

    runtime_paths = RuntimePaths(root_dir=tmp_path / ".agent")
    supervisor = WorkerSupervisor(
        command_runner=fake_runner,
        runtime_paths=runtime_paths,
        model_id="qwen/qwen-plus",
        default_reasoning="low",
    )

    asyncio.run(supervisor.run(ticket=ticket, prompt="Initial"))
    asyncio.run(supervisor.run(ticket=ticket, prompt="Resume", session_id="ses_102"))
    asyncio.run(supervisor.run(ticket=ticket, prompt="User answered: ok", session_id="ses_102"))

    assert len(fake_runner.spawns) == 3
    for spawn_cmd in fake_runner.spawns:
        assert "-m" in spawn_cmd
        m_idx = spawn_cmd.index("-m")
        assert spawn_cmd[m_idx + 1] == "qwen/qwen-plus"
        assert "--variant" in spawn_cmd
        v_idx = spawn_cmd.index("--variant")
        assert spawn_cmd[v_idx + 1] == "max"


# --- US 15: Reasoning value passed to OpenCode without allowlist validation ---
def test_us_15_reasoning_passed_without_validation() -> None:
    custom_variant = "extreme-thinking-v4"
    cmd = build_opencode_run_command("Prompt", model_id="qwen/qwen-plus", variant=custom_variant)
    assert "--variant" in cmd
    idx = cmd.index("--variant")
    assert cmd[idx + 1] == "extreme-thinking-v4"


# --- US 16: Ticket template in to-tickets skill includes Reasoning: field and example comment ---
def test_us_16_ticket_template_includes_reasoning_comment() -> None:
    skill_file = Path(".agents/skills/to-tickets/SKILL.md")
    assert skill_file.is_file()
    content = skill_file.read_text(encoding="utf-8")
    assert "Reasoning: medium" in content
    assert "# optional: low | medium | high | max (provider-specific; omit to use config default)" in content


# --- US 17: Case-insensitive extraction of Reasoning: frontmatter field ---
def test_us_17_reasoning_parsed_case_insensitively(tmp_path: Path) -> None:
    parser = TicketMarkdownParser()

    # Uppercase
    f1 = tmp_path / "T103.md"
    f1.write_text("# T103\nStatus: pending\nREASONING: HIGH\n\n### Requirements\nR1\n", encoding="utf-8")
    t_upper = parser.parse(f1)
    assert t_upper.reasoning == "HIGH"

    # Mixed case
    f2 = tmp_path / "T104.md"
    f2.write_text("# T104\nStatus: pending\nReasoning: Medium\n\n### Requirements\nR1\n", encoding="utf-8")
    t_mixed = parser.parse(f2)
    assert t_mixed.reasoning == "Medium"

    # Lowercase
    f3 = tmp_path / "T105.md"
    f3.write_text("# T105\nStatus: pending\nreasoning: low\n\n### Requirements\nR1\n", encoding="utf-8")
    t_lower = parser.parse(f3)
    assert t_lower.reasoning == "low"
