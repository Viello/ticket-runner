"""RichTerminalDisplay adapter implementing TerminalDisplay using rich.live.Live and rich.layout.Layout (T057)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from runner.domain.ring_buffer import RingBuffer
from runner.domain.state import RunnerState
from runner.ports.terminal_display import TerminalDisplay

DEFAULT_CEILING: int = 150_000
WARNING_THRESHOLD: int = 120_000
HANDOFF_THRESHOLD: int = 135_000

HOTKEY_LEGENDS: Mapping[str, str] = {
    "normal": "[p] pause  [m] toggle mode  [q] quit  [o] open TUI  [j/k] scroll",
    "confirm_pending": "Open TUI? [y] confirm / [n] cancel",
    "tui_queued": "[p] pause  [m] toggle mode  [q] quit  [o] pending…  [j/k] scroll",
    "tui_open": "[r] Resume  (all other keys suspended)",
}


def calculate_token_bar(
    current: int,
    ceiling: int = DEFAULT_CEILING,
) -> tuple[str, str, int]:
    """Calculate token bar markup, plain bar text, and rounded percentage.

    Rules (Spec 06 §Token Bar Format):
    - 10 characters wide: fill '█', empty '░'
    - Percentage: round(current / 150_000 * 100), clamped to [0, 100]
    - Blocks 1–8: green (when current >= that tenth)
    - Block 9: yellow (when current >= 120,000)
    - Block 10: red (when current >= 135,000)

    Returns:
        tuple of (bar_markup, bar_plain, percentage)
    """
    safe_current = max(0, current)
    pct = min(100, max(0, round(safe_current / ceiling * 100))) if ceiling > 0 else 0

    green_count = min(8, max(0, round(safe_current / ceiling * 10))) if ceiling > 0 else 0
    green_filled = "█" * green_count
    green_empty = "░" * (8 - green_count)
    green_markup = f"[green]{green_filled}[/green]{green_empty}" if green_count > 0 else green_empty

    b9_filled = safe_current >= WARNING_THRESHOLD
    b9_markup = "[yellow]█[/yellow]" if b9_filled else "░"
    b9_plain = "█" if b9_filled else "░"

    b10_filled = safe_current >= HANDOFF_THRESHOLD
    b10_markup = "[red]█[/red]" if b10_filled else "░"
    b10_plain = "█" if b10_filled else "░"

    bar_markup = f"{green_markup}{b9_markup}{b10_markup}"
    bar_plain = f"{green_filled}{green_empty}{b9_plain}{b10_plain}"
    return bar_markup, bar_plain, pct


def build_warning_panel() -> Panel:
    """Construct frozen TUI session warning panel matching Spec 06 verbatim."""
    lines = [
        Text.from_markup("[bold yellow]⚠  OpenCode TUI open — Runner is paused & blind[/bold yellow]"),
        Text.from_markup(
            "[dim white]   Execution is paused: no Gatekeeper, no Circuit Breaker, no token tracking.[/dim white]"
        ),
        Text.from_markup(
            "[dim white]   Tokens consumed in TUI are NOT tracked against the 135k handoff budget.[/dim white]"
        ),
        Text.from_markup(
            "[dim white]   Work done in TUI bypasses the Gatekeeper and Signal protocol.[/dim white]"
        ),
        Text.from_markup(
            "[dim white]   Close the terminal window to resume managed execution.[/dim white]"
        ),
        Text.from_markup(
            "[bold green]   \\[r] Resume  (required if using Windows Terminal)[/bold green]"
        ),
    ]
    return Panel(Group(*lines), border_style="yellow")


DEFAULT_TELEMETRY_CAPACITY: int = 500
SCROLL_STEP: int = 5


class RichTerminalDisplay(TerminalDisplay):
    """Terminal display adapter rendering split interactive dashboard using rich.live.Live."""

    def __init__(
        self,
        console: Console | None = None,
        ring_buffer: RingBuffer | None = None,
        max_entries: int = DEFAULT_TELEMETRY_CAPACITY,
    ) -> None:
        self._console = console or Console()
        self._ring_buffer = ring_buffer or RingBuffer(max_entries=max_entries)
        self._current_state: RunnerState | None = None
        self._queue_remaining: int = 0
        self._legend_state: str = "normal"
        self._is_active: bool = False
        self._show_warning: bool = False
        self._scroll_offset: int = 0
        self._layout = self._build_layout()
        self._live: Live | None = None

    @property
    def scroll_offset(self) -> int:
        """Current scroll offset (0 = live stream at bottom, >0 = scrolled up into history)."""
        return self._scroll_offset

    def scroll_up(self, lines: int = SCROLL_STEP) -> None:
        """Scroll viewport up into past logs."""
        max_scroll = max(0, len(self._ring_buffer) - 1)
        self._scroll_offset = min(max_scroll, self._scroll_offset + lines)
        self._update_layout()

    def scroll_down(self, lines: int = SCROLL_STEP) -> None:
        """Scroll viewport down towards live logs."""
        self._scroll_offset = max(0, self._scroll_offset - lines)
        self._update_layout()

    def scroll_to_top(self) -> None:
        """Jump to oldest available log entries."""
        self._scroll_offset = max(0, len(self._ring_buffer) - 1)
        self._update_layout()

    def scroll_to_bottom(self) -> None:
        """Reset scroll to bottom (live streaming mode)."""
        self._scroll_offset = 0
        self._update_layout()

    @property
    def is_active(self) -> bool:
        """Whether the Live display is currently started."""
        return self._is_active

    @property
    def is_warning_visible(self) -> bool:
        """Whether the TUI warning panel is currently displayed."""
        return self._show_warning or (
            self._current_state is not None and self._current_state.tui_open
        )

    @property
    def ring_buffer(self) -> RingBuffer:
        """Underlying telemetry ring buffer."""
        return self._ring_buffer

    def set_legend_state(self, state: str) -> None:
        """Set the hotkey legend state ('normal', 'confirm_pending', 'tui_queued', 'tui_open')."""
        if state not in HOTKEY_LEGENDS:
            valid_states = ", ".join(sorted(HOTKEY_LEGENDS.keys()))
            raise ValueError(f"Invalid legend state '{state}'. Valid states: {valid_states}")
        self._legend_state = state
        self._update_layout()

    def show_warning_panel(self) -> None:
        """Freeze live dashboard and display full-screen TUI warning panel."""
        self._show_warning = True
        self._legend_state = "tui_open"
        self._update_layout()

    def restore_dashboard(self) -> None:
        """Restore normal split live dashboard and clear warning display."""
        self._show_warning = False
        self._legend_state = "normal"
        self._update_layout()

    def update_state(self, state: RunnerState, queue_remaining: int) -> None:
        """Update runner state and remaining queue count, refreshing layout."""
        self._current_state = state
        self._queue_remaining = max(0, queue_remaining)
        self._update_layout()

    def emit(self, source: str, message: str) -> None:
        """Emit telemetry log into the rolling ring buffer and refresh display."""
        self._ring_buffer.append(source, message)
        self._update_layout()

    def _build_top_panel(self) -> Panel:
        """Build the fixed 6-row top panel matching the Spec 06 contract."""
        state = self._current_state
        ticket_id = (state.active_ticket_id if state and state.active_ticket_id else "none")
        status_val = (
            (state.status.value if hasattr(state.status, "value") else str(state.status))
            if state
            else "IDLE"
        )
        attempts = state.verification_attempts if state else 0
        current_tokens = state.tokens.current if state else 0
        presence_mode = state.presence_mode if state else "nearby"
        session_id = (
            (state.opencode_session_id if state.opencode_session_id else "none")
            if state
            else "none"
        )
        branch = state.branch if state else "main"

        # Row 1
        row1 = f"ticket  {ticket_id} · status  {status_val} · attempt  {attempts} / 3"

        # Row 2
        bar_markup, _, pct = calculate_token_bar(current_tokens)
        row2 = f"tokens  [{bar_markup}] {current_tokens:,} / {DEFAULT_CEILING:,} ({pct}%)"

        # Row 3
        row3 = f"presence  {presence_mode} · session  {session_id}"

        # Row 4
        if self._queue_remaining == 0:
            row4 = f"branch  {branch} · queue  empty"
        else:
            row4 = f"branch  {branch} · queue  {ticket_id} ({self._queue_remaining} remaining)"

        # Row 5: Horizontal rule
        row5 = Rule(characters="─", style="white")

        # Row 6: Hotkey legend
        legend_text = HOTKEY_LEGENDS.get(self._legend_state, HOTKEY_LEGENDS["normal"])

        group = Group(
            Text(row1),
            Text.from_markup(row2),
            Text(row3),
            Text(row4),
            row5,
            Text(legend_text),
        )
        return Panel(group, height=8)

    def _build_bottom_panel(self) -> Panel:
        """Build the bottom panel displaying the rolling ring buffer with scroll support and source highlights."""
        all_lines = list(self._ring_buffer.lines)
        total = len(all_lines)

        if total == 0:
            return Panel(Text(""), title="Telemetry", border_style="blue")

        viewport_height = 15
        if self._console and hasattr(self._console, "size") and self._console.size and self._console.size.height > 12:
            viewport_height = max(5, self._console.size.height - 12)

        max_offset = max(0, total - 1)
        offset = min(max_offset, self._scroll_offset)

        if offset == 0:
            visible_lines = all_lines[-viewport_height:]
            title = "Telemetry"
        else:
            end_idx = total - offset
            start_idx = max(0, end_idx - viewport_height)
            visible_lines = all_lines[start_idx:end_idx]
            title = f"Telemetry [SCROLLED UP +{offset} — [Esc]/[G] for live]"

        formatted_text = Text()
        for i, line in enumerate(visible_lines):
            t = Text(line)
            if "[worker]" in line:
                t.highlight_regex(r"\[worker\]", "bold green")
            elif "[runner]" in line:
                t.highlight_regex(r"\[runner\]", "bold cyan")
            elif "[gate  ]" in line:
                t.highlight_regex(r"\[gate  \]", "bold yellow")
            formatted_text.append_text(t)
            if i < len(visible_lines) - 1:
                formatted_text.append("\n")

        border_color = "yellow" if offset > 0 else "blue"
        return Panel(formatted_text, title=title, border_style=border_color)

    def _build_layout(self) -> Layout:
        """Construct the split Layout container."""
        layout = Layout()
        if self._show_warning or (self._current_state is not None and self._current_state.tui_open):
            layout.update(build_warning_panel())
        else:
            layout.split_column(
                Layout(self._build_top_panel(), name="header", size=8),
                Layout(self._build_bottom_panel(), name="body"),
            )
        return layout

    def _update_layout(self) -> None:
        """Update the existing layout in place with fresh panel content."""
        if self._show_warning or (self._current_state is not None and self._current_state.tui_open):
            self._layout.split()
            self._layout.update(build_warning_panel())
        else:
            if self._layout.get("header") is not None and self._layout.get("body") is not None:
                self._layout["header"].update(self._build_top_panel())
                self._layout["body"].update(self._build_bottom_panel())
            else:
                self._layout.split()
                self._layout.split_column(
                    Layout(self._build_top_panel(), name="header", size=8),
                    Layout(self._build_bottom_panel(), name="body"),
                )
        if self._is_active and self._live is not None:
            self._live.update(self._layout, refresh=True)

    def render_to_console(self) -> None:
        """Helper to render the current layout snapshot directly to the console."""
        self._console.print(self._layout)

    def start(self) -> None:
        """Start the interactive Live dashboard."""
        if not self._is_active:
            self._live = Live(
                self._layout,
                console=self._console,
                refresh_per_second=4,
                auto_refresh=False,
            )
            self._live.start(refresh=True)
            self._is_active = True

    def stop(self) -> None:
        """Stop and tear down the interactive Live dashboard."""
        if self._is_active and self._live is not None:
            self._live.stop()
            self._is_active = False

    def refresh(self) -> None:
        """Force an immediate refresh of the Live dashboard."""
        self._update_layout()
        if self._is_active and self._live is not None:
            self._live.refresh()

