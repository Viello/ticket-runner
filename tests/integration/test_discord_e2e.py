"""End-to-end integration tests for Discord adapter stack and local-only mode (T088)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
import pytest
import yaml

from runner.adapters.discord.client import DiscordClient
from runner.adapters.discord.gateway import DiscordPyGateway
from runner.adapters.discord.logger import DiscordLoggerImpl
from runner.application.discord_thread_manager import DiscordThreadManager
from runner.application.doctor import Doctor
from runner.application.gatekeeper import CommandOutcome, VerificationReport
from runner.application.handoff_coordinator import SingleCycleStatus, WorkerRunResult
from runner.application.presence_coordinator import PresenceCoordinator
from runner.application.ticket_processor import GatekeeperTicketProcessor
from runner.domain.config import DiscordConfig, RunnerConfig
from runner.domain.exceptions import DiscordGatewayError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import QuestionSignal, QuestionType, ReadySignal, SignalStatus
from runner.domain.ticket import Ticket, TicketStatus
from tests.fakes.fake_discord_gateway import FakeDiscordGateway
from tests.fakes.fake_intervention import FakeInterventionGateway
from tests.fakes.fake_signal_repository import FakeSignalRepository


def _make_ticket(
    ticket_id: str = "T088",
    title: str = "Discord e2e smoke and local-only verification",
    spec_path: str = "docs/specs/05-presence-mode-and-discord.md",
) -> Ticket:
    return Ticket(
        id=ticket_id,
        title=title,
        status=TicketStatus.PENDING,
        spec_path=spec_path,
        requirements=("Verify full Discord stack and local-only bypass",),
        acceptance_criteria=("All lifecycle events route cleanly",),
        gotchas=(),
        path=Path(f"docs/tickets/05-presence-mode-and-discord/{ticket_id}-test.md"),
        security_required=False,
    )


class _PassingExecutor:
    async def verify(self, config: Any) -> VerificationReport:
        return VerificationReport(
            passed=True,
            results=(
                CommandOutcome(
                    label="test",
                    command="pytest -q",
                    exit_code=0,
                    timed_out=False,
                    tail="1 passed",
                ),
            ),
            diagnostics=(),
            skipped_commands=(),
        )


@pytest.mark.anyio
async def test_full_discord_lifecycle_with_fake_gateway() -> None:
    """Smoke Scenario: Full Discord lifecycle with fake gateway.

    Verifies: thread open -> status card pinned -> live digest started -> question posted
    -> escalation scheduled -> answer resets presence -> status card updated -> commit embed
    -> thread archived.
    """
    ticket = _make_ticket()
    gateway = FakeDiscordGateway()
    notify_user_id = "555123456789"
    logger = DiscordLoggerImpl(gateway, notify_user_id=notify_user_id)
    thread_mgr = DiscordThreadManager(gateway, logger=logger, discord_enabled=True)

    # Use immediate timer factory so escalation fires synchronously when scheduled
    async def _immediate_timer(delay: float, callback: Any) -> asyncio.Task[None]:
        await callback()

        async def _dummy() -> None:
            pass

        return asyncio.create_task(_dummy())

    presence_coord = PresenceCoordinator(
        idle_escalation_minutes=0.0,
        timer_factory=_immediate_timer,
    )
    sig_repo = FakeSignalRepository()
    intervention_gw = FakeInterventionGateway(answers=["Proceed with the implementation."])

    cycle_count = 0

    async def _cycle_runner(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        nonlocal cycle_count
        cycle_count += 1
        if cycle_count == 1:
            sig_repo.seed_question(
                QuestionSignal(
                    ticket_id=t.id,
                    question="Which logging approach should be used?",
                    type=QuestionType.TEXT,
                    options=None,
                    status=SignalStatus.PENDING,
                    answer=None,
                    created_at=datetime.now(timezone.utc),
                )
            )
            return WorkerRunResult(
                status=SingleCycleStatus.QUESTION_PENDING,
                session_id="ses_e2e_1",
            )
        else:
            sig_repo.seed_ready(
                ReadySignal(
                    ticket_id=t.id,
                    status=SignalStatus.READY_FOR_VERIFICATION,
                    modified_files=("runner/application/ticket_processor.py",),
                    self_review_notes="Implementation reviewed and clean.",
                    new_gotchas=(),
                    timestamp=datetime.now(timezone.utc),
                    scope="adapters",
                    manual_verification=(
                        {
                            "name": "Full lifecycle check",
                            "setup": "None",
                            "steps": "Observe Discord thread",
                            "expected": "Thread created, card updated, thread archived",
                        },
                    ),
                )
            )
            return WorkerRunResult(
                status=SingleCycleStatus.READY,
                session_id="ses_e2e_1",
                resources_accessed=frozenset({"code-review", "AGENTS.md"}),
            )

    processor = GatekeeperTicketProcessor(
        cycle_runner=_cycle_runner,
        signal_repository=sig_repo,
        executor=_PassingExecutor(),
        intervention_gateway=intervention_gw,
        discord_thread_manager=thread_mgr,
        discord_logger=logger,
        presence_coordinator=presence_coord,
        discord_channel_id="chan-e2e-100",
    )

    outcome = await processor.process(ticket)
    assert outcome.is_approved is True
    assert presence_coord.current_mode == "nearby"

    # Analyze recorded calls on FakeDiscordGateway
    calls = gateway.calls
    methods = [c.method for c in calls]

    # Verify critical operations are present in chronological order
    assert "create_thread" in methods
    assert "pin_message" in methods
    assert "post_message" in methods
    assert "edit_message" in methods
    assert "archive_thread" in methods

    create_idx = methods.index("create_thread")
    pin_idx = methods.index("pin_message")
    assert pin_idx > create_idx

    # Question escalation check: user mention + yellow embed posted
    post_calls = [c for c in calls if c.method == "post_message"]
    mention_posts = [c for c in post_calls if c.content == f"<@{notify_user_id}>"]
    assert len(mention_posts) == 1

    question_embed_posts = [
        c for c in post_calls if c.embed and "❓ Worker Question" in c.embed.get("title", "")
    ]
    assert len(question_embed_posts) == 1

    # Status card updates and live digest finalization check
    edit_calls = [c for c in calls if c.method == "edit_message"]
    reviewing_edits = [
        c for c in edit_calls if c.embed and "Reviewing" in c.embed.get("description", "")
    ]
    assert len(reviewing_edits) >= 1

    verifying_edits = [
        c for c in edit_calls if c.embed and "Verifying" in c.embed.get("description", "")
    ]
    assert len(verifying_edits) >= 1

    done_digest_edits = [c for c in edit_calls if c.content and "[done]" in c.content]
    assert len(done_digest_edits) >= 1

    committed_card_edits = [
        c for c in edit_calls if c.embed and "✅ Committed" in c.embed.get("description", "")
    ]
    assert len(committed_card_edits) >= 1

    # Thread archived as final step
    assert methods[-1] == "archive_thread"


@pytest.mark.anyio
async def test_local_only_flag_suppresses_all_discord_calls() -> None:
    """Smoke Scenario: local-only produces zero Discord calls.

    Verifies that when Discord is disabled via configuration or thread manager,
    no calls are dispatched to DiscordGateway.
    """
    ticket = _make_ticket()
    gateway = FakeDiscordGateway()
    logger = DiscordLoggerImpl(gateway)
    thread_mgr = DiscordThreadManager(gateway, logger=logger, discord_enabled=False)

    sig_repo = FakeSignalRepository()

    async def _cycle_runner(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        sig_repo.seed_ready(
            ReadySignal(
                ticket_id=ticket.id,
                status=SignalStatus.READY_FOR_VERIFICATION,
                modified_files=("clean.py",),
                self_review_notes="Done",
                new_gotchas=(),
                timestamp=datetime.now(timezone.utc),
                manual_verification=(
                    {"name": "Local smoke", "setup": "None", "steps": "Run", "expected": "Pass"},
                ),
            )
        )
        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            session_id="ses_local_only",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    import types
    runner_config = types.SimpleNamespace(
        discord=DiscordConfig(enabled=False, channel_id="chan-local-only")
    )

    processor = GatekeeperTicketProcessor(
        cycle_runner=_cycle_runner,
        signal_repository=sig_repo,
        executor=_PassingExecutor(),
        intervention_gateway=FakeInterventionGateway(),
        discord_thread_manager=thread_mgr,
        discord_logger=logger,
        runner_config=runner_config,
    )

    outcome = await processor.process(ticket)
    assert outcome.is_approved is True
    assert len(gateway.calls) == 0


@pytest.mark.anyio
async def test_transient_gateway_error_does_not_abort_ticket() -> None:
    """Smoke Scenario: Transient gateway error does not abort ticket.

    Verifies that DiscordGatewayError raised during post_message is swallowed
    and ticket processing completes normally with TicketOutcome.approved.
    """
    ticket = _make_ticket()
    gateway = FakeDiscordGateway(
        raise_on_post_message=DiscordGatewayError("Simulated transient connection reset")
    )
    logger = DiscordLoggerImpl(gateway)
    thread_mgr = DiscordThreadManager(gateway, logger=logger, discord_enabled=True)

    sig_repo = FakeSignalRepository()

    async def _cycle_runner(t: Ticket, **kwargs: Any) -> WorkerRunResult:
        sig_repo.seed_ready(
            ReadySignal(
                ticket_id=ticket.id,
                status=SignalStatus.READY_FOR_VERIFICATION,
                modified_files=("resilient.py",),
                self_review_notes="Done",
                new_gotchas=(),
                timestamp=datetime.now(timezone.utc),
                manual_verification=(
                    {"name": "Transient check", "setup": "None", "steps": "Run", "expected": "Pass"},
                ),
            )
        )
        return WorkerRunResult(
            status=SingleCycleStatus.READY,
            session_id="ses_transient",
            resources_accessed=frozenset({"code-review", "AGENTS.md"}),
        )

    processor = GatekeeperTicketProcessor(
        cycle_runner=_cycle_runner,
        signal_repository=sig_repo,
        executor=_PassingExecutor(),
        intervention_gateway=FakeInterventionGateway(),
        discord_thread_manager=thread_mgr,
        discord_logger=logger,
        discord_channel_id="chan-transient",
    )

    outcome = await processor.process(ticket)
    assert outcome.is_approved is True


@pytest.mark.anyio
async def test_doctor_startup_local_only_skips_discord() -> None:
    """Verifies that Doctor check_discord passes when local_only=True without credentials."""
    doctor = Doctor(env={})  # empty environment, no DISCORD_BOT_TOKEN
    check = await doctor.check_discord(local_only=True)
    assert check.passed is True
    assert "bypassed" in check.message.lower()


@pytest.mark.anyio
async def test_actual_discord_lifecycle_live() -> None:
    """End-to-end integration test against ACTUAL Discord using live bot token.

    Runs only when DISCORD_BOT_TOKEN is present in the environment and config.yaml exists.
    Connects to the Discord channel specified in config.yaml, creates a ticket thread,
    runs the question -> answer -> review -> pass lifecycle, and verifies clean thread closing.
    """
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token or not Path("config.yaml").is_file():
        pytest.skip("DISCORD_BOT_TOKEN or config.yaml not available for live Discord test.")

    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    discord_cfg = cfg.get("discord", {})
    channel_id = str(discord_cfg.get("channel_id", ""))
    guild_id = str(discord_cfg.get("guild_id", ""))

    if not channel_id:
        pytest.skip("No discord.channel_id configured in config.yaml.")

    bot_client = DiscordClient(config=DiscordConfig(channel_id=channel_id, guild_id=guild_id))
    start_task = asyncio.create_task(bot_client.start(token=token))
    try:
        await asyncio.wait_for(bot_client.ready_event.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        await bot_client.close()
        start_task.cancel()
        pytest.fail("Timed out waiting for live Discord bot to connect.")

    try:
        gateway = DiscordPyGateway(bot_client.client)
        logger = DiscordLoggerImpl(gateway, notify_user_id=None)
        thread_mgr = DiscordThreadManager(gateway, logger=logger, discord_enabled=True)

        async def _immediate_timer(delay: float, callback: Any) -> asyncio.Task[None]:
            async def _run() -> None:
                await callback()

            return asyncio.create_task(_run())

        presence_coord = PresenceCoordinator(
            idle_escalation_minutes=0.0,
            timer_factory=_immediate_timer,
        )
        sig_repo = FakeSignalRepository()
        intervention_gw = FakeInterventionGateway(answers=["Proceed with live test fix."])

        ticket = Ticket(
            id="T999",
            title="Live Discord e2e integration smoke",
            status=TicketStatus.PENDING,
            spec_path="docs/specs/05-presence-mode-and-discord.md",
            requirements=("Verify real Discord lifecycle",),
            acceptance_criteria=("All real Discord calls succeed",),
            gotchas=(),
            path=Path("docs/tickets/T999.md"),
            security_required=False,
        )

        call_count = 0

        async def _fake_cycle_runner(t: Ticket, **kwargs: Any) -> WorkerRunResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                sig_repo.seed_question(
                    QuestionSignal(
                        ticket_id=t.id,
                        question="Live check: Does escalation work?",
                        type=QuestionType.TEXT,
                        options=None,
                        status=SignalStatus.PENDING,
                        answer=None,
                        created_at=datetime.now(timezone.utc),
                    )
                )
                return WorkerRunResult(
                    status=SingleCycleStatus.QUESTION_PENDING,
                    session_id="live_ses_1",
                )
            else:
                sig_repo.seed_ready(
                    ReadySignal(
                        ticket_id=t.id,
                        status=SignalStatus.READY_FOR_VERIFICATION,
                        modified_files=("tests/integration/test_discord_e2e.py",),
                        self_review_notes="Live verification passed.",
                        new_gotchas=(),
                        timestamp=datetime.now(timezone.utc),
                        scope="adapters",
                        manual_verification=(
                            {
                                "name": "Live smoke check",
                                "setup": "None",
                                "steps": "Check Discord",
                                "expected": "Thread created, card updated, thread archived",
                            },
                        ),
                    )
                )
                return WorkerRunResult(
                    status=SingleCycleStatus.READY,
                    session_id="live_ses_1",
                    resources_accessed=frozenset({"code-review", "AGENTS.md"}),
                )

        processor = GatekeeperTicketProcessor(
            cycle_runner=_fake_cycle_runner,
            signal_repository=sig_repo,
            executor=_PassingExecutor(),
            intervention_gateway=intervention_gw,
            discord_thread_manager=thread_mgr,
            discord_logger=logger,
            presence_coordinator=presence_coord,
            discord_channel_id=channel_id,
        )

        outcome = await processor.process(ticket)
        assert outcome.is_approved is True
        assert presence_coord.current_mode == "nearby"
    finally:
        await bot_client.close()
        if not start_task.done():
            start_task.cancel()
            try:
                await start_task
            except (asyncio.CancelledError, Exception):
                pass
