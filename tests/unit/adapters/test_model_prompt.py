"""Unit tests for ModelPrompt UI adapter."""

from __future__ import annotations

import pytest

from runner.adapters.ui.model_prompt import ModelPrompt
from runner.domain.config import ModelEntry
from runner.domain.exceptions import NonInteractiveError


MODELS_TWO = (
    ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),
    ModelEntry(id="qwen/qwen-plus", label="Qwen Plus"),
)


def test_render_menu_format() -> None:
    prompt = ModelPrompt()
    menu = prompt.render_menu(MODELS_TWO)
    expected = (
        "Select model for this session:\n"
        "  [1] DeepSeek Chat    (deepseek/deepseek-chat)\n"
        "  [2] Qwen Plus        (qwen/qwen-plus)\n"
        "> _"
    )
    assert menu == expected


def test_select_model_zero_models_returns_none() -> None:
    output_lines: list[str] = []
    read_called = False

    def fake_read_key() -> str:
        nonlocal read_called
        read_called = True
        return "1"

    prompt = ModelPrompt(read_key=fake_read_key, output_fn=output_lines.append)
    res = prompt.select_model(())
    assert res is None
    assert output_lines == []
    assert read_called is False


def test_select_model_single_model_auto_selects_silently() -> None:
    single = (ModelEntry(id="deepseek/deepseek-chat", label="DeepSeek Chat"),)
    output_lines: list[str] = []
    read_called = False

    def fake_read_key() -> str:
        nonlocal read_called
        read_called = True
        return "1"

    prompt = ModelPrompt(read_key=fake_read_key, output_fn=output_lines.append)
    selected = prompt.select_model(single)
    assert selected == single[0]
    assert output_lines == []
    assert read_called is False


def test_select_model_valid_key_sequence() -> None:
    keys = ["2", "\r"]
    key_iter = iter(keys)
    output_lines: list[str] = []

    prompt = ModelPrompt(read_key=lambda: next(key_iter), output_fn=output_lines.append)
    selected = prompt.select_model(MODELS_TWO)

    assert selected == MODELS_TWO[1]
    assert len(output_lines) == 1
    assert "Select model for this session:" in output_lines[0]
    assert "[2] Qwen Plus" in output_lines[0]


def test_select_model_invalid_keys_loop_until_valid() -> None:
    # 9 (out of range), 'x' (non-digit), '\r' (Enter before selection), '1' (valid), '\n' (confirm)
    keys = ["9", "x", "\r", "1", "\n"]
    key_iter = iter(keys)
    output_lines: list[str] = []

    prompt = ModelPrompt(read_key=lambda: next(key_iter), output_fn=output_lines.append)
    selected = prompt.select_model(MODELS_TWO)

    assert selected == MODELS_TWO[0]


def test_select_model_eof_raises_non_interactive_error() -> None:
    prompt = ModelPrompt(read_key=lambda: "", output_fn=lambda _: None)
    with pytest.raises(NonInteractiveError) as exc_info:
        prompt.select_model(MODELS_TWO)
    assert "--model" in str(exc_info.value)


def test_select_model_os_error_raises_non_interactive_error() -> None:
    def raise_os_error() -> str:
        raise OSError("handle invalid")

    prompt = ModelPrompt(read_key=raise_os_error, output_fn=lambda _: None)
    with pytest.raises(NonInteractiveError) as exc_info:
        prompt.select_model(MODELS_TWO)
    assert "--model" in str(exc_info.value)
