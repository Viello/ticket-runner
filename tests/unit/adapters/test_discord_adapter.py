"""Unit tests for DiscordAdapter stub (T066)."""

from __future__ import annotations

import logging
import pytest

from runner.adapters.discord import DiscordAdapter


def test_discord_adapter_stub_send_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    adapter = DiscordAdapter()
    with caplog.at_level(logging.WARNING):
        adapter.send("⚠ HANG detected — test_foo\nToken budget: 42k")

    assert "DiscordAdapter.send called on stub:" in caplog.text
    assert "⚠ HANG detected" in caplog.text


def test_discord_adapter_init_parameters() -> None:
    adapter = DiscordAdapter(token_env="MY_TOKEN_ENV", channel_id="123456789")
    assert adapter.token_env == "MY_TOKEN_ENV"
    assert adapter.channel_id == "123456789"
