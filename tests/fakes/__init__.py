"""Test doubles and in-memory fakes for isolated testing."""

from tests.fakes.fake_agent_worker import FakeAgentWorker
from tests.fakes.fake_approval_gateway import FakeApprovalGateway
from tests.fakes.fake_command_runner import FakeCommandRunner
from tests.fakes.fake_discord_gateway import DiscordCall, FakeDiscordGateway
from tests.fakes.fake_discord_logger import DiscordLogCall, FakeDiscordLogger
from tests.fakes.fake_intervention import FakeInterventionGateway
from tests.fakes.fake_signal_repository import FakeSignalRepository
from tests.fakes.fake_skills_client import FakeSkillsClient, SkillsSyncInvocation
from tests.fakes.fake_state_store import FakeStateStore
from tests.fakes.fake_terminal_display import FakeTerminalDisplay
from tests.fakes.fake_ticket_repository import FakeTicketRepository

__all__ = [
    "DiscordCall",
    "DiscordLogCall",
    "FakeAgentWorker",
    "FakeApprovalGateway",
    "FakeCommandRunner",
    "FakeDiscordGateway",
    "FakeDiscordLogger",
    "FakeInterventionGateway",
    "FakeSignalRepository",
    "FakeSkillsClient",
    "FakeStateStore",
    "FakeTerminalDisplay",
    "FakeTicketRepository",
    "SkillsSyncInvocation",
]


