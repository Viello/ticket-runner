"""UI adapters implementing port protocols (terminal prompts, dashboard, and intervention menus)."""

from runner.adapters.ui.keyboard import (
    HotkeyDispatcher,
    KeyboardPoller,
    default_windows_key_reader,
    read_windows_key,
)
from runner.adapters.ui.model_prompt import ModelPrompt
from runner.adapters.ui.terminal import (
    HOTKEY_LEGENDS,
    RichTerminalDisplay,
    calculate_token_bar,
)
from runner.adapters.ui.terminal_approval import TerminalApprovalAdapter
from runner.adapters.ui.terminal_prompts import TerminalInterventionGateway

__all__ = [
    "HOTKEY_LEGENDS",
    "HotkeyDispatcher",
    "KeyboardPoller",
    "ModelPrompt",
    "RichTerminalDisplay",
    "TerminalApprovalAdapter",
    "TerminalInterventionGateway",
    "calculate_token_bar",
    "default_windows_key_reader",
    "read_windows_key",
]