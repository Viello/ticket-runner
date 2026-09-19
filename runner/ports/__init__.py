"""Port definitions (protocols and interfaces) for external seams."""

from runner.ports.command_runner import CommandRunner, ProcessHandle
from runner.ports.config_loader import ConfigLoader
from runner.ports.intervention import InterventionAction, InterventionDecision, InterventionGateway
from runner.ports.signal_repository import SignalRepository
from runner.ports.state_store import StateStore
from runner.ports.terminal_display import TerminalDisplay, UiEventSink
from runner.ports.ticket_repository import TicketRepository

__all__ = [
    "CommandRunner",
    "ConfigLoader",
    "InterventionAction",
    "InterventionDecision",
    "InterventionGateway",
    "ProcessHandle",
    "SignalRepository",
    "StateStore",
    "TerminalDisplay",
    "TicketRepository",
    "UiEventSink",
]
