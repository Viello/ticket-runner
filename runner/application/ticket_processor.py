"""Ticket processor application interactor driving the ready-path verification loop (T032)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import inspect
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from runner.adapters.filesystem.signal_watcher import FilesystemSignalRepository
from runner.adapters.markdown.gotchas_store import GotchasStore
from runner.adapters.markdown.spec_parser import SpecExcerpt, SpecMarkdownParser
from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway
from runner.application.gatekeeper import (
    GatekeeperCommandExecutor,
    VerificationLoop,
    WorkerCycleRunner,
    build_verification_failure_prompt,
)
from runner.application.handoff_coordinator import (
    HandoffCoordinator,
    WorkerRunResult,
)
from runner.application.prompt_builder import PromptBuilder
from runner.application.state_coordinator import StateCoordinator
from runner.application.queue_orchestrator import (
    TicketOutcome,
    TicketOutcomeStatus,
    TicketProcessor as TicketProcessorProtocol,
)
from runner.adapters.discord.logger import CRITICAL_EVENT_TYPES
from runner.application.git_operations import GitOperations
from runner.domain.config import VerificationConfig, WorkerConfig
from runner.domain.exceptions import DiscordGatewayError, SignalFormatError, UserAbortError
from runner.domain.runtime_paths import RuntimePaths
from runner.domain.signal import ReadySignal
from runner.domain.ticket import Ticket
from runner.ports.approval_gateway import ApprovalGateway
from runner.ports.intervention import InterventionGateway
from runner.ports.signal_repository import SignalRepository
from runner.ports.status_publisher import StatusPublisher

_DEFAULT_PRINTER: Callable[[str], None] = print


class GatekeeperTicketProcessor:
    """Processes a single Ticket through signal isolation, prompt building, and Gatekeeper verification."""

    def __init__(
        self,
        coordinator: HandoffCoordinator | None = None,
        cycle_runner: WorkerCycleRunner | Callable[..., Awaitable[WorkerRunResult]] | None = None,
        signal_repository: SignalRepository | None = None,
        executor: GatekeeperCommandExecutor | None = None,
        intervention_gateway: InterventionGateway | None = None,
        verification_config: VerificationConfig | None = None,
        max_attempts: int | None = None,
        prompt_builder: PromptBuilder | None = None,
        spec_parser: SpecMarkdownParser | None = None,
        gotchas_store: GotchasStore | None = None,
        worker_config: WorkerConfig | None = None,
        loop_factory: Callable[..., VerificationLoop] | None = None,
        printer: Callable[[str], None] | None = _DEFAULT_PRINTER,
        notify: Callable[[str], None] | None = None,
        state_coordinator: StateCoordinator | None = None,
        runtime_paths: RuntimePaths | None = None,
        token_budget: Any | None = None,
        status_publisher: StatusPublisher | None = None,
        git_operations: GitOperations | None = None,
        discord_thread_manager: Any | None = None,
        discord_logger: Any | None = None,
        presence_coordinator: Any | None = None,
        runner_config: Any | None = None,
        discord_channel_id: str | None = None,
        approval_gateway: ApprovalGateway | None = None,
        approval_mode: str | None = None,
        tui_coordinator: Any | None = None,
    ) -> None:
        self._coordinator = coordinator
        self._notify_sink = notify
        self._state_coordinator = state_coordinator
        self._runtime_paths = runtime_paths
        self._token_budget = token_budget
        self._status_publisher = status_publisher
        self._discord_thread_manager = discord_thread_manager
        self._discord_logger = discord_logger
        if self._discord_logger is None and discord_thread_manager is not None:
            self._discord_logger = getattr(discord_thread_manager, "_logger", None)
        self._presence_coordinator = presence_coordinator
        self._runner_config = runner_config
        self._approval_gateway = approval_gateway
        self._approval_mode = (
            approval_mode
            if approval_mode is not None
            else (
                getattr(getattr(runner_config, "lifecycle", None), "approval_mode", "autonomous")
                if runner_config is not None
                else "autonomous"
            )
        )
        self._tui_coordinator = tui_coordinator
        self._discord_channel_id = (
            discord_channel_id
            if discord_channel_id is not None
            else (
                getattr(getattr(runner_config, "discord", None), "channel_id", "")
                if runner_config is not None
                else ""
            )
        )
        self._current_thread_id: str = ""
        self._current_status_card_message_id: str = ""
        if git_operations is not None:
            self._git_operations = git_operations
        elif coordinator is not None and getattr(coordinator, "git_operations", None) is not None:
            self._git_operations = coordinator.git_operations
        elif coordinator is not None and getattr(coordinator, "_git_operations", None) is not None:
            self._git_operations = coordinator._git_operations
        else:
            self._git_operations = None
        if self._notify_sink is None and coordinator is not None and getattr(coordinator, "_notify", None) is not None:
            self._notify_sink = coordinator._notify

        if signal_repository is not None:
            self._signal_repository = signal_repository
        elif coordinator is not None and getattr(coordinator, "signal_repository", None) is not None:
            self._signal_repository = coordinator.signal_repository
        else:
            self._signal_repository = FilesystemSignalRepository(RuntimePaths())

        if cycle_runner is not None:
            self._cycle_runner = cycle_runner
        elif coordinator is not None:
            self._cycle_runner = coordinator.run_cycle
        else:
            self._cycle_runner = None

        self._executor = executor or GatekeeperCommandExecutor()
        self._intervention_gateway = intervention_gateway or TerminalInterventionGateway()
        self._verification_config = verification_config
        self._max_attempts = max_attempts
        self._prompt_builder = prompt_builder or PromptBuilder()
        self._spec_parser = spec_parser or SpecMarkdownParser()
        self._gotchas_store = gotchas_store
        self._worker_config = worker_config
        self._loop_factory = loop_factory
        self._printer = printer

    def _notify(self, message: str) -> None:
        """Emit notification notice to configured notification sink or printer."""
        if self._notify_sink is not None:
            try:
                self._notify_sink(message)
            except Exception:
                pass
        elif self._printer is not None:
            try:
                self._printer(message)
            except Exception:
                pass

    def evaluate_ready_warnings(
        self,
        ticket: Ticket,
        resources_accessed: frozenset[str] | set[str],
    ) -> list[str]:
        """Evaluate resource access compliance upon receiving a ready signal and emit soft warnings."""
        warnings: list[str] = []
        if "code-review" not in resources_accessed:
            warnings.append(
                f"[{ticket.id}] Warning: Ready signal emitted without reading '.agents/skills/code-review/SKILL.md'. Proceeding to verification."
            )
        if "AGENTS.md" not in resources_accessed:
            warnings.append(
                f"[{ticket.id}] Warning: Ready signal emitted without reading 'AGENTS.md'. Proceeding to verification."
            )
        if ticket.security_required and "security-review" not in resources_accessed:
            warnings.append(
                f"[{ticket.id}] Warning: Ready signal emitted without reading required '.agents/skills/security-review/SKILL.md'. Proceeding to verification."
            )

        for warning in warnings:
            logger.warning(warning)
            self._notify(warning)

        return warnings

    @property
    def signal_repository(self) -> SignalRepository:
        """Signal repository port used for isolation and ready consumption."""
        return self._signal_repository

    @property
    def cycle_runner(self) -> WorkerCycleRunner | Callable[..., Awaitable[WorkerRunResult]] | None:
        """Configured worker cycle runner."""
        return self._cycle_runner

    @property
    def executor(self) -> GatekeeperCommandExecutor:
        """Gatekeeper command verification executor."""
        return self._executor

    @property
    def intervention_gateway(self) -> InterventionGateway:
        """Human intervention gateway."""
        return self._intervention_gateway

    @property
    def state_coordinator(self) -> StateCoordinator | None:
        """State coordinator used to persist verification transitions."""
        return self._state_coordinator

    @state_coordinator.setter
    def state_coordinator(self, value: StateCoordinator | None) -> None:
        self._state_coordinator = value

    @property
    def discord_thread_manager(self) -> Any | None:
        """DiscordThreadManager instance used for thread lifecycle management."""
        return self._discord_thread_manager

    @discord_thread_manager.setter
    def discord_thread_manager(self, value: Any | None) -> None:
        self._discord_thread_manager = value
        if self._discord_logger is None and value is not None:
            self._discord_logger = getattr(value, "_logger", None)

    @property
    def discord_logger(self) -> Any | None:
        """DiscordLogger instance used for remote event dispatch."""
        return self._discord_logger

    @discord_logger.setter
    def discord_logger(self, value: Any | None) -> None:
        self._discord_logger = value

    @property
    def presence_coordinator(self) -> Any | None:
        """PresenceCoordinator instance used for mode transitions and escalation."""
        return self._presence_coordinator

    @presence_coordinator.setter
    def presence_coordinator(self, value: Any | None) -> None:
        self._presence_coordinator = value

    @property
    def runner_config(self) -> Any | None:
        """RunnerConfig composite configuration."""
        return self._runner_config

    @runner_config.setter
    def runner_config(self, value: Any | None) -> None:
        self._runner_config = value
        if value is not None and not self._discord_channel_id:
            self._discord_channel_id = getattr(getattr(value, "discord", None), "channel_id", "")

    @property
    def is_discord_enabled(self) -> bool:
        """Return True if Discord notifications and thread management are enabled."""
        if self._runner_config is not None:
            discord_cfg = getattr(self._runner_config, "discord", None)
            if discord_cfg is not None and not getattr(discord_cfg, "enabled", True):
                return False
        if self._discord_thread_manager is None and self._discord_logger is None:
            return False
        if self._discord_thread_manager is not None and getattr(self._discord_thread_manager, "discord_enabled", True) is False:
            return False
        return True

    @property
    def current_thread_id(self) -> str:
        """Discord thread ID for active ticket."""
        return self._current_thread_id

    @property
    def current_status_card_message_id(self) -> str:
        """Discord status card message ID for active ticket."""
        return self._current_status_card_message_id

    @property
    def supervisor(self) -> Any:
        """Underlying WorkerSupervisor if available through coordinator."""
        if self._coordinator is not None and hasattr(self._coordinator, "supervisor"):
            return self._coordinator.supervisor
        return None

    def build_initial_prompt(
        self,
        ticket: Ticket,
        spec_excerpt: SpecExcerpt | str | None = None,
    ) -> str:
        """Build initial worker prompt with documented ready signal schema and question protocol."""
        if self._coordinator is not None and hasattr(self._coordinator, "build_initial_prompt"):
            return self._coordinator.build_initial_prompt(ticket, spec_excerpt=spec_excerpt)

        resolved_excerpt: SpecExcerpt | str
        if spec_excerpt is not None:
            resolved_excerpt = spec_excerpt
        elif ticket.spec_path and Path(ticket.spec_path).is_file():
            try:
                resolved_excerpt = self._spec_parser.extract_excerpt(ticket.spec_path)
            except Exception:
                resolved_excerpt = f"Full specification reference: `{ticket.spec_path}`"
        else:
            resolved_excerpt = f"Full specification reference: `{ticket.spec_path}`"

        gotchas_path = (
            self._gotchas_store.path.as_posix()
            if self._gotchas_store is not None
            else "docs/tickets/gotchas.md"
        )
        execution_skill = (
            self._worker_config.execution_skill
            if self._worker_config is not None
            else ".agents/skills/implement/SKILL.md"
        )

        return self._prompt_builder.build(
            ticket=ticket,
            spec_excerpt=resolved_excerpt,
            gotchas_path=gotchas_path,
            execution_skill=execution_skill,
        )

    _build_prompt = build_initial_prompt

    async def __call__(self, ticket: Ticket) -> TicketOutcome:
        """Execute and verify a single ticket, returning its outcome."""
        return await self.process(ticket)

    async def process(self, ticket: Ticket) -> TicketOutcome:
        """Drive the ready-path verification loop for a ticket."""
        return await self._process_ticket(ticket)

    async def _process_ticket(self, ticket: Ticket) -> TicketOutcome:
        """Internal processing seam driving prompt generation and verification loop."""
        if self._cycle_runner is None:
            raise RuntimeError(
                "No worker cycle runner configured for TicketProcessor."
            )

        # 1. Purge stale Signals for the Ticket at start (Isolation Layer)
        self._signal_repository.purge(ticket.id)

        # 2. Build initial Worker prompt
        initial_prompt = self.build_initial_prompt(ticket)

        # Discord ticket thread initialization
        thread_id = ""
        status_card_message_id = ""
        channel_id = (
            self._discord_channel_id
            or (
                getattr(getattr(self._runner_config, "discord", None), "channel_id", "")
                if self._runner_config is not None
                else ""
            )
        )
        if self.is_discord_enabled and self._discord_thread_manager is not None:
            try:
                thread_id, status_card_message_id = await self._discord_thread_manager.open_ticket_thread(
                    ticket, channel_id
                )
            except (DiscordGatewayError, Exception) as exc:
                logger.warning("Failed to open Discord ticket thread: %s", exc)

        self._current_thread_id = thread_id
        self._current_status_card_message_id = status_card_message_id

        async def _on_phase_change(phase: str) -> None:
            if not self.is_discord_enabled:
                return
            status_label = (
                f"🟡 {phase}"
                if not phase.startswith("🟡") and not phase.startswith("✅")
                else phase
            )
            presence_mode = (
                self._presence_coordinator.current_mode
                if self._presence_coordinator is not None
                and hasattr(self._presence_coordinator, "current_mode")
                else "nearby"
            )
            if (
                self._discord_thread_manager is not None
                and thread_id
                and status_card_message_id
            ):
                try:
                    await self._discord_thread_manager.update_status_card(
                        thread_id,
                        status_card_message_id,
                        status=status_label,
                    )
                except (DiscordGatewayError, Exception) as exc:
                    logger.warning(
                        "Failed to update status card on phase transition: %s", exc
                    )

            if self._discord_logger is not None and thread_id:
                try:
                    await self._discord_logger.log(
                        "phase_transition",
                        phase,
                        thread_id,
                        presence_mode,
                    )
                except (DiscordGatewayError, Exception) as exc:
                    logger.warning(
                        "Failed to log phase transition to Discord: %s", exc
                    )

        async def _on_event(event_type: str, payload: str) -> None:
            if not self.is_discord_enabled or self._discord_logger is None or not thread_id:
                return
            presence_mode = (
                self._presence_coordinator.current_mode
                if self._presence_coordinator is not None
                and hasattr(self._presence_coordinator, "current_mode")
                else "nearby"
            )
            try:
                is_crit = event_type in CRITICAL_EVENT_TYPES
                await self._discord_logger.log(
                    event_type,
                    payload,
                    thread_id,
                    presence_mode,
                    severity="critical" if is_crit else None,
                )
            except (DiscordGatewayError, Exception) as exc:
                logger.warning("Failed to emit Discord event %s: %s", event_type, exc)

        # Transition to initial Working phase
        await _on_phase_change("Working")

        # 3. Create and drive VerificationLoop
        factory = self._loop_factory or VerificationLoop
        loop_kwargs: dict[str, Any] = {
            "ticket": ticket,
            "cycle_runner": self._cycle_runner,
            "signal_repository": self._signal_repository,
            "executor": self._executor,
            "intervention_gateway": self._intervention_gateway,
            "verification_config": self._verification_config,
            "max_attempts": self._max_attempts,
            "initial_prompt": initial_prompt,
        }
        try:
            sig = inspect.signature(factory)
            if "notify" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["notify"] = self._notify_sink
            if "state_coordinator" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["state_coordinator"] = self._state_coordinator
            if "runtime_paths" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["runtime_paths"] = self._runtime_paths
            if "token_budget" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["token_budget"] = self._token_budget
            if "status_publisher" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["status_publisher"] = self._status_publisher
            if "git_operations" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["git_operations"] = self._git_operations
            if "phase_callback" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["phase_callback"] = _on_phase_change
            if "event_callback" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["event_callback"] = _on_event
            if "discord_logger" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["discord_logger"] = self._discord_logger
            if "thread_id" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["thread_id"] = thread_id
            if "status_card_message_id" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["status_card_message_id"] = status_card_message_id
            if "presence_coordinator" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["presence_coordinator"] = self._presence_coordinator
            if "discord_thread_manager" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["discord_thread_manager"] = self._discord_thread_manager
            if "approval_gateway" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["approval_gateway"] = self._approval_gateway
            if "approval_mode" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["approval_mode"] = self._approval_mode
            if "tui_coordinator" in sig.parameters or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
            ):
                loop_kwargs["tui_coordinator"] = self._tui_coordinator
        except (ValueError, TypeError):
            pass

        loop = factory(**loop_kwargs)

        pending_prompt: str | None = None
        while True:
            try:
                result = await loop.run(prompt=pending_prompt)
            except UserAbortError as exc:
                return TicketOutcome.aborted(details=str(exc))

            # 4. Map verification loop result to TicketOutcome
            if result.is_passed:
                ready_signal = result.ready_signal
                if ready_signal is not None:
                    changes = tuple(f"Update {p}" for p in ready_signal.modified_files)
                    new_gotchas = ready_signal.new_gotchas
                    scope = ready_signal.scope
                    if ready_signal.self_review_notes and self._printer is not None:
                        self._printer(f"[{ticket.id}] Self-review notes: {ready_signal.self_review_notes}")
                    scope_str = scope or "adapters"
                    file_bullets = "\n".join(
                        f"- Update {f}"
                        for f in (ready_signal.modified_files if ready_signal else ())
                    )
                    commit_summary = (
                        f"{scope_str}: {ticket.title}\n{file_bullets}"
                        if file_bullets
                        else f"{scope_str}: {ticket.title}"
                    )
                else:
                    changes = ()
                    new_gotchas = ()
                    scope = None
                    commit_summary = f"{ticket.id}: {ticket.title}"

                if (
                    self.is_discord_enabled
                    and self._discord_thread_manager is not None
                    and thread_id
                    and status_card_message_id
                ):
                    try:
                        await self._discord_thread_manager.close_ticket_thread(
                            thread_id,
                            status_card_message_id,
                            commit_summary,
                        )
                    except (DiscordGatewayError, Exception) as exc:
                        logger.warning(
                            "Failed to close Discord ticket thread: %s", exc
                        )

                return TicketOutcome.approved(
                    new_gotchas=new_gotchas,
                    changes=changes,
                    scope=scope,
                )

            if result.is_skipped:
                diagnostics = result.diagnostics or loop.last_diagnostics or ""
                return TicketOutcome.skipped(details=diagnostics)

            if result.is_intervention_requested:
                diagnostics = result.diagnostics or loop.last_diagnostics or ""
                return TicketOutcome.intervention_requested(
                    diagnostic=result.failure_diagnostic,
                    details=diagnostics,
                )

            if result.is_question_pending:
                # Precedence: check if a valid ready signal exists (ready wins)
                ready: ReadySignal | None = None
                try:
                    ready = self._signal_repository.read_ready(ticket.id)
                except SignalFormatError:
                    ready = None

                if ready is not None:
                    if hasattr(self._signal_repository, "clean_question"):
                        self._signal_repository.clean_question(ticket.id)
                    pending_prompt = None
                    continue

                # Read pending question
                try:
                    question = self._signal_repository.read_pending_question(ticket.id)
                except SignalFormatError as exc:
                    if hasattr(self._signal_repository, "clean_question"):
                        self._signal_repository.clean_question(ticket.id)
                    pending_prompt = build_verification_failure_prompt(ticket, str(exc))
                    continue

                if question is None:
                    pending_prompt = None
                    continue

                # Schedule escalation on question signal
                if (
                    self.is_discord_enabled
                    and self._presence_coordinator is not None
                    and self._discord_logger is not None
                ):
                    try:
                        schedule_res = self._presence_coordinator.schedule_escalation(
                            ticket.id, thread_id, self._discord_logger
                        )
                        if inspect.iscoroutine(schedule_res):
                            await schedule_res
                    except (DiscordGatewayError, Exception) as exc:
                        logger.warning(
                            "Failed to schedule escalation on question signal: %s", exc
                        )

                # Prompt through InterventionGateway.ask_question
                raw_answer = self._intervention_gateway.ask_question(question)
                if inspect.iscoroutine(raw_answer):
                    answer = await raw_answer
                else:
                    answer = raw_answer

                # Cancel escalation and reset presence on local answer
                if self._presence_coordinator is not None:
                    try:
                        self._presence_coordinator.cancel_escalation()
                        self._presence_coordinator.set_mode("nearby")
                    except (DiscordGatewayError, Exception) as exc:
                        logger.warning("Failed to cancel escalation: %s", exc)

                # Write answer back by rewriting question Signal (status: answered, answer)
                self._signal_repository.write_answer(ticket.id, answer)

                # Resume same Worker Session with prompt carrying answer
                pending_prompt = f"User answered: {answer}. Proceed with implementation."
                continue

            raise ValueError(f"Unsupported verification loop status: {result.status}")


TicketProcessor = GatekeeperTicketProcessor
